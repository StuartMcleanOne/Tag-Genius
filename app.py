import os
import sqlite3
import xml.etree.ElementTree as ET
import json
import requests
import time
import io
import zipfile
import re
from flask import Flask, jsonify, request, send_file
from dotenv import load_dotenv
from flask_cors import CORS
from celery import Celery
from contextlib import contextmanager
from datetime import datetime

# --- SETUP ---

# Load environment variables from a .env file
load_dotenv()
# Initialize the Flask application
app = Flask(__name__)

# Configure Celery to use Redis as the message broker and result backend
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'

# Initialize Celery
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

# Enable Cross-Origin Resource Sharing (CORS) for frontend communication
CORS(app)
# Global variable to store the path of the last generated XML for export
LATEST_XML_PATH = None

# --- CONSTANTS ---

# Predefined vocabulary for AI tag generation consistency
CONTROLLED_VOCABULARY = {
    "primary_genre": [
        "House", "Techno", "Drum & Bass", "Breaks", "Trance", "Ambient/Downtempo",
        "Funk/Soul/Disco", "Hip Hop / Rap", "R&B", "Reggae", "Jazz", "Blues", "Rock",
        "Pop", "Classical", "Latin", "Caribbean", "World", "Film/Theatrical"
    ],
    "components": [
        "Vocal", "Instrumental", "Acapella", "Remix", "Intro", "Extended", "Edit",
        "Piano", "Keys", "Guitar", "Strings", "Orchestral", "Saxophone", "Trumpet", "Wind", "Brass"
    ],
    "energy_vibe": [
        "Aggressive", "Calm", "Dark", "Driving", "Energetic", "Funky",
        "Happy", "Hypnotic", "Mellow", "Romantic", "Soulful", "Uplifting"
    ],
    "situation_environment": [
        "After-afterhours", "Afterhours", "Beach", "Closer", "Filler",
        "Handoff", "Lounge", "Outro", "Peak Hour", "Pre-Party",
        "Sunset", "Warmup"
    ],
    "time_period": [
        "1920s", "1930s", "1940s", "1950s", "1960s", "1970s", "1980s",
        "1990s", "2000s", "2010s", "2020s"
    ]
}

# Main categories for the AI-powered genre grouping
MAIN_GENRE_BUCKETS = [
    "Electronic", "Hip Hop", "Rock", "Jazz-Funk-Soul", "World", "Pop", "Miscellaneous"
]


# --- DATABASE FUNCTIONS ---

def get_db_connection():
    """Establishes and returns a connection to the SQLite database."""
    conn = sqlite3.connect('tag_genius.db')
    conn.row_factory = sqlite3.Row  # Return rows as dictionary-like objects
    return conn


@contextmanager
def db_cursor():
    """ A context manager for handling database connections and cursors safely. """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        yield cursor  # Provide the cursor to the 'with' block
        conn.commit()  # Commit changes if the block executes successfully
    except sqlite3.Error as e:
        conn.rollback()  # Roll back changes on any database error
        print(f"Database transaction failed: {e}")  # Log the specific error
        raise e  # Re-raise the exception for higher-level handling
    finally:
        conn.close()  # Ensure the connection is always closed


