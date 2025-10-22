import os
import sqlite3
import xml.etree.ElementTree as ET
import json
from asyncio import timeout

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

app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'

celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

# Enable Cross-Origin Resource Sharing (CORS) to allow the front-end to communicate with the backend
CORS(app)
# Global variable to store the path of the last generated XML file for the export function
LATEST_XML_PATH = None

# --- CONSTANTS ---

# A predefined dictionary of tags to ensure the AI's output is consistent and predictable.
CONTROLLED_VOCABULARY = {
    "primary_genre": [
        "House", "Techno", "Drum & Bass", "Breaks", "Trance", "Ambient/Downtempo",
        "Funk/Soul/Disco", "Hip Hop / Rap", "Reggae", "Jazz", "Blues", "Rock",
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

MAIN_GENRE_BUCKETS = [
    "Electronic", "Hip Hop", "Rock", "Jazz-Funk-Soul", "World", "Pop", "Miscellaneous"
]

# --- DATABASE FUNCTIONS ---

def get_db_connection():
    """Establishes and returns a connection to the SQLite database."""
    conn = sqlite3.connect('tag_genius.db')
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db_cursor():
    """ A context manager for handling database connections and cursors. """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


@app.cli.command('init-db')
def init_db():
    """A Flask CLI command to initialize the database with all tables."""
    try:
        with db_cursor() as cursor:
            # Tracks Table.
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS tracks
                           (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, artist TEXT, bpm REAL,
                           track_key TEXT, genre TEXT, label TEXT, comments TEXT, grouping TEXT, tags_json TEXT);
                           """)
            # Tags Table.
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS tags
                           (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE);
                           """)
            # Track_tags Link Table.
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS track_tags
                           (track_id INTEGER, tag_id INTEGER,
                           FOREIGN KEY (track_id) REFERENCES tracks (id),
                           FOREIGN KEY (tag_id) REFERENCES tags (id),
                           PRIMARY KEY (track_id, tag_id));
                           """)
            # The  processing_log table for conversation history.
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS processing_log
                           (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                           original_filename TEXT NOT NULL, input_file_path TEXT, output_file_path TEXT,
                           track_count INTEGER, status TEXT NOT NULL);
                           """)
        print('Database with all tables initialized successfully.')
    except sqlite3.Error as e:
        print(f"Database initialisation failed: {e}")


@app.cli.command('drop-tables')
def drop_tables():
    """Drops all tables from the database."""
    try:
        with db_cursor() as cursor:
            print("Dropping all tables...")
            cursor.execute("DROP TABLE IF EXISTS track_tags")
            cursor.execute("DROP TABLE IF EXISTS tags")
            cursor.execute("DROP TABLE IF EXISTS tracks")
            cursor.execute("DROP TABLE IF EXISTS processing_log")
            print("All tables dropped successfully.")
    except sqlite3.Error as e:
        print(f"Failed to drop tables: {e}")

# --- EXTERNAL API FUNCTIONS ---

def insert_track_data(name, artist, bpm, track_key, genre, label, comments, grouping, tags_dict):
    """
    Inserts a track and its associated tags into the normalized database.
    - Adds the track to the 'tracks' table.
    - Adds each new tag to the 'tags' table.
    - Links the track and its tags in the 'track_tags' table.
    """
    try:
        with db_cursor() as cursor:
            # First, check for and insert the track, getting its ID
            cursor.execute("SELECT id FROM tracks WHERE name = ? AND artist = ?", (name, artist))
            if cursor.fetchone():
                print(f"Skipping duplicate track: {name} by {artist}")
                return
            # Convert the dictionary to a JSON string here, right before saving.
            tags_json_string = json.dumps(tags_dict)
            cursor.execute(
                "INSERT INTO tracks (name, artist, bpm, track_key, genre, label, comments, grouping, tags_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (name, artist, bpm, track_key, genre, label, comments, grouping, tags_json_string)
            )
            track_id = cursor.lastrowid
            print(f"Successfully inserted track: {name} by {artist} (ID: {track_id})")
            # Now, process and link the tags from the dictionary
            all_tags = set()
            for category in tags_dict.values():
                if isinstance(category, list):
                    all_tags.update(category)
                elif isinstance(category, str):
                    all_tags.add(category)
            for tag_name in all_tags:
                cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                tag_row = cursor.fetchone()
                tag_id = tag_row['id'] if tag_row else None
                if not tag_id:
                    cursor.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
                    tag_id = cursor.lastrowid
                cursor.execute("INSERT INTO track_tags (track_id, tag_id) VALUES (?, ?)", (track_id, tag_id))
            print(f"Successfully linked {len(all_tags)} tags for track ID {track_id}.")
    except sqlite3.Error as e:
        print(f"Database error: {e}")


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
        print(f"Failed to create log entry: {e}")
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
        print(f"Failed to update log entry:{e}")