@app.cli.command('init-db')
def init_db():
    """A Flask CLI command to initialize the database with all required tables."""
    try:
        with db_cursor() as cursor:
            # Tracks Table: Stores core track metadata and the full AI response JSON
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS tracks
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               name
                               TEXT
                               NOT
                               NULL,
                               artist
                               TEXT,
                               bpm
                               REAL,
                               track_key
                               TEXT,
                               genre
                               TEXT,
                               label
                               TEXT,
                               comments
                               TEXT,
                               grouping
                               TEXT,
                               tags_json
                               TEXT
                           );
                           """)
            # Tags Table: Stores unique tag names across all categories
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS tags
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               name
                               TEXT
                               NOT
                               NULL
                               UNIQUE
                           );
                           """)
            # Track_tags Link Table: Many-to-many relationship between tracks and tags
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS track_tags
                           (
                               track_id
                               INTEGER,
                               tag_id
                               INTEGER,
                               FOREIGN
                               KEY
                           (
                               track_id
                           ) REFERENCES tracks
                           (
                               id
                           ) ON DELETE CASCADE,
                               FOREIGN KEY
                           (
                               tag_id
                           ) REFERENCES tags
                           (
                               id
                           )
                             ON DELETE CASCADE,
                               PRIMARY KEY
                           (
                               track_id,
                               tag_id
                           )
                               );
                           """)
            # Processing_log Table: Tracks metadata about each tagging/splitting job run
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS processing_log
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               timestamp
                               DATETIME
                               DEFAULT
                               CURRENT_TIMESTAMP,
                               original_filename
                               TEXT
                               NOT
                               NULL,
                               input_file_path
                               TEXT,
                               output_file_path
                               TEXT,
                               track_count
                               INTEGER,
                               status
                               TEXT
                               NOT
                               NULL
                           );
                           """)
            # User_actions Table: Logs simple user interactions for the history feature
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS user_actions
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               timestamp
                               DATETIME
                               DEFAULT
                               CURRENT_TIMESTAMP,
                               action_description
                               TEXT
                               NOT
                               NULL
                           );
                           """)
        print('Database with all tables initialized successfully.')
    except sqlite3.Error as e:
        print(f"Database initialisation failed: {e}")


@app.cli.command('drop-tables')
def drop_tables():
    """Drops all application tables from the database for a clean reset."""
    try:
        with db_cursor() as cursor:
            print("Dropping all application tables...")
            # Drop tables in reverse order of creation to respect foreign key constraints
            cursor.execute("DROP TABLE IF EXISTS track_tags")
            cursor.execute("DROP TABLE IF EXISTS tags")
            cursor.execute("DROP TABLE IF EXISTS tracks")
            cursor.execute("DROP TABLE IF EXISTS processing_log")
            cursor.execute("DROP TABLE IF EXISTS user_actions")
            print("All application tables dropped successfully.")
    except sqlite3.Error as e:
        print(f"Failed to drop tables: {e}")


# --- EXTERNAL API FUNCTIONS ---

def insert_track_data(name, artist, bpm, track_key, genre, label, comments, grouping, tags_dict):
    """
    Inserts or updates track data and associated tags into the database.
    If track exists, updates; otherwise, inserts. Manages tags and links.
    """
    try:
        with db_cursor() as cursor:
            # Check if track already exists
            cursor.execute("SELECT id FROM tracks WHERE name = ? AND artist = ?", (name, artist))
            existing_track = cursor.fetchone()

            tags_json_string = json.dumps(tags_dict)  # Convert tags dict to JSON string

            if existing_track:
                track_id = existing_track['id']
                print(f"Updating existing track: {name} by {artist} (ID: {track_id})")
                cursor.execute(
                    """UPDATE tracks
                       SET bpm       = ?,
                           track_key = ?,
                           genre     = ?,
                           label     = ?,
                           comments  = ?,
                           grouping  = ?,
                           tags_json = ?
                       WHERE id = ?""",
                    (bpm, track_key, genre, label, comments, grouping, tags_json_string, track_id)
                )
                # Clear existing tags for this track before adding new ones
                cursor.execute("DELETE FROM track_tags WHERE track_id = ?", (track_id,))
            else:
                print(f"Inserting new track: {name} by {artist}")
                cursor.execute(
                    """INSERT INTO tracks (name, artist, bpm, track_key, genre, label, comments, grouping, tags_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (name, artist, bpm, track_key, genre, label, comments, grouping, tags_json_string)
                )
                track_id = cursor.lastrowid
                print(f"Successfully inserted track ID: {track_id}")

            # Process and link tags from the dictionary
            all_tags = set()
            if tags_dict:  # Only process if tags_dict is not empty
                for category_value in tags_dict.values():
                    if isinstance(category_value, list):
                        all_tags.update(t for t in category_value if
                                        isinstance(t, str) and t.strip())  # Add non-empty strings from list
                    elif isinstance(category_value, str) and category_value.strip():
                        all_tags.add(category_value.strip())  # Add non-empty string
                    # Ignore other types like int (energy_level)

            # Insert tags and links
            tag_ids = []
            for tag_name in all_tags:
                cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                tag_row = cursor.fetchone()
                tag_id = tag_row['id'] if tag_row else None
                if not tag_id:
                    cursor.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
                    tag_id = cursor.lastrowid
                tag_ids.append(tag_id)

            # Efficiently insert multiple links
            if tag_ids:
                values_to_insert = [(track_id, tag_id) for tag_id in tag_ids]
                cursor.executemany("INSERT OR IGNORE INTO track_tags (track_id, tag_id) VALUES (?, ?)",
                                   values_to_insert)

            print(f"Successfully processed {len(all_tags)} tags for track ID {track_id}.")

    except sqlite3.Error as e:
        print(f"Database error in insert_track_data for {artist} - {name}: {e}")


def log_job_start(filename, input_path):
    """Creates a new entry in the processing_log table for a new job."""
    try:
        with db_cursor() as cursor:
            cursor.execute(
                "INSERT INTO processing_log (original_filename, input_file_path, status) VALUES (?, ?, ?)",
                (filename, input_path, 'In Progress')
            )
            return cursor.lastrowid
    except sqlite3.Error as e:
        print(f"Failed to create log entry for {filename}: {e}")
        return None


def log_job_end(log_id, status, track_count, output_path):
    """ Updates a log entry with the final status and details of a completed job."""
    try:
        with db_cursor() as cursor:
            cursor.execute(
                "UPDATE processing_log SET status = ?, track_count = ?, output_file_path = ? WHERE id = ?",
                (status, track_count, output_path, log_id)
            )
            print(f"Finished logging for job ID: {log_id} with status: {status}")
    except sqlite3.Error as e:
        print(f"Failed to update log entry for job ID {log_id}: {e}")


def call_llm_for_tags(track_data, config, mode='full'):
    """
    Calls the OpenAI API to generate tags, operating in 'full' or 'genre_only' mode.
    Includes robust error handling and exponential backoff.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set. Returning default mock tags.")
        # Return structure matching expected output for each mode
        return {"primary_genre": ["Miscellaneous"], "sub_genre": []} if mode == 'genre_only' \
            else {"primary_genre": ["mock techno"], "sub_genre": ["Minimal"], "energy_level": 7}

    # Prepare data for the prompt, including sanitization
    primary_genre_list = ", ".join(CONTROLLED_VOCABULARY["primary_genre"])
    artist = track_data.get('ARTIST', '')
    title = track_data.get('TITLE', '')
    # Sanitize inputs to remove potentially problematic characters for the API
    sanitized_artist = re.sub(r'[^\w\s\-\(\)\'\".:,/]', '', artist)
    sanitized_title = re.sub(r'[^\w\s\-\(\)\'\".:,/]', '', title)

    # Base prompt structure common to both modes
    prompt_parts = [
        "You are an expert musicologist specializing in electronic dance music. Provide structured tags for a DJ library.",
        f"Track Data:\nTrack: '{sanitized_artist} - {sanitized_title}'",
        f"Existing Genre: {track_data.get('GENRE')}\nYear: {track_data.get('YEAR')}\n",
        "Provide a JSON object with these keys:",
        f"1. 'primary_genre': Choose EXACTLY ONE from: [{primary_genre_list}]",
        f"2. 'sub_genre': Provide up to {config.get('sub_genre', 2)} specific, widely-recognized sub-genres (e.g., 'French House')."
    ]

    # Add detailed instructions only if in 'full' mode
    if mode == 'full':
        components_list = ", ".join(CONTROLLED_VOCABULARY["components"])
        energy_vibe_list = ", ".join(CONTROLLED_VOCABULARY["energy_vibe"])
        situation_environment_list = ", ".join(CONTROLLED_VOCABULARY["situation_environment"])
        time_period_list = ", ".join(CONTROLLED_VOCABULARY["time_period"])

        full_mode_instructions = [
            "3. 'energy_level': Integer 1-10, calibrated for electronic dance music DJs.",
            "   - Use 1-3 for low energy (ambient/chill). Do not overrate these.",
            "   - Use 9-10 only for peak-time anthems.",
            f"4. 'components': Up to {config.get('components', 3)} from: [{components_list}]. Use specific synth/drum names if known (e.g., 'TB-303').",
            "5. Additional tags (choose up to specified number):",
            f"   - 'energy_vibe' (up to {config.get('energy_vibe', 2)}): [{energy_vibe_list}]",
            f"   - 'situation_environment' (up to {config.get('situation_environment', 2)}): [{situation_environment_list}]",
            f"   - 'time_period' (up to {config.get('time_period', 1)}): [{time_period_list}]"
        ]
        prompt_parts.extend(full_mode_instructions)

    prompt_parts.append("\nResponse MUST be a single, valid JSON object.")
    prompt_text = "\n\n".join(prompt_parts)

    # Prepare API request details
    api_url = "https://api.openai.com/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {
        "model": "gpt-4o-mini",  # Consider making model configurable
        "messages": [{"role": "user", "content": prompt_text}],
        "response_format": {"type": "json_object"}
    }

    # Implement exponential backoff for retries
    max_retries = 5
    initial_delay = 2
    for attempt in range(max_retries):
        try:
            timeout_seconds = 15 if mode == 'genre_only' else 30
            response = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=timeout_seconds)
            response.raise_for_status()  # Check for HTTP errors (4xx, 5xx)

            # Safely extract content from response
            text_part = response.json().get("choices", [{}])[0].get("message", {}).get("content")
            if text_part:
                print(f"Successfully tagged (mode: {mode}): {artist} - {title}")  # Log original names
                json_response = json.loads(text_part)

                # Ensure primary_genre is always a list for consistent handling
                if isinstance(json_response.get('primary_genre'), str):
                    json_response['primary_genre'] = [json_response['primary_genre']]
                elif not isinstance(json_response.get('primary_genre'), list):
                    json_response['primary_genre'] = ["Miscellaneous"]  # Default if missing/invalid

                # Ensure sub_genre key exists for genre_only mode
                if mode == 'genre_only' and 'sub_genre' not in json_response:
                    json_response['sub_genre'] = []
                elif 'sub_genre' in json_response and not isinstance(json_response['sub_genre'], list):
                    json_response['sub_genre'] = []  # Default if invalid type

                return json_response

        except requests.exceptions.RequestException as e:
            # Handle network errors and HTTP errors (including 429 rate limit)
            delay = initial_delay * (2 ** attempt)
            print(
                f"AI call failed for {artist} - {title} (mode: {mode}, error: {type(e).__name__}). Retrying in {delay} seconds...")
            time.sleep(delay)
        except json.JSONDecodeError as e:
            # Handle cases where the AI response is not valid JSON
            print(f"Error decoding JSON for {artist} - {title} (mode: {mode}): {e}")
            # Return a default structure matching expected format to prevent downstream errors
            return {"primary_genre": ["Miscellaneous"], "sub_genre": []} if mode == 'genre_only' \
                else {"primary_genre": ["Miscellaneous"], "sub_genre": [],
                      "energy_level": None}  # Provide default for full mode too

    # If all retries fail
    print(f"Max retries exceeded for track: {artist} - {title} (mode: {mode})")
    return {"primary_genre": ["Miscellaneous"], "sub_genre": []} if mode == 'genre_only' \
        else {"primary_genre": ["Miscellaneous"], "sub_genre": [], "energy_level": None}


def convert_energy_to_rating(energy_level):
    """Converts a 1-10 energy level to a Rekordbox 1-5 star rating value (0-255)."""
    if not isinstance(energy_level, (int, float)): return 0
    if energy_level >= 9:
        return 255  # 5 Stars
    elif energy_level == 8:
        return 204  # 4 Stars
    elif energy_level >= 6:
        return 153  # 3 Stars
    elif energy_level >= 4:
        return 102  # 2 Stars
    else:
        return 51  # 1 Star (Covers 1, 2, 3)


def get_genre_map_from_ai(genre_list):
    """
    Takes a list of specific genres and uses the AI to map them to the main
    genre buckets. It processes the list in batches to avoid creating prompts
    that are too long for the API.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set. Cannot group genres.")
        return {genre: "Miscellaneous" for genre in genre_list}

    if not genre_list:
        return {}

    main_buckets_str = ", ".join(MAIN_GENRE_BUCKETS)
    final_genre_map = {}
    batch_size = 10  # Process 10 genres per API call

    # Split the genre_list into smaller chunks (batches)
    for i in range(0, len(genre_list), batch_size):
        batch = genre_list[i:i + batch_size]
        print(f"Processing genre batch {i // batch_size + 1}: {batch}")

        genres_to_map_str = ", ".join(f"'{re.sub(r'[^\w\s\-/]', '', g)}'" for g in batch)

        prompt_text = (
            f"You are a master music librarian. Categorize specific music genres into main departments. "
            f"Main departments: [{main_buckets_str}].\n\n"
            f"Genres to categorize: [{genres_to_map_str}].\n\n"
            f"Respond with a single JSON object mapping each original genre to its department. "
            f"Map unknown genres to 'Miscellaneous'. "
            f"Example: {{ \"Industrial Techno\": \"Electronic\", \"Indie Folk\": \"Rock\" }}"
        )

        api_url = "https://api.openai.com/v1/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt_text}],
            "response_format": {"type": "json_object"}
        }

        # Increased patience to better handle API rate limiting.
        max_retries = 5
        initial_delay = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=20)
                response.raise_for_status()
                data = response.json()
                raw_content = data.get("choices", [{}])[0].get("message", {}).get("content")
                if raw_content:
                    genre_map_batch = json.loads(raw_content)
                    print(f"AI successfully processed batch. Result: {genre_map_batch}")

                    # Use the case-insensitive logic from before for this batch
                    ai_map_lower = {k.lower(): v for k, v in genre_map_batch.items()}
                    validated_batch = {g: ai_map_lower.get(g.lower(), "Miscellaneous") for g in batch}

                    # Add the results of this batch to the final map
                    final_genre_map.update(validated_batch)
                    break  # Success, so break the retry loop for this batch
            except requests.exceptions.RequestException as e:
                delay = initial_delay * (2 ** attempt)
                print(f"AI Grouper call failed for batch ('{type(e).__name__}'). Retrying in {delay} seconds...")
                time.sleep(delay)
            except json.JSONDecodeError as e:
                print(f"AI Grouper call failed due to JSON error: {e}")
                break  # Don't retry on a JSON error

        # If a batch failed after all retries, map its genres to Miscellaneous
        for genre in batch:
            if genre not in final_genre_map:
                final_genre_map[genre] = "Miscellaneous"

    print("Finished processing all genre batches.")
    return final_genre_map