def call_llm_for_tags(track_data, config, mode='full'):
    """
    Calls the OpenAI API to generate tags. Can operate in two modes:
    - 'full': Gets all tags (genres, energy, vibes, etc.).
    - 'genre_only': Gets only the primary and sub-genres for faster processing.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set. Using mock tags.")
        if mode == 'genre_only':
            return {"primary_genre": ["mock house"]}
        return {"primary_genre": ["mock techno"], "sub_genre": ["Minimal"], "energy_level": 7}

    # Dynamically build the prompt parts from our vocabulary
    primary_genre_list = ", ".join(CONTROLLED_VOCABULARY["primary_genre"])

    # Start with the core instructions that are the same for both modes.
    prompt_parts = [
        "You are an expert musicologist specializing in electronic dance music. Your mission is to provide structured, consistent tags for a DJ's library.",
        f"Here is the track data:\nTrack: '{track_data.get('ARTIST')} - {track_data.get('TITLE')}'",
        f"Existing Genre: {track_data.get('GENRE')}\nYear: {track_data.get('YEAR')}\n",
        "Please provide a JSON object with the following keys, following these specific instructions:",
        f"1. 'primary_genre': Choose EXACTLY ONE foundational genre from this list that best represents the track's core identity:\n   {primary_genre_list}",
        f"2. 'sub_genre': Using your expert knowledge, provide up to {config.get('sub_genre', 2)} specific and widely-recognized sub-genres for this track (e.g., 'French House'). Do not invent obscure genres."
    ]

    # If we are in 'full' mode, add the details instructions for all the other tags.
    if mode == 'full':
        components_list = ", ".join(CONTROLLED_VOCABULARY["components"])
        energy_vibe_list = ", ".join(CONTROLLED_VOCABULARY["energy_vibe"])
        situation_environment_list = ", ".join(CONTROLLED_VOCABULARY["situation_environment"])
        time_period_list = ", ".join(CONTROLLED_VOCABULARY["time_period"])

        full_mode_instructions = [
            "3. 'energy_level': Provide a single integer from 1 (lowest energy) to 10 (highest energy). Your rating MUST be calibrated for a DJ who plays electronic dance music.",
            "   - A '10/10' is for the most intense, peak-time festival anthems (e.g., hard techno, big room house).",
            "   - A '1/10' or '2/10' is for very low-energy tracks, such as ambient, downtempo, or chill-out music.",
            "   - IMPORTANT: Do not be afraid to use the 1, 2, or 3 ratings. Overrating a low-energy track is a significant error.",
            f"4. 'components': Identify up to {config.get('components', 3)} prominent musical elements from this list: {components_list}. Avoid generic terms like 'Synth'.",
            "5. For the remaining categories, choose up to the specified number of tags from their respective lists:",
            f"   - 'energy_vibe' (up to {config.get('energy_vibe', 2)}): {energy_vibe_list}",
            f"   - 'situation_environment' (up to {config.get('situation_environment', 2)}): {situation_environment_list}",
            f"   - 'time_period' (up to {config.get('time_period', 1)}): {time_period_list}"
        ]
        prompt_parts.extend(full_mode_instructions)

    prompt_parts.append("\nIMPORTANT: Your response MUST be a single, valid JSON object and nothing else.")
    prompt_text = "\n\n".join(prompt_parts)

    api_url = "https://api.openai.com/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt_text}],
        "response_format": {"type": "json_object"}
    }

    max_retries = 5
    initial_delay = 2
    for attempt in range(max_retries):
        try:
            response = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=30)
            response.raise_for_status()
            text_part = response.json().get("choices", [{}])[0].get("message", {}).get("content")
            if text_part:
                print(f"Successfully tagged (mode: {mode}): {track_data.get('ARTIST')} - {track_data.get('TITLE')}")
                json_response = json.loads(text_part)
                if isinstance(json_response.get('primary_genre'), str):
                    json_response['primary_genre'] = [json_response['primary_genre']]
                return json_response
        except requests.exceptions.RequestException as e:
            delay = initial_delay * (2 ** attempt)
            print(f"A network error occurred ('{type(e).__name__}'). Retrying in {delay} seconds...")
            time.sleep(delay)
        except json.JSONDecodeError as e:
            print(f"Error: Failed to decode JSON response from server. {e}")
            return {}

    print(f"Max retries exceeded for track: {track_data.get('ARTIST')} - {track_data.get('TITLE')}")
    return {}


def convert_energy_to_rating(energy_level):
    """Converts a 1-10 energy level to a Rekordbox 1-5 star rating value."""
    if not isinstance(energy_level, (int, float)):
        return 0
    if energy_level >= 9: return 255  # 5 Stars
    elif energy_level == 8: return 204  # 4 Stars
    elif energy_level >= 6: return 153  # 3 Stars
    elif energy_level >= 4: return 102  # 2 Stars
    else: return 51   # 1 Star

# In app.py -> --- EXTERNAL API FUNCTIONS ---

def get_genre_map_from_ai(genre_list):
    """
    Takes a list of specific genres and uses a single AI call to map them
    to the main genre buckets.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set. Cannot group genres.")
        # Return a map where every genre maps to Miscellaneous as a fallback.
        return {genre: "Miscellaneous" for genre in genre_list}

    main_buckets_str = ", ".join(MAIN_GENRE_BUCKETS)
    genres_to_map_str = ", ".join(f"'{g}'" for g in genre_list)

    prompt_text = (
        f"You are a master music librarian. Your only task is to categorize a list of specific music genres into a set of main departments. "
        f"The main departments are: [{main_buckets_str}].\n\n"
        f"Here is the list of genres to categorize: [{genres_to_map_str}].\n\n"
        f"Your response must be a single JSON object where each key is a specific genre from the list, and its value is the correct department name. "
        f"For example: {{\"Industrial Techno\": \"Electronic\", \"Indie Folk\": \"Rock\"}}"
    )

    api_url = "https://api.openai.com/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt_text}],
        "response_format": {"type": "json_object"}
    }

    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=20)
        response.raise_for_status()
        data = response.json()
        raw_content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if raw_content:
            genre_map = json.loads(raw_content)
            print("AI successfully generated the genre map.")
            return genre_map
    except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
        print(f"AI Grouper call failed: {e}")
        return {genre: "Miscellaneous" for genre in genre_list}

    return {genre: "Miscellaneous" for genre in genre_list}