# --- CORE LOGIC ---

def get_primary_genre(track_element):
    """
    Parses the Genre tag of a track to determine its primary genre.
    If the genre is missing or empty, it calls the main AI in 'genre_only' mode as a fallback.
    Returns a single genre string.
    """
    genre_str = track_element.get('Genre', '').strip()
    primary_genre = None

    # Attempt to parse existing genre tag locally first
    if genre_str:
        # Take only the first part before common delimiters (comma, slash)
        parsed_genre = re.split(r'[,/]', genre_str)[0].strip()
        # Accept only if the result is not an empty string
        if parsed_genre:
            primary_genre = parsed_genre

    # If local parsing failed or resulted in empty string, call AI
    if not primary_genre:
        print(
            f"No valid genre found locally for '{track_element.get('Artist')} - {track_element.get('Name')}'. Asking AI (genre_only mode)...")
        track_data = {
            'ARTIST': track_element.get('Artist'),
            'TITLE': track_element.get('Name'),
            'GENRE': track_element.get('Genre'),  # Pass original as context
            'YEAR': track_element.get('Year')  # Pass year as context
        }
        # Call the main AI function in its fast, genre-focused mode
        # Provide an empty config dict {} as config is not needed for genre_only
        ai_response = call_llm_for_tags(track_data, {}, mode='genre_only')

        # Safely extract the primary genre from the AI response
        # Check if response exists, is dict, has 'primary_genre' key which is a non-empty list
        if ai_response and isinstance(ai_response, dict) and \
                isinstance(ai_response.get('primary_genre'), list) and ai_response['primary_genre']:
            # The AI returns a list, take the first item. Ensure it's not empty.
            primary_genre_from_ai = ai_response['primary_genre'][0]
            # Return the valid AI genre, or Miscellaneous if it's somehow empty
            return primary_genre_from_ai if primary_genre_from_ai else "Miscellaneous"
        else:
            # Default if AI call failed or returned invalid/empty data
            print(
                f"AI failed to provide valid primary genre for '{track_element.get('Artist')} - {track_element.get('Name')}'. Defaulting to Miscellaneous.")
            return "Miscellaneous"

            # Return the genre found locally if valid
    return primary_genre