# --- CORE LOGIC ---

def get_primary_genre(track_element):
    """
    Parses the Genre tag of a track to determine its primary genre.
    If the genre is missing or empty, it calls the main AI in 'genre_only' mode as a fallback.
    """
    genre_str = track_element.get('Genre', '').strip()
    primary_genre = None

    # First, try to parse an existing genre tag.
    if genre_str:
        parsed_genre = genre_str.split(',')[0].strip()
        if '/' in parsed_genre:
            parsed_genre = parsed_genre.split('/')[0].strip()
        # Only accept the parsed genre if it's not an empty string.
        if parsed_genre:
            primary_genre = parsed_genre

    if not primary_genre:
        print(
            f"No valid genre found for '{track_element.get('Artist')} - {track_element.get('Name')}'. Asking AI (genre_only mode)...")
        track_data = {
            'ARTIST': track_element.get('Artist'),
            'TITLE': track_element.get('Name'),
            'GENRE': track_element.get('Genre'),  # Pass along any messy genre data as a clue.
            'YEAR': track_element.get('Year')  # Pass along the year as a clue.
        }
        # Call ONE brain, but in its fast mode.
        ai_response = call_llm_for_tags(track_data, {}, mode='genre_only')

        if ai_response and ai_response.get('primary_genre'):
            # The AI returns a list, so take the first item.
            return ai_response['primary_genre'][0]
        else:
            return "Miscellaneous"  # Default if the AI fails.

        # Otherwise, return the genre found locally.
    return primary_genre


def split_xml_by_genre(input_path, job_folder_path):
    """
    Parses a Rekordbox XML, groups tracks by their specific genres, and then
    uses a dynamic AI call to group those into main "Genius" buckets before saving.
    """
    print(f"Starting to split file: {input_path} into {job_folder_path}")
    try:
        # Open the main XML file and get a list of all the tracks.
        original_tree = ET.parse(input_path)
        root = original_tree.getroot()
        tracks = root.find('COLLECTION').findall('TRACK')

        # Stage 1: Raw sort into individual genres.
        genre_groups = {}
        for track in tracks:
            primary_genre = get_primary_genre(track)
            if primary_genre not in genre_groups:
                genre_groups[primary_genre] = []
            # Add current track to correct group (Corrected indentation)
            genre_groups[primary_genre].append(track)

        print(f"Found raw genres: {list(genre_groups.keys())}")

        # Stage 2: Dynamic AI powered grouping.
        unique_genres = list(genre_groups.keys())
        # Call the AI once to get our dynamic "rulebook" for this specific run
        genre_map = get_genre_map_from_ai(unique_genres)
        print(f"AI Genre Map: {genre_map}")

        # Use the AI-generated map to group into main buckets
        main_genre_buckets = {}
        for genre, track_list in genre_groups.items():
            main_bucket_name = genre_map.get(genre, "Miscellaneous")
            if main_bucket_name not in main_genre_buckets:
                main_genre_buckets[main_bucket_name] = []
            # Add all tracks from the small pile into the big bucket
            main_genre_buckets[main_bucket_name].extend(track_list)

        print(f"Grouped into main buckets: {list(main_genre_buckets.keys())}")

        # FILE CREATION (using the final, grouped buckets)
        # Initialise empty list to keep log of file paths created
        created_files = []
        for bucket_name, track_list in main_genre_buckets.items():
            # Build new valid XML structure
            new_root = ET.Element('DJ_PLAYLISTS', attrib={'Version': '1.0.0'})
            # Add the standard <PRODUCT> information tag.
            ET.SubElement(new_root, 'PRODUCT', attrib={'Name': 'Tag Genius', 'Version': '1.0', 'Company': ''})
            # Create the main <COLLECTION>element, making sure to set the 'Entries' attribute.
            new_collection = ET.SubElement(new_root, 'COLLECTION', attrib={'Entries': str(len(track_list))})
            # Loop through all the <TRACK> elements belonging to this bucket...
            for track_element in track_list:
                # ...and append each one into the new <COLLECTION>. This perfectly copies
                # the original track data into the new file structure.
                new_collection.append(track_element)

            # Save new XML file.
            new_tree = ET.ElementTree(new_root)
            # Create a filename-safe version of the bucket name by replacing spaces
            # and slashes with underscores (e.g., "Hip Hop / Rap" becomes "Hip_Hop___Rap"). (Corrected typo)
            safe_bucket_name = bucket_name.replace(' ', '_').replace('/', '_')
            filename = f"{safe_bucket_name}.xml"
            # Combine the provided 'job_folder_path' with the new filename to get the full path
            # where the file should be saved (e.g., "outputs/job123/Electronic.xml").
            output_path = os.path.join(job_folder_path, filename)
            # Write the XML tree to the specified path. 'encoding="UTF-8"' and 'xml_declaration=True'
            # ensure the file is saved in the standard format expected by Rekordbox.
            new_tree.write(output_path, encoding='UTF-8', xml_declaration=True)
            # Add the path of the file just created to our list of results.
            created_files.append(output_path)
            # Log success message
            print(f"Created {filename} with {len(track_list)} tracks.")

        # Return list of all the new files created
        return created_files

    except ET.ParseError as e:
        print(f"Error parsing XML: {e}")
        # Re-raise the exception. This stops the function and signals to the calling code
        # (the Flask route) that something went wrong, allowing it to return a 500 error.
        raise