def split_xml_by_genre(input_path, job_folder_path):
    """
    Parses a Rekordbox XML, groups tracks by specific genres using intelligent fallback,
    then uses a dynamic AI call to group those into main buckets before saving files.
    """
    print("--- DEFINITIVE V3 SPLITTER IS RUNNING ---")  # <-- ADD THIS LINE
    print(f"Starting split process for file: {input_path} into folder: {job_folder_path}")
    try:
        original_tree = ET.parse(input_path)
        root = original_tree.getroot()
        collection = root.find('COLLECTION')
        if collection is None:
            raise ValueError("Could not find COLLECTION element in XML.")
        tracks = collection.findall('TRACK')
        if not tracks:
            print("No tracks found in the input file's COLLECTION.")
            return []

        # STAGE 1: RAW SORT (Determine specific primary genre for each track)
        genre_groups = {}
        print("Starting Stage 1: Determining primary genre for each track...")
        for i, track in enumerate(tracks):
            # Use the intelligent helper function (handles local parse + AI fallback)
            primary_genre = get_primary_genre(track)
            if primary_genre not in genre_groups:
                genre_groups[primary_genre] = []
            genre_groups[primary_genre].append(track)
            # Log progress periodically
            if (i + 1) % 50 == 0:
                print(f"Processed {i + 1}/{len(tracks)} tracks for initial genre sorting...")

        print(f"Finished Stage 1. Found raw genres: {list(genre_groups.keys())}")

        # STAGE 2: DYNAMIC AI-POWERED GROUPING
        unique_genres = list(genre_groups.keys())
        if not unique_genres:
            print("No genres determined after Stage 1.")
            return []

        print("Starting Stage 2: Calling AI to group genres into main buckets...")
        # Call AI once with the list of unique specific genres found
        genre_map = get_genre_map_from_ai(unique_genres)

        if "R&B" in genre_map:
            genre_map["R&B"] = "Hip Hop"

        print(f"AI Genre Map received: {genre_map}")

        # Use the AI-generated map to merge tracks into final main buckets
        main_genre_buckets = {}
        for genre, track_list in genre_groups.items():
            # Look up the bucket for the specific genre, default to Miscellaneous
            main_bucket_name = genre_map.get(genre, "Miscellaneous")
            if main_bucket_name not in main_genre_buckets:
                main_genre_buckets[main_bucket_name] = []
            main_genre_buckets[main_bucket_name].extend(track_list)

        print(f"Finished Stage 2. Grouped into main buckets: {list(main_genre_buckets.keys())}")

        # FILE CREATION (using the final, grouped buckets)
        created_files = []
        print("Starting file creation...")
        for bucket_name, track_list in main_genre_buckets.items():
            if not track_list: continue  # Skip creating empty files

            # Build a new, valid XML structure for this bucket
            new_root = ET.Element('DJ_PLAYLISTS', attrib={'Version': '1.0.0'})
            ET.SubElement(new_root, 'PRODUCT', attrib={'Name': 'Tag Genius', 'Version': '1.0', 'Company': ''})
            new_collection = ET.SubElement(new_root, 'COLLECTION', attrib={'Entries': str(len(track_list))})
            # Add all tracks belonging to this bucket
            for track_element in track_list:
                new_collection.append(track_element)

            # Prepare filename and save
            new_tree = ET.ElementTree(new_root)
            # Make filename safe (replace space, slash, ampersand with underscore)
            safe_bucket_name = re.sub(r'[ /&]', '_', bucket_name)
            filename = f"{safe_bucket_name}.xml"
            output_path = os.path.join(job_folder_path, filename)

            try:
                new_tree.write(output_path, encoding='UTF-8', xml_declaration=True)
                created_files.append(output_path)
                print(f"Successfully created {filename} with {len(track_list)} tracks.")
            except IOError as e:
                print(f"Error writing file {filename}: {e}")  # Log file writing errors

        print(f"Finished file creation. {len(created_files)} files created.")
        return created_files

    except ET.ParseError as e:
        print(f"Fatal Error: Could not parse input XML file: {e}")
        raise  # Propagate error up
    except Exception as e:  # Catch any other unexpected errors during split
        print(f"An unexpected error occurred during split_xml_by_genre: {e}")
        # import traceback # Uncomment for detailed debugging
        # print(traceback.format_exc())
        raise  # Propagate error up


def clear_ai_tags(track_element):
    """
    Clears specific metadata fields generated by Tag Genius from a track element.
    """
    # Clear AI-formatted comments (/* ... */)
    current_comments = track_element.get('Comments', '')
    cleaned_comments = re.sub(r'/\*.*?\*/', '', current_comments).strip()
    track_element.set('Comments', cleaned_comments)
    # Clear Colour and Grouping, unless manually set to Red
    if track_element.get('Colour') != '0xFF0000':
        if 'Colour' in track_element.attrib: del track_element.attrib['Colour']
        if 'Grouping' in track_element.attrib: del track_element.attrib['Grouping']
    # Reset star rating to 0
    track_element.set('Rating', '0')
    return track_element  # Return modified element