def clear_ai_tags(track_element):
    """
    Clears the specific metadata fields that are generated by Tag Genius.
    - Resets comments matching the AI format.
    - Resets color and grouping, preserving manual "Red" color.
    - Resets the star rating.
    """
    # 1. Clear Comments using a regular expression
    # This specifically looks for '/* ... */' and won't touch other comments.
    current_comments = track_element.get('Comments', '')
    cleaned_comments = re.sub(r'/\*.*?\*/', '', current_comments).strip()
    track_element.set('Comments', cleaned_comments)
    # 2. Clear Colour and Grouping
    # We must respect the "Red" override.
    if track_element.get('Colour') != '0xFF0000':
        if 'Colour' in track_element.attrib:
            del track_element.attrib['Colour']
        if 'Grouping' in track_element.attrib:
            del track_element.attrib['Grouping']
    # 3. Reset the star rating
    track_element.set('Rating', '0')
    return track_element


@celery.task
def process_library_task(input_path, output_path, config):
    """Orchestrates the entire tagging process, including clearing tags, colour-coding, and star ratings as a background Celery task."""
    original_filename = os.path.basename(input_path)
    log_id = log_job_start(original_filename, input_path)

    if not log_id:
        return {"error": "Failed to initialize logging for the job."}

    try:
        tree = ET.parse(input_path)
        root = tree.getroot()
        tracks = root.find('COLLECTION').findall('TRACK')
        total_tracks = len(tracks)
        print(f"Found {total_tracks} tracks. Starting processing...")

        for index, track in enumerate(tracks):
            track_name = track.get('Name')
            artist = track.get('Artist')
            print(f"\nProcessing track {index + 1}/{total_tracks}: {artist} - {track_name}")

            # Step 1: Clear existing AI tags if the user requested it.
            if config.get('clear_tags', False):
                clear_ai_tags(track)
                print(f"Cleared existing AI tags for: {track_name}")

            # Step 2: Only run the AI tagging process if a detail level is selected.
            if config.get('level') != 'None':
                track_data = {'ARTIST': artist, 'TITLE': track_name, 'GENRE': track.get('Genre'),
                              'YEAR': track.get('Year')}
                generated_tags = call_llm_for_tags(track_data, config)

                if not generated_tags:
                    print("Skipping tag update due to empty AI response.")
                    continue

                def ensure_list(value):
                    if isinstance(value, str): return [value]
                    if isinstance(value, list): return value
                    return []

                # Set Genre
                primary_genre = ensure_list(generated_tags.get('primary_genre'))
                sub_genre = ensure_list(generated_tags.get('sub_genre'))
                new_genre_string = ", ".join(primary_genre + sub_genre)
                track.set('Genre', new_genre_string)

                # Set Comments
                tag_order_and_prefixes = {
                    'situation_environment': 'Sit',
                    'energy_vibe': 'Vibe',
                    'components': 'Comp',
                    'time_period': 'Time'
                }
                formatted_parts = []

                energy_level = generated_tags.get('energy_level')
                if isinstance(energy_level, int):
                    energy_str = f"E: {str(energy_level).zfill(2)}"
                    formatted_parts.append(energy_str)

                for key, prefix in tag_order_and_prefixes.items():
                    tags = ensure_list(generated_tags.get(key))
                    if tags:
                        tag_string = ", ".join([tag.strip().capitalize() for tag in tags])
                        formatted_parts.append(f"{prefix}: {tag_string}")

                final_comments_content = ' / '.join(formatted_parts)
                final_comments = f"/* {final_comments_content} */" if final_comments_content else ""
                track.set('Comments', final_comments)

                # Set Colour based on Energy Level
                if track.get('Colour') == '0xFF0000':  # Red (User Override)
                    print("Track is marked as Red, skipping automatic color-coding.")
                else:
                    energy_level = generated_tags.get('energy_level')
                    track_colour_hex, track_colour_name = None, "None"

                    if isinstance(energy_level, int):
                        if energy_level >= 9:
                            track_colour_hex, track_colour_name = '0xFF007F', "Pink"
                        elif energy_level == 8:
                            track_colour_hex, track_colour_name = '0xFFA500', "Orange"
                        elif energy_level >= 6:
                            track_colour_hex, track_colour_name = '0xFFFF00', "Yellow"
                        elif energy_level >= 4:
                            track_colour_hex, track_colour_name = '0x00FF00', "Green"
                        else:  # Anything 3 or below
                            track_colour_hex, track_colour_name = '0x25FDE9', "Aqua"

                    if track_colour_hex:
                        track.set('Colour', track_colour_hex)
                        track.set('Grouping', track_colour_name)
                        print(f"Colour-coded track as {track_colour_name} based on energy: {energy_level}/10")
                    elif 'Colour' in track.attrib:
                        del track.attrib['Colour']

                # Set Star Rating
                energy_level = generated_tags.get('energy_level')
                if energy_level is not None:
                    rating_value = convert_energy_to_rating(energy_level)
                    track.set('Rating', str(rating_value))
                    print(f"Assigned star rating based on energy level: {energy_level}/10")

                print(f"Updated XML for: {track_name}")

                # Save to database
                insert_track_data(
                    track_name, artist, track.get('AverageBpm'), track.get('Tonality'),
                    new_genre_string, track.get('Label'), final_comments, track.get('Grouping'),
                    generated_tags
                )

            else:  # This runs if the user selected the "None" level
                print(f"Skipped AI tagging for: {track_name} (Level: None)")
                # Still save the track to the database, but with cleared/original values and no new tags
                insert_track_data(
                    track_name, artist, track.get('AverageBpm'), track.get('Tonality'),
                    track.get('Genre'), track.get('Label'), track.get('Comments'), track.get('Grouping'),
                    {}  # Pass an empty dictionary for the tags
                )

        tree.write(output_path, encoding='UTF-8', xml_declaration=True)
        log_job_end(log_id, 'Completed', total_tracks, output_path)
        print(f"\nProcessing complete! New file saved at: {output_path}")
        return {"message": "Success! Your new library file is ready.", "filePath": output_path}

    except Exception as e:
        log_job_end(log_id, 'Failed', 0, output_path)
        print(f"An error occurred during processing: {e}")
        return {"error": f"Failed to process XML: {e}"}


# --- FLASK ROUTES ---

@app.route('/')
def hello_ai():
    """A simple route to confirm the server is running."""
    return 'Hello, Ai!'


@app.route('/upload_library', methods=['POST'])
def upload_library():
    """Handles the XML file upload and sends the tagging processing job to the background worker"""
    global LATEST_XML_PATH
    if 'file' not in request.files: return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({"error": "No selected file"}), 400

    config_str = request.form.get('config')
    if not config_str: return jsonify({"error": "No config provided"}), 400
    try:
        config = json.loads(config_str)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid config format"}), 400

    if file:
        original_filename = file.filename
        name, ext = os.path.splitext(original_filename)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        unique_input_filename = f"{name}_{timestamp}{ext}"
        unique_output_filename = f"tagged_{name}_{timestamp}{ext}"
        upload_folder, output_folder = "uploads", "outputs"
        os.makedirs(upload_folder, exist_ok=True)
        os.makedirs(output_folder, exist_ok=True)
        input_path = os.path.join(upload_folder, unique_input_filename)
        output_path = os.path.join(output_folder, unique_output_filename)
        file.save(input_path)
        process_library_task.delay(input_path, output_path, config)
        LATEST_XML_PATH = output_path
        return jsonify({"message": "Success! Your library is now being processed in the background."}), 202
    return jsonify({"error": "Unknown error"}), 500