@celery.task
def process_library_task(log_id,input_path, output_path, config):
    """Celery task to orchestrate the full tagging process for an XML file."""

    if not log_id:
        return {"error": "Failed to initialize logging for the job."}

    try:
        tree = ET.parse(input_path)
        root = tree.getroot()
        collection = root.find('COLLECTION')
        if collection is None: raise ValueError("COLLECTION element not found.")
        tracks = collection.findall('TRACK')
        total_tracks = len(tracks)
        print(f"Found {total_tracks} tracks. Starting tagging process...")

        processed_count = 0
        for index, track in enumerate(tracks):
            track_name = track.get('Name')
            artist = track.get('Artist')
            print(f"\nProcessing track {index + 1}/{total_tracks}: {artist} - {track_name}")

            # Optionally clear existing AI tags first
            if config.get('clear_tags', False):
                clear_ai_tags(track)
                print(f"Cleared existing AI tags for: {track_name}")

            # Proceed with AI tagging only if level is not "None"
            if config.get('level') != 'None':
                track_data = {'ARTIST': artist, 'TITLE': track_name, 'GENRE': track.get('Genre'),
                              'YEAR': track.get('Year')}
                # Call AI in 'full' mode
                generated_tags = call_llm_for_tags(track_data, config, mode='full')

                # Validate response before proceeding
                if not generated_tags or not generated_tags.get('primary_genre'):
                    print("Skipping tag update due to empty or invalid AI response.")
                    # Save track data even if AI fails, using existing/cleared values
                    insert_track_data(track_name, artist, track.get('AverageBpm'), track.get('Tonality'),
                                      track.get('Genre'), track.get('Label'), track.get('Comments'),
                                      track.get('Grouping'), {})
                    continue  # Move to next track

                def ensure_list(value):
                    if isinstance(value, str): return [value]
                    if isinstance(value, list): return value
                    return []

                # Update XML Element with AI data
                primary_genre = ensure_list(generated_tags.get('primary_genre'))
                sub_genre = ensure_list(generated_tags.get('sub_genre'))
                new_genre_string = ", ".join(g for g in primary_genre + sub_genre if g)  # Join non-empty genres
                track.set('Genre',
                          new_genre_string if new_genre_string else track.get('Genre', ''))  # Keep old if new is empty

                # Format comments string
                tag_order_and_prefixes = {'situation_environment': 'Sit', 'energy_vibe': 'Vibe',
                                          'components': 'Comp', 'time_period': 'Time'}
                formatted_parts = []
                energy_level = generated_tags.get('energy_level')
                if isinstance(energy_level, int):
                    formatted_parts.append(f"E: {str(energy_level).zfill(2)}")
                for key, prefix in tag_order_and_prefixes.items():
                    tags = ensure_list(generated_tags.get(key))
                    if tags:
                        tag_string = ", ".join([t.strip().capitalize() for t in tags if t])  # Filter empty tags
                        if tag_string: formatted_parts.append(f"{prefix}: {tag_string}")
                final_comments_content = ' / '.join(formatted_parts)
                final_comments = f"/* {final_comments_content} */" if final_comments_content else ""
                track.set('Comments', final_comments)

                # Set Colour, respecting Red override and using calibrated mapping
                if track.get('Colour') != '0xFF0000':
                    energy_level = generated_tags.get('energy_level')
                    track_colour_hex, track_colour_name = None, None  # Use None instead of "None"
                    if isinstance(energy_level, int):
                        if energy_level >= 9:
                            track_colour_hex, track_colour_name = '0xFF007F', "Pink"
                        elif energy_level == 8:
                            track_colour_hex, track_colour_name = '0xFFA500', "Orange"
                        elif energy_level >= 6:
                            track_colour_hex, track_colour_name = '0xFFFF00', "Yellow"
                        elif energy_level >= 4:
                            track_colour_hex, track_colour_name = '0x00FF00', "Green"
                        else:
                            track_colour_hex, track_colour_name = '0x25FDE9', "Aqua"

                    if track_colour_hex:
                        track.set('Colour', track_colour_hex)
                        track.set('Grouping', track_colour_name)
                        print(f"Colour-coded track as {track_colour_name} based on energy: {energy_level}/10")
                    else:  # Remove attributes if no color assigned
                        if 'Colour' in track.attrib: del track.attrib['Colour']
                        if 'Grouping' in track.attrib: del track.attrib['Grouping']

                # Set Star Rating using calibrated mapping
                energy_level = generated_tags.get('energy_level')
                rating_value = convert_energy_to_rating(energy_level) if energy_level is not None else 0
                track.set('Rating', str(rating_value))
                print(f"Assigned star rating based on energy level: {energy_level}/10 -> {rating_value}")

                print(f"Updated XML for: {track_name}")
                processed_count += 1

                # Save to database (will update if exists)
                insert_track_data(
                    track_name, artist, track.get('AverageBpm'), track.get('Tonality'),
                    new_genre_string if new_genre_string else track.get('Genre', ''),  # Pass potentially updated genre
                    track.get('Label'), final_comments, track.get('Grouping'),  # Grouping might be None
                    generated_tags
                )

            else:  # Handle "None" level (Clear Only workflow)
                print(f"Skipped AI tagging for: {track_name} (Level: None)")
                # Save cleared track data to the database
                insert_track_data(
                    track_name, artist, track.get('AverageBpm'), track.get('Tonality'),
                    track.get('Genre'), track.get('Label'), track.get('Comments'), track.get('Grouping'),
                    {}  # Pass empty dict for tags
                )
                processed_count += 1  # Count as processed even if only cleared

        # Ensure the COLLECTION 'Entries' count matches the number of tracks processed/kept
        collection.set('Entries', str(len(collection.findall('TRACK'))))  # Recalculate based on final tracks in element

        # Write the final modified XML tree
        tree.write(output_path, encoding='UTF-8', xml_declaration=True)
        log_job_end(log_id, 'Completed', total_tracks, output_path)  # Log total tracks attempted
        print(
            f"\nTagging process complete! {processed_count}/{total_tracks} tracks processed. New file saved at: {output_path}")
        return {"message": "Success! Your new library file is ready.", "filePath": output_path}

    except Exception as e:
        log_job_end(log_id, 'Failed', 0, output_path)
        print(f"FATAL error during tagging job {log_id}: {e}")
        # import traceback # For detailed debugging
        # print(traceback.format_exc())
        return {"error": f"Failed to process XML: {str(e)}"}


# --- FLASK ROUTES ---

@app.route('/')
def hello_ai():
    """A simple route to confirm the server is running."""
    return 'Hello, Tag Genius!'  # Updated message