@app.route('/analyze_library', methods=['POST'])
def analyze_library():
    """
    Quickly scans an uploaded XML file to count how many tracks are missing a genre tag.
    This is a fast, local-only operation used to set user expectations.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file:
        try:
            file.seek(0)
            tree = ET.parse(file)
            root = tree.getroot()
            tracks = root.find('COLLECTION').findall('TRACK')
            untagged_count = 0
            for track in tracks:
                genre_str = track.get('Genre', '').strip()
                if not genre_str:
                    untagged_count += 1
            file.seek(0)
            return jsonify({"untagged_count": untagged_count}), 200
        except ET.ParseError as e:
            return jsonify({"error": f"Failed to parse XML: {e}"}), 500
    return jsonify({"error": "Unknown error"}), 500


@app.route('/split_library', methods=['POST'])
def split_library():
    """
    Handles XML file upload, creates a job folder, calls the splitter function,
    and returns a list of new files.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file:
        original_filename = file.filename
        name, ext = os.path.splitext(original_filename)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        job_folder_name = f"{timestamp}_{name}_split"
        job_folder_path = os.path.join("outputs", job_folder_name)
        os.makedirs(job_folder_path, exist_ok=True)
        input_path = os.path.join(job_folder_path, "original_library.xml")
        file.save(input_path)
        try:
            new_files = split_xml_by_genre(input_path, job_folder_path)
            return jsonify({
                "message": "Library split successfully!",
                "files": new_files,
                "job_folder": job_folder_path
            }), 200
        except Exception as e:
            return jsonify({"error": f"Failed to split library: {str(e)}"}), 500
    return jsonify({"error": "Unknown error"}), 500


@app.route('/download_split_file', methods=['GET'])
def download_split_file():
    """Safely serves a single split XML file for download."""
    file_path = request.args.get('path')
    if not file_path:
        return jsonify({"error": "File path is required"}), 400
    safe_base_path = os.path.abspath("outputs")
    requested_path = os.path.abspath(os.path.join(safe_base_path, file_path))
    if not requested_path.startswith(safe_base_path):
        return jsonify({"error": "Invalid file path"}), 403
    if os.path.exists(requested_path):
        return send_file(requested_path, as_attachment=True)
    else:
        return jsonify({"error": "File not found"}), 404


@app.route('/export_xml', methods=['GET'])
def export_xml():
    """Allows the user to download the most recently generated XML file."""
    global LATEST_XML_PATH
    if LATEST_XML_PATH and os.path.exists(LATEST_XML_PATH):
        return send_file(LATEST_XML_PATH, as_attachment=True)
    return jsonify({"error": "No file available to export"}), 404


@app.route('/history', methods=['GET'])
def get_history():
    """Retrieves the log of all past processing jobs."""
    try:
        with db_cursor() as cursor:
            logs = cursor.execute(
                "SELECT * FROM processing_log ORDER BY timestamp DESC"
            ).fetchall()
        history_list = [dict(row) for row in logs]
        return jsonify(history_list)
    except sqlite3.Error as e:
        print(f"Database error in get_history: {e}")
        return jsonify({"error": "Failed to retrieve history"}), 500