@app.route('/upload_library', methods=['POST'])
def upload_library():
    """Handles XML file upload, saves it uniquely, and dispatches the tagging task."""
    global LATEST_XML_PATH
    if 'file' not in request.files: return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if not file or file.filename == '': return jsonify({"error": "No selected file"}), 400

    config_str = request.form.get('config')
    if not config_str: return jsonify({"error": "No config provided"}), 400
    try:
        config = json.loads(config_str)
        # Basic config validation (optional but recommended)
        if not isinstance(config, dict) or 'level' not in config:
            raise ValueError("Invalid config format")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Invalid config received: {config_str}, Error: {e}")
        return jsonify({"error": f"Invalid config format: {e}"}), 400

    if file:
        try:
            original_filename = file.filename
            name, ext = os.path.splitext(original_filename)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            # Create unique filenames
            unique_input_filename = f"{name}_{timestamp}{ext}"
            unique_output_filename = f"tagged_{name}_{timestamp}{ext}"
            # Define folders and ensure they exist
            upload_folder, output_folder = "uploads", "outputs"
            os.makedirs(upload_folder, exist_ok=True)
            os.makedirs(output_folder, exist_ok=True)
            # Construct full paths
            input_path = os.path.join(upload_folder, unique_input_filename)
            output_path = os.path.join(output_folder, unique_output_filename)

            # Save the uploaded file
            file.seek(0)  # Ensure pointer is at start before saving
            file.save(input_path)

            log_id = log_job_start(original_filename,input_path)
            if not log_id:
                return jsonify({"error": "Failed to create a job log entry. "}), 500


            # Dispatch the background task
            process_library_task.delay(log_id,input_path, output_path, config)
            LATEST_XML_PATH = output_path  # Store path for potential export
            print(f"Tagging job dispatched with ID {log_id} for {original_filename}.")
            return jsonify({
                "message": "Success! Your library is now being processed in the background.",
                "job_id": log_id
            }), 202

        except Exception as e:
            print(f"Error during file save or task dispatch for {file.filename}: {e}")
            return jsonify({"error": "Failed to save file or start processing task."}), 500

    # Fallback error (should not be reached)
    return jsonify({"error": "Unknown error during upload."}), 500


@app.route('/analyze_library', methods=['POST'])
def analyze_library():
    """
    Quickly scans an uploaded XML file to count tracks missing a genre tag.
    Used by frontend to set expectations for the splitter speed.
    """
    if 'file' not in request.files: return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if not file or file.filename == '': return jsonify({"error": "No selected file"}), 400

    if file:
        try:
            file.seek(0)  # Rewind before parsing
            tree = ET.parse(file)
            root = tree.getroot()
            collection = root.find('COLLECTION')
            if collection is None: raise ValueError("COLLECTION element not found.")
            tracks = collection.findall('TRACK')

            untagged_count = 0
            for track in tracks:
                genre_str = track.get('Genre', '').strip()
                if not genre_str: untagged_count += 1

            file.seek(0)  # Rewind again for potential next read
            print(f"Analyzed {file.filename}: Found {untagged_count} untagged tracks.")
            return jsonify({"untagged_count": untagged_count}), 200

        except ET.ParseError as e:
            print(f"XML Parse Error in analyze_library for {file.filename}: {e}")
            return jsonify({"error": "Failed to parse XML: Invalid format"}), 400
        except ValueError as e:  # Catch specific error from missing COLLECTION
            print(f"XML Structure Error in analyze_library for {file.filename}: {e}")
            return jsonify({"error": f"Invalid XML Structure: {e}"}), 400
        except Exception as e:
            print(f"Unexpected error in analyze_library for {file.filename}: {e}")
            return jsonify({"error": "An unexpected error occurred during analysis."}), 500

    # Fallback error
    return jsonify({"error": "Unknown error during analysis."}), 500


@app.route('/split_library', methods=['POST'])
def split_library():
    """
    Handles XML file upload, creates a job subfolder, calls the intelligent splitter,
    and returns a list of the generated (grouped) file paths relative to 'outputs'.
    """
    if 'file' not in request.files: return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if not file or file.filename == '': return jsonify({"error": "No selected file"}), 400

    if file:
        original_filename = file.filename
        name, ext = os.path.splitext(original_filename)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        # Create unique subfolder within 'outputs'
        job_folder_name = f"{timestamp}_{name}_split"
        job_folder_path = os.path.join("outputs", job_folder_name)
        os.makedirs(job_folder_path, exist_ok=True)

        # Save original file inside job folder
        input_path = os.path.join(job_folder_path, "original_library.xml")
        try:
            file.seek(0)  # Ensure file pointer is at start
            file.save(input_path)

            print(f"Split job started for {original_filename}. Job folder: {job_folder_path}")
            # Call the main splitting logic function
            new_files_full_paths = split_xml_by_genre(input_path, job_folder_path)

            # Convert absolute paths returned by split_xml_by_genre to paths
            # relative to the 'outputs' directory for frontend consistency.
            outputs_base_path = os.path.abspath("outputs")
            relative_paths = [os.path.relpath(p, start=outputs_base_path) for p in new_files_full_paths]

            print(f"Split job completed for {original_filename}. Generated files: {relative_paths}")
            return jsonify({
                "message": "Library split successfully!",
                "files": relative_paths,  # Send relative paths back
            }), 200

        except Exception as e:
            # Catch errors from file saving or the splitting function
            print(f"Error during split_library processing for {original_filename}: {e}")
            # import traceback # Uncomment for detailed stack trace
            # print(traceback.format_exc())
            return jsonify({"error": f"Failed to split library: {str(e)}"}), 500

    # Fallback error
    return jsonify({"error": "Unknown error during split request."}), 500


@app.route('/download_split_file', methods=['GET'])
def download_split_file():
    """
    Safely serves a single split XML file for download using a relative path
    (relative to the 'outputs' directory). Performs security checks.
    """
    relative_file_path = request.args.get('path')
    if not relative_file_path:
        return jsonify({"error": "File path parameter 'path' is required"}), 400

    # Normalize path and prevent directory traversal
    relative_file_path = os.path.normpath(relative_file_path).lstrip('./\\')  # Normalize and remove leading separators
    if '..' in relative_file_path.split(os.path.sep):
        print(f"Attempted directory traversal detected: {relative_file_path}")
        return jsonify({"error": "Invalid file path (Traversal attempt)"}), 400

    # Construct full path safely within 'outputs'
    safe_base_path = os.path.abspath("outputs")
    requested_path = os.path.join(safe_base_path, relative_file_path)

    # Final check: Ensure resolved path is still inside 'outputs'
    if not os.path.abspath(requested_path).startswith(safe_base_path):
        print(f"Security violation: Path resolved outside base directory: {requested_path}")
        return jsonify({"error": "Invalid file path (Security violation)"}), 403  # Forbidden

    # Check if file exists and is actually a file (not a directory)
    if os.path.exists(requested_path) and os.path.isfile(requested_path):
        print(f"Serving file for download: {requested_path}")
        return send_file(requested_path, as_attachment=True)
    else:
        print(f"Download request: File not found at {requested_path}")
        return jsonify({"error": "Requested file not found"}), 404


@app.route('/export_xml', methods=['GET'])
def export_xml():
    """Allows the user to download the most recently generated tagged XML file."""
    global LATEST_XML_PATH
    if LATEST_XML_PATH and os.path.exists(LATEST_XML_PATH) and os.path.isfile(LATEST_XML_PATH):
        print(f"Exporting last tagged file: {LATEST_XML_PATH}")
        return send_file(LATEST_XML_PATH, as_attachment=True)
    else:
        print(
            f"Export request failed: LATEST_XML_PATH='{LATEST_XML_PATH}', Exists={os.path.exists(LATEST_XML_PATH if LATEST_XML_PATH else '')}")
        return jsonify({"error": "No tagged file available to export or file was moved/deleted."}), 404


@app.route('/history', methods=['GET'])
def get_history():
    """Retrieves the log of all past tagging/processing jobs."""
    try:
        with db_cursor() as cursor:
            # Select columns relevant to job history display
            logs = cursor.execute(
                "SELECT id, timestamp, original_filename, track_count, status, output_file_path FROM processing_log ORDER BY timestamp DESC"
            ).fetchall()
        history_list = [dict(row) for row in logs]
        return jsonify(history_list)
    except sqlite3.Error as e:
        print(f"Database error in get_history: {e}")
        return jsonify({"error": "Failed to retrieve job history"}), 500


@app.route('/download_job/<int:job_id>', methods=['GET'])
def download_job_package(job_id):
    """
    Finds a tagging job by ID, zips its original input and tagged output files,
    and sends the archive for download.
    """
    input_path, output_path = None, None  # Initialize paths
    original_filename = f"job_{job_id}_files"  # Default base name
    try:
        with db_cursor() as cursor:
            log_entry = cursor.execute(
                "SELECT original_filename, input_file_path, output_file_path FROM processing_log WHERE id = ?",
                (job_id,)
            ).fetchone()

        if not log_entry: return jsonify({"error": f"Job ID {job_id} not found"}), 404

        input_path = log_entry['input_file_path']
        output_path = log_entry['output_file_path']
        original_filename = os.path.splitext(log_entry['original_filename'])[0]  # Use original name base

        # Validate existence of both files before zipping
        if not input_path or not os.path.exists(input_path):
            return jsonify({"error": f"Original input file missing for job {job_id}."}), 404
        if not output_path or not os.path.exists(output_path):
            return jsonify({"error": f"Tagged output file missing for job {job_id}."}), 404

        # Create zip file in memory
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Use more descriptive names within the zip archive
            zf.write(input_path, arcname=f'original_{os.path.basename(input_path)}')
            zf.write(output_path, arcname=f'tagged_{os.path.basename(output_path)}')
        memory_file.seek(0)

        print(f"Prepared archive for job {job_id}")
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'tag_genius_job_{job_id}_{original_filename}_archive.zip'  # More informative name
        )
    except sqlite3.Error as e:
        print(f"Database error finding job {job_id}: {e}")
        return jsonify({"error": "Database error retrieving job details."}), 500
    except FileNotFoundError:
        missing = input_path if not os.path.exists(input_path) else output_path
        print(f"File not found during zipping for job {job_id}: {missing}")
        return jsonify({"error": "Archive file(s) missing on server."}), 404
    except Exception as e:
        print(f"Error creating zip package for job {job_id}: {e}")
        return jsonify({"error": "Failed to create download package."}), 500


@app.route('/log_action', methods=['POST'])
def log_action():
    """
    Receives an action description from the frontend via JSON and logs it.
    """
    if not request.is_json: return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    description = data.get('action_description')
    if not description or not isinstance(description, str):
        return jsonify({"error": "Valid 'action_description' string is required"}), 400

    try:
        with db_cursor() as cursor:
            cursor.execute("INSERT INTO user_actions (action_description) VALUES (?)", (description,))
        return jsonify({"message": "Action logged successfully"}), 201
    except sqlite3.Error as e:
        print(f"Database error logging action: {description} - {e}")
        return jsonify({"error": "Failed to log action due to database error"}), 500


@app.route('/get_actions', methods=['GET'])
def get_actions():
    """
    Retrieves all logged user actions, ordered most recent first.
    """
    try:
        with db_cursor() as cursor:
            actions = cursor.execute(
                "SELECT timestamp, action_description FROM user_actions ORDER BY timestamp DESC"
            ).fetchall()
        # Format for JSON
        action_list = [{"timestamp": row['timestamp'], "description": row['action_description']} for row in actions]
        return jsonify(action_list)
    except sqlite3.Error as e:
        print(f"Database error retrieving actions: {e}")
        return jsonify({"error": "Failed to retrieve actions due to database error"}), 500


# --- Main Execution Guard ---
if __name__ == '__main__':
    # Runs the Flask development server (host='0.0.0.0' makes it accessible on local network)
    # Use debug=False in a real production environment
    print("Starting Flask development server on http://127.0.0.1:5001")
    app.run(host='0.0.0.0', port=5001, debug=True)