@app.route('/download_job/<int:job_id>', methods=['GET'])
def download_job_package(job_id):
    """
    Finds a job by its ID, zips up its input and output files,
    and sends them to the user as a downloadable package.
    """
    try:
        with db_cursor() as cursor:
            log_entry = cursor.execute(
                "SELECT input_file_path, output_file_path FROM processing_log WHERE id = ?",
                (job_id,)
            ).fetchone()

        if not log_entry or not log_entry['input_file_path'] or not log_entry['output_file_path']:
            return jsonify({"error": "Job or files not found"}), 404

        input_path = log_entry['input_file_path']
        output_path = log_entry['output_file_path']

        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w') as zf:
            zf.write(input_path, arcname='original_library.xml')
            zf.write(output_path, arcname='tagged_library.xml')
        memory_file.seek(0)
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'tag_genius_job_{job_id}.zip'
        )
    except Exception as e:
        print(f"Error creating zip package for job {job_id}: {e}")
        return jsonify({"error": "Failed to create download package"}), 500


# --- Standard CRUD routes for direct database management ---

@app.route('/tracks', methods=['GET'])
def get_tracks():
    """Retrieves all tracks from the local database."""
    try:
        with db_cursor() as cursor:
            tracks = cursor.execute('SELECT * FROM tracks').fetchall()
            tracks_list = [dict(row) for row in tracks]
            for track in tracks_list:
                if 'tags_json' in track and track['tags_json']:
                    try:
                        track['tags_json'] = json.loads(track['tags_json'])
                    except json.JSONDecodeError:
                        track['tags_json'] = {"error": "Invalid JSON"}
            return jsonify(tracks_list)
    except sqlite3.Error as e:
        print(f"Database error in get_tracks: {e}")
        return jsonify({"error": "Failed to retrieve tracks"}), 500


@app.route('/tracks', methods=['POST'])
def add_track():
    """Adds a new track to the database from a JSON payload."""
    data = request.get_json()
    name = data.get('name')
    artist = data.get('artist')
    if not name or not artist:
        return jsonify({"error": "Name and artist are required."}), 400
    try:
        with db_cursor() as cursor:
            cursor.execute(
                "INSERT INTO tracks (name, artist) VALUES (?, ?)", (name, artist)
            )
            return jsonify({"message": "Track added successfully."}), 201
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500


@app.route('/tracks/<int:track_id>', methods=['GET'])
def get_track(track_id):
    """Retrieves a single track by its ID from the local database."""
    try:
        with db_cursor() as cursor:
            track = cursor.execute(
                'SELECT * FROM tracks WHERE id = ?', (track_id,)).fetchone()
            if track is None: return jsonify({"error": "Track not found"}), 404
            track_dict = dict(track)
            if 'tags_json' in track_dict and track_dict['tags_json']:
                try:
                    track_dict['tags_json'] = json.loads(track_dict['tags_json'])
                except json.JSONDecodeError:
                    track_dict['tags_json'] = {"error": "Invalid JSON"}
            return jsonify(track_dict)
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 404


@app.route('/tracks/<int:track_id>', methods=['PUT'])
def update_track(track_id):
    """Updates an existing track by its unique ID."""
    data = request.get_json()
    name = data.get('name')
    artist = data.get('artist')
    if not name or not artist:
        return jsonify({"error": "Name and artist are required"}), 400

    try:
        with db_cursor() as cursor:
            if cursor.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone() is None:
                return jsonify({"error": "Track not found"}), 404
            cursor.execute(
                "UPDATE tracks SET name = ?, artist = ? WHERE id = ?", (name, artist, track_id)
            )
            return jsonify({"message": "Track updated successfully"}), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500


@app.route('/tracks/<int:track_id>', methods=['DELETE'])
def delete_track(track_id):
    """Deletes a single track by its unique ID."""
    try:
        with db_cursor() as cursor:
            if cursor.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone() is None:
                return jsonify({"error": "Track not found"}), 404
            cursor.execute(
                "DELETE FROM tracks WHERE id = ?", (track_id,)
            )
            return jsonify({"message": "Track deleted successfully"}), 200
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    # Runs the Flask development server on port 5001
    app.run(debug=True, port=5001)