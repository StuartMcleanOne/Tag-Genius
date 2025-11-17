import os
import psycopg
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
from datetime import datetime, timedelta

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

# --- CONSTANTS ---

# Predefined vocabulary for AI tag generation consistency
CONTROLLED_VOCABULARY = {
    "primary_genre": [
        "House", "Techno", "Drum & Bass", "Breaks", "Trance",
        "Ambient/Downtempo", "Funk/Soul/Disco", "Hip Hop / Rap", "R&B",
        "Reggae", "Jazz", "Blues", "Rock", "Pop", "Classical", "Latin",
        "Caribbean", "World", "Film/Theatrical"
    ],
    "components": [
        "Vocal", "Instrumental", "Acapella", "Remix", "Intro", "Extended",
        "Edit", "Piano", "Keys", "Guitar", "Strings", "Orchestral",
        "Saxophone", "Trumpet", "Wind", "Brass"
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
    "Electronic", "Hip Hop", "Rock", "Jazz-Funk-Soul", "World", "Pop",
    "Miscellaneous"
]

# Master Blueprint Configuration
MASTER_BLUEPRINT_CONFIG = {
    "level": "Detailed",
    "sub_genre": 3,
    "energy_vibe": 3,
    "situation_environment": 3,
    "components": 3,
    "time_period": 1
}


# --- DATABASE FUNCTIONS ---

def get_db_connection():
    """Establishes and returns a connection to the PostgreSQL database."""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    conn = psycopg.connect(database_url, row_factory=psycopg.rows.dict_row)
    return conn

@contextmanager
def db_cursor():
    """A context manager for handling database connections and cursors."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except psycopg.Error as e:
        conn.rollback()
        print(f"Database transaction failed:{e}")
        raise e
    finally:
        cursor.close()
        conn.close()

# @app.cli.command('init-db')
# def init_db():
#     """Initialize the database with all required tables."""
#     try:
#         with db_cursor() as cursor:
#             # Tracks Table
#             cursor.execute("""
#                 CREATE TABLE IF NOT EXISTS tracks (
#                     id INTEGER PRIMARY KEY AUTOINCREMENT,
#                     name TEXT NOT NULL,
#                     artist TEXT,
#                     bpm REAL,
#                     tonality TEXT,
#                     genre TEXT,
#                     label TEXT,
#                     comments TEXT,
#                     grouping TEXT,
#                     tags_json TEXT
#                 );
#             """)
#             # Tags Table
#             cursor.execute("""
#                 CREATE TABLE IF NOT EXISTS tags (
#                     id INTEGER PRIMARY KEY AUTOINCREMENT,
#                     name TEXT NOT NULL UNIQUE
#                 );
#             """)
#             # Track_tags Link Table
#             cursor.execute("""
#                 CREATE TABLE IF NOT EXISTS track_tags (
#                     track_id INTEGER,
#                     tag_id INTEGER,
#                     FOREIGN KEY (track_id) REFERENCES tracks (id)
#                         ON DELETE CASCADE,
#                     FOREIGN KEY (tag_id) REFERENCES tags (id)
#                         ON DELETE CASCADE,
#                     PRIMARY KEY (track_id, tag_id)
#                 );
#             """)
#             # Processing_log Table
#             cursor.execute("""
#                 CREATE TABLE IF NOT EXISTS processing_log (
#                     id INTEGER PRIMARY KEY AUTOINCREMENT,
#                     timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
#                     job_display_name TEXT,
#                     original_filename TEXT NOT NULL,
#                     input_file_path TEXT,
#                     output_file_path TEXT,
#                     track_count INTEGER,
#                     status TEXT NOT NULL,
#                     job_type TEXT NOT NULL,
#                     result_data TEXT
#                 );
#             """)
#             # User_actions Table
#             cursor.execute("""
#                 CREATE TABLE IF NOT EXISTS user_actions (
#                     id INTEGER PRIMARY KEY AUTOINCREMENT,
#                     timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
#                     action_description TEXT NOT NULL
#                 );
#             """)
#         print('Database with all tables initialized successfully.')
#     except psycopg.Error as e:
#         print(f"Database initialisation failed: {e}")
#
#
# @app.cli.command('drop-tables')
# def drop_tables():
#     """Drop all application tables from the database."""
#     try:
#         with db_cursor() as cursor:
#             print("Dropping all application tables...")
#             cursor.execute("DROP TABLE IF EXISTS track_tags")
#             cursor.execute("DROP TABLE IF EXISTS tags")
#             cursor.execute("DROP TABLE IF EXISTS tracks")
#             cursor.execute("DROP TABLE IF EXISTS processing_log")
#             cursor.execute("DROP TABLE IF EXISTS user_actions")
#             print("All application tables dropped successfully.")
#     except psycopg.Error as e:
#         print(f"Failed to drop tables: {e}")


def get_track_blueprint(name, artist):
    """Check database for existing track and return its blueprint."""
    try:
        with db_cursor() as cursor:
            cursor.execute(
                "SELECT tags_json FROM tracks WHERE name = %s AND artist = %s",
                (name, artist)
            )
            result = cursor.fetchone()

            if result and result['tags_json']:
                return json.loads(result['tags_json'])
    except (psycopg.Error, json.JSONDecodeError) as e:
        print(f"Error retrieving blueprint for {artist} - {name}: {e}")
    return None


def apply_user_config_to_tags(blueprint_tags, user_config):
    """Trim tag lists to match user's selected detail level."""
    rendered_tags = json.loads(json.dumps(blueprint_tags))

    list_keys_to_trim = [
        'sub_genre', 'components', 'energy_vibe',
        'situation_environment', 'time_period'
    ]

    for key in list_keys_to_trim:
        if key in rendered_tags and key in user_config:
            num_tags_to_keep = user_config[key]
            if isinstance(rendered_tags[key], list):
                rendered_tags[key] = rendered_tags[key][:num_tags_to_keep]

    return rendered_tags


# --- EXTERNAL API FUNCTIONS ---

def insert_track_data(name, artist, bpm, tonality, genre, label, comments,
                      grouping, tags_dict):
    """Insert or update track data and associated tags in database."""
    try:
        with db_cursor() as cursor:
            cursor.execute(
                "SELECT id FROM tracks WHERE name = %s AND artist = %s",
                (name, artist)
            )
            existing_track = cursor.fetchone()

            tags_json_string = (json.dumps(tags_dict)
                                if tags_dict is not None else None)

            if existing_track:
                track_id = existing_track['id']
                print(f"Updating existing track: {name} by {artist} "
                      f"(ID: {track_id})")

                if tags_json_string is not None:
                    cursor.execute(
                        """UPDATE tracks
                           SET bpm = %s, tonality = %s, genre = %s, label = %s,
                               comments = %s, grouping = %s, tags_json = %s
                           WHERE id = %s""",
                        (bpm, tonality, genre, label, comments, grouping,
                         tags_json_string, track_id)
                    )
                else:
                    cursor.execute(
                        """UPDATE tracks
                           SET bpm = %s, tonality = %s, genre = %s, label = %s,
                               comments = %s, grouping = %s
                           WHERE id = %s""",
                        (bpm, tonality, genre, label, comments, grouping,
                         track_id)
                    )
            else:
                print(f"Inserting new track: {name} by {artist}")
                cursor.execute(
                    """INSERT INTO tracks
                       (name, artist, bpm, tonality, genre, label, comments,
                        grouping, tags_json)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (name, artist, bpm, tonality, genre, label, comments,
                     grouping, tags_json_string)
                )
                track_id = cursor.lastrowid
                print(f"Successfully inserted track ID: {track_id}")

            # Process and link tags
            all_tags = set()
            if tags_dict:
                for category_value in tags_dict.values():
                    if isinstance(category_value, list):
                        all_tags.update(
                            t for t in category_value
                            if isinstance(t, str) and t.strip()
                        )
                    elif (isinstance(category_value, str) and
                          category_value.strip()):
                        all_tags.add(category_value.strip())

            # Insert tags and links
            tag_ids = []
            for tag_name in all_tags:
                cursor.execute(
                    "SELECT id FROM tags WHERE name = %s",
                    (tag_name,)
                )
                tag_row = cursor.fetchone()
                tag_id = tag_row['id'] if tag_row else None
                if not tag_id:
                    cursor.execute(
                        "INSERT INTO tags (name) VALUES (%s)",
                        (tag_name,)
                    )
                    tag_id = cursor.lastrowid
                tag_ids.append(tag_id)

            if tag_ids:
                values_to_insert = [(track_id, tag_id) for tag_id in tag_ids]
                cursor.executemany(
                    "INSERT INTO track_tags "
                    "(track_id, tag_id) VALUES (%s, %s) "
                    "ON CONFLICT DO NOTHING",
                    values_to_insert
                )

            print(f"Database record updated for track ID {track_id}.")

    except psycopg.Error as e:
        print(f"Database error in insert_track_data for "
              f"{artist} - {name}: {e}")


def log_job_start(filename, input_path, job_type, job_display_name):
    """Create a new entry in processing_log for a new job."""
    try:
        with db_cursor() as cursor:
            cursor.execute(
                "INSERT INTO processing_log "
                "(original_filename, input_file_path, status, job_type, "
                "job_display_name) VALUES (%s, %s, %s, %s, %s)",
                (filename, input_path, 'In Progress', job_type,
                 job_display_name)
            )
            return cursor.lastrowid
    except psycopg.Error as e:
        print(f"Failed to create log entry for {filename}: {e}")
        return None


def log_job_end(log_id, status, track_count, output_path):
    """Update log entry with final status of completed job."""
    try:
        with db_cursor() as cursor:
            cursor.execute(
                "UPDATE processing_log "
                "SET status = %s, track_count = %s, output_file_path = %s "
                "WHERE id = %s",
                (status, track_count, output_path, log_id)
            )
            print(f"Finished logging for job ID: {log_id} "
                  f"with status: {status}")
    except psycopg.Error as e:
        print(f"Failed to update log entry for job ID {log_id}: {e}")


def cleanup_stale_jobs():
    """
    Mark jobs stuck 'In Progress' for more than 2 hours as 'Failed'.

    This prevents zombie jobs from auto-resuming after server restarts
    while still allowing legitimate in-progress jobs to continue.

    Called automatically on app startup.
    """
    try:
        cutoff_time = datetime.now() - timedelta(hours=2)

        with db_cursor() as cursor:
            # Find stale jobs first (for logging)
            cursor.execute(
                "SELECT id, job_display_name FROM processing_log "
                        "WHERE status = 'In Progress' AND timestamp < %s",
                (cutoff_time,)
            )
            stale_jobs = cursor.fetchall()

            if stale_jobs:
                print(f"\n🧹 Cleaning up {len(stale_jobs)} stale job(s):")
                for job in stale_jobs:
                    print(f"   - Job {job['id']}: {job['job_display_name']}")

                # Mark them as failed
                cursor.execute("""
                               UPDATE processing_log
                               SET status = 'Failed'
                               WHERE status = 'In Progress'
                                 AND timestamp
                                   < %s
                               """, (cutoff_time,))
                print(f" Marked {len(stale_jobs)} stale job(s) as 'Failed'\n")
            else:
                print(" No stale jobs to clean up\n")

    except psycopg.Error as e:
        print(f"  Failed to clean up stale jobs: {e}\n")


def call_llm_for_tags(track_data, config, mode='full'):
    """Call OpenAI API to generate tags in 'full' or 'genre_only' mode."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set. Returning default mock tags.")
        return ({"primary_genre": ["Miscellaneous"], "sub_genre": []}
                if mode == 'genre_only'
                else {"primary_genre": ["mock techno"], "sub_genre": [],
                      "energy_level": 7})

    primary_genre_list = ", ".join(CONTROLLED_VOCABULARY["primary_genre"])
    artist = track_data.get('ARTIST', '')
    title = track_data.get('TITLE', '')
    sanitized_artist = re.sub(r'[^\w\s\-\(\)\'\".:,/]', '', artist)
    sanitized_title = re.sub(r'[^\w\s\-\(\)\'\".:,/]', '', title)

    prompt_parts = [
        "You are an expert musicologist specializing in electronic dance "
        "music. Provide structured tags for a DJ library.",
        f"Track Data:\nTrack: '{sanitized_artist} - {sanitized_title}'",
        f"Existing Genre: {track_data.get('GENRE')}\n"
        f"Year: {track_data.get('YEAR')}\n",
        "Provide a JSON object with these keys:",
        f"1. 'primary_genre': Choose EXACTLY ONE from: "
        f"[{primary_genre_list}]",
        f"2. 'sub_genre': Provide up to {config.get('sub_genre', 2)} "
        f"specific, widely-recognized sub-genres (e.g., 'French House')."
    ]

    if mode == 'full':
        components_list = ", ".join(CONTROLLED_VOCABULARY["components"])
        energy_vibe_list = ", ".join(CONTROLLED_VOCABULARY["energy_vibe"])
        situation_environment_list = ", ".join(
            CONTROLLED_VOCABULARY["situation_environment"]
        )
        time_period_list = ", ".join(CONTROLLED_VOCABULARY["time_period"])

        full_mode_instructions = [
            "3. 'energy_level': Integer 1-10, calibrated for electronic "
            "dance music DJs.",
            "   - Use 1-3 for low energy (ambient/chill). "
            "Do not overrate these.",
            "   - Use 9-10 only for peak-time anthems.",
            f"4. 'components': Identify up to {config.get('components', 3)} "
            f"prominent musical elements from this list: [{components_list}].",
            "   - IMPORTANT: Do NOT list common elements like 'Drums' or "
            "'Bass' unless they are the absolute main focus of the track.",
            "   - Focus on descriptive instruments like 'Piano', 'Strings', "
            "or 'Saxophone' that are useful for a DJ's search.",
            f"5. 'energy_vibe': Provide up to "
            f"{config.get('energy_vibe', 2)} from: [{energy_vibe_list}]",
            f"6. 'situation_environment': Provide up to "
            f"{config.get('situation_environment', 2)} from: "
            f"[{situation_environment_list}]",
            f"7. 'time_period': Provide up to "
            f"{config.get('time_period', 1)} from: [{time_period_list}]"
        ]

        prompt_parts.extend(full_mode_instructions)

    prompt_parts.append("\nResponse MUST be a single, valid JSON object.")
    prompt_text = "\n\n".join(prompt_parts)

    api_url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt_text}],
        "response_format": {"type": "json_object"},
        "temperature": 0
    }

    max_retries = 5
    initial_delay = 2
    for attempt in range(max_retries):
        try:
            timeout_seconds = 15 if mode == 'genre_only' else 30
            response = requests.post(
                api_url,
                headers=headers,
                data=json.dumps(payload),
                timeout=timeout_seconds
            )
            response.raise_for_status()

            text_part = (response.json()
                         .get("choices", [{}])[0]
                         .get("message", {})
                         .get("content"))
            if text_part:
                json_response = json.loads(text_part)

                if isinstance(json_response.get('primary_genre'), str):
                    json_response['primary_genre'] = [
                        json_response['primary_genre']
                    ]
                elif not isinstance(json_response.get('primary_genre'), list):
                    json_response['primary_genre'] = ["Miscellaneous"]

                primary_genre_for_log = (
                    json_response['primary_genre'][0]
                    if json_response['primary_genre'] else "N/A"
                )

                if mode == 'full':
                    print(f"Successfully tagged (mode: full): "
                          f"{artist} - {title}")
                else:
                    print(f"Successfully identified genre "
                          f"'{primary_genre_for_log}' for (mode: {mode}): "
                          f"{artist} - {title}")

                if mode == 'genre_only' and 'sub_genre' not in json_response:
                    json_response['sub_genre'] = []
                elif ('sub_genre' in json_response and
                      not isinstance(json_response['sub_genre'], list)):
                    json_response['sub_genre'] = []

                return json_response

        except requests.exceptions.RequestException as e:
            delay = initial_delay * (2 ** attempt)
            print(f"AI call failed for {artist} - {title} "
                  f"(mode: {mode}, error: {type(e).__name__}). "
                  f"Retrying in {delay} seconds...")
            time.sleep(delay)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON for {artist} - {title} "
                  f"(mode: {mode}): {e}")
            return ({"primary_genre": ["Miscellaneous"], "sub_genre": []}
                    if mode == 'genre_only'
                    else {"primary_genre": ["Miscellaneous"],
                          "sub_genre": [], "energy_level": None})

    print(f"Max retries exceeded for track: {artist} - {title} "
          f"(mode: {mode})")
    return ({"primary_genre": ["Miscellaneous"], "sub_genre": []}
            if mode == 'genre_only'
            else {"primary_genre": ["Miscellaneous"], "sub_genre": [],
                  "energy_level": None})


def convert_energy_to_rating(energy_level):
    """Convert 1-10 energy level to Rekordbox 1-5 star rating (0-255)."""
    if not isinstance(energy_level, (int, float)):
        return 0
    if energy_level >= 9:
        return 255
    elif energy_level == 8:
        return 204
    elif energy_level >= 6:
        return 153
    elif energy_level >= 4:
        return 102
    else:
        return 51


def get_genre_map_from_ai(genre_list):
    """Map specific genres to main genre buckets using AI."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set. Cannot group genres.")
        return {genre: "Miscellaneous" for genre in genre_list}

    if not genre_list:
        return {}

    main_buckets_str = ", ".join(MAIN_GENRE_BUCKETS)
    final_genre_map = {}
    batch_size = 10

    for i in range(0, len(genre_list), batch_size):
        batch = genre_list[i:i + batch_size]
        print(f"Processing genre batch {i // batch_size + 1}: {batch}")

        genres_to_map_str = ", ".join(
            f"'{re.sub(r'[^\w\s\-/]', '', g)}'" for g in batch
        )

        prompt_text = (
            f"You are a master music librarian. Categorize specific music "
            f"genres into main departments. "
            f"Main departments: [{main_buckets_str}].\n\n"
            f"Genres to categorize: [{genres_to_map_str}].\n\n"
            f"Respond with a single JSON object mapping each original genre "
            f"to its department. "
            f"Map unknown genres to 'Miscellaneous'. "
            f"Example: {{ \"Industrial Techno\": \"Electronic\", "
            f"\"Indie Folk\": \"Rock\" }}"
        )

        api_url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt_text}],
            "response_format": {"type": "json_object"}
        }

        max_retries = 5
        initial_delay = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    api_url,
                    headers=headers,
                    data=json.dumps(payload),
                    timeout=20
                )
                response.raise_for_status()
                data = response.json()
                raw_content = (data.get("choices", [{}])[0]
                               .get("message", {})
                               .get("content"))
                if raw_content:
                    genre_map_batch = json.loads(raw_content)
                    print(f"AI successfully processed batch. "
                          f"Result: {genre_map_batch}")

                    ai_map_lower = {
                        k.lower(): v for k, v in genre_map_batch.items()
                    }
                    validated_batch = {
                        g: ai_map_lower.get(g.lower(), "Miscellaneous")
                        for g in batch
                    }

                    final_genre_map.update(validated_batch)
                    break
            except requests.exceptions.RequestException as e:
                delay = initial_delay * (2 ** attempt)
                print(f"AI Grouper call failed for batch "
                      f"('{type(e).__name__}'). "
                      f"Retrying in {delay} seconds...")
                time.sleep(delay)
            except json.JSONDecodeError as e:
                print(f"AI Grouper call failed due to JSON error: {e}")
                break

        for genre in batch:
            if genre not in final_genre_map:
                final_genre_map[genre] = "Miscellaneous"

    print("Finished processing all genre batches.")
    return final_genre_map


# --- CORE LOGIC ---

def get_primary_genre(track_element):
    """Parse genre tag or use AI fallback to determine primary genre."""
    genre_str = track_element.get('Genre', '').strip()
    primary_genre = None

    if genre_str:
        parsed_genre = re.split(r'[,/]', genre_str)[0].strip()
        if parsed_genre:
            primary_genre = parsed_genre

    if not primary_genre:
        print(f"No valid genre found locally for "
              f"'{track_element.get('Artist')} - "
              f"{track_element.get('Name')}'. "
              f"Asking AI (genre_only mode)...")
        track_data = {
            'ARTIST': track_element.get('Artist'),
            'TITLE': track_element.get('Name'),
            'GENRE': track_element.get('Genre'),
            'YEAR': track_element.get('Year')
        }
        ai_response = call_llm_for_tags(track_data, {}, mode='genre_only')

        if (ai_response and isinstance(ai_response, dict) and
                isinstance(ai_response.get('primary_genre'), list) and
                ai_response['primary_genre']):
            primary_genre_from_ai = ai_response['primary_genre'][0]
            return (primary_genre_from_ai
                    if primary_genre_from_ai else "Miscellaneous")
        else:
            print(f"AI failed to provide valid primary genre for "
                  f"'{track_element.get('Artist')} - "
                  f"{track_element.get('Name')}'. "
                  f"Defaulting to Miscellaneous.")
            return "Miscellaneous"

    return primary_genre


def split_xml_by_genre(input_path, job_folder_path):
    """Parse Rekordbox XML, group tracks by genre, and save split files."""
    print(f"Starting split process for file: {input_path} "
          f"into folder: {job_folder_path}")
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

        # STAGE 1: RAW SORT
        genre_groups = {}
        print("Starting Stage 1: Determining primary genre for each track...")
        for i, track in enumerate(tracks):
            primary_genre = get_primary_genre(track)
            if primary_genre not in genre_groups:
                genre_groups[primary_genre] = []
            genre_groups[primary_genre].append(track)
            if (i + 1) % 50 == 0:
                print(f"Processed {i + 1}/{len(tracks)} tracks "
                      f"for initial genre sorting...")

        print(f"Finished Stage 1. Found raw genres: "
              f"{list(genre_groups.keys())}")

        # STAGE 2: DYNAMIC AI-POWERED GROUPING
        unique_genres = list(genre_groups.keys())
        if not unique_genres:
            print("No genres determined after Stage 1.")
            return []

        print("Starting Stage 2: Calling AI to group genres "
              "into main buckets...")
        genre_map = get_genre_map_from_ai(unique_genres)

        if "R&B" in genre_map:
            genre_map["R&B"] = "Hip Hop"

        print(f"AI Genre Map received: {genre_map}")

        main_genre_buckets = {}
        for genre, track_list in genre_groups.items():
            main_bucket_name = genre_map.get(genre, "Miscellaneous")
            if main_bucket_name not in main_genre_buckets:
                main_genre_buckets[main_bucket_name] = []
            main_genre_buckets[main_bucket_name].extend(track_list)

        print(f"Finished Stage 2. Grouped into main buckets: "
              f"{list(main_genre_buckets.keys())}")

        # FILE CREATION
        created_files = []
        print("Starting file creation...")
        for bucket_name, track_list in main_genre_buckets.items():
            if not track_list:
                continue

            new_root = ET.Element('DJ_PLAYLISTS',
                                  attrib={'Version': '1.0.0'})
            ET.SubElement(new_root, 'PRODUCT',
                          attrib={'Name': 'Tag Genius', 'Version': '1.0',
                                  'Company': ''})
            new_collection = ET.SubElement(
                new_root, 'COLLECTION',
                attrib={'Entries': str(len(track_list))}
            )
            for track_element in track_list:
                new_collection.append(track_element)

            new_tree = ET.ElementTree(new_root)
            safe_bucket_name = re.sub(r'[ /&]', '_', bucket_name)
            filename = f"{safe_bucket_name}.xml"
            output_path = os.path.join(job_folder_path, filename)

            try:
                new_tree.write(output_path, encoding='UTF-8',
                               xml_declaration=True)
                created_files.append(output_path)
                print(f"Successfully created {filename} "
                      f"with {len(track_list)} tracks.")
            except IOError as e:
                print(f"Error writing file {filename}: {e}")

        print(f"Finished file creation. {len(created_files)} files created.")
        return created_files

    except ET.ParseError as e:
        print(f"Fatal Error: Could not parse input XML file: {e}")
        raise
    except Exception as e:
        print(f"An unexpected error occurred during split_xml_by_genre: {e}")
        raise


def clear_ai_tags(track_element):
    """Clear AI-generated metadata fields from a track element."""
    current_comments = track_element.get('Comments', '')
    cleaned_comments = re.sub(r'/\*.*?\*/', '', current_comments).strip()
    track_element.set('Comments', cleaned_comments)
    if track_element.get('Colour') != '0xFF0000':
        if 'Colour' in track_element.attrib:
            del track_element.attrib['Colour']
        if 'Grouping' in track_element.attrib:
            del track_element.attrib['Grouping']
    track_element.set('Rating', '0')
    return track_element


@celery.task
def split_library_task(log_id, input_path, job_folder_path):
    """Celery task to orchestrate library splitting in background."""
    try:
        created_files = split_xml_by_genre(input_path, job_folder_path)

        outputs_base_path = os.path.abspath("outputs")
        relative_paths = [
            os.path.relpath(p, start=outputs_base_path)
            for p in created_files
        ]
        result_json = json.dumps(relative_paths)

        with db_cursor() as cursor:
            cursor.execute(
                "UPDATE processing_log "
                "SET status = %s, result_data = %s, track_count = %s "
                "WHERE id = %s",
                ('Completed', result_json, len(created_files), log_id)
            )
        print(f"Split job {log_id} completed successfully.")
        return {"message": "Split successful", "files": relative_paths}

    except Exception as e:
        print(f"FATAL error during split job {log_id}: {e}")
        with db_cursor() as cursor:
            cursor.execute(
                "UPDATE processing_log SET status = %s WHERE id = %s",
                ('Failed', log_id)
            )
        return {"error": str(e)}


@celery.task
def process_library_task(log_id, input_path, output_path, config):
    """Celery task to orchestrate full tagging process for XML file."""
    if not log_id:
        return {"error": "Failed to initialize logging for the job."}

    try:
        tree = ET.parse(input_path)
        root = tree.getroot()
        collection = root.find('COLLECTION')
        if collection is None:
            raise ValueError("COLLECTION element not found.")
        tracks = collection.findall('TRACK')
        total_tracks = len(tracks)
        print(f"Found {total_tracks} tracks. Starting tagging process...")

        processed_count = 0
        for index, track in enumerate(tracks):
            track_name = track.get('Name')
            artist = track.get('Artist')
            print(f"\nProcessing track {index + 1}/{total_tracks}: "
                  f"{artist} - {track_name}")

            # Handle "Clear Tags" Mode
            if config.get('level') == 'Clear':
                clear_ai_tags(track)
                print(f"Cleared existing AI tags for: {track_name}")
                insert_track_data(
                    track_name, artist, track.get('AverageBpm'),
                    track.get('Tonality'), track.get('Genre'),
                    track.get('Label'), track.get('Comments'),
                    track.get('Grouping'), None
                )
                processed_count += 1
                continue

            # Caching and Tagging Logic
            full_blueprint_tags = None

            # CACHE CHECK
            full_blueprint_tags = get_track_blueprint(track_name, artist)

            if full_blueprint_tags:
                print(f"CACHE HIT for: {track_name}. "
                      f"Using stored blueprint.")
            else:
                print(f"CACHE MISS for: {track_name}. "
                      f"Calling AI to create blueprint...")
                track_data = {
                    'ARTIST': artist,
                    'TITLE': track_name,
                    'GENRE': track.get('Genre'),
                    'YEAR': track.get('Year')
                }
                full_blueprint_tags = call_llm_for_tags(
                    track_data, MASTER_BLUEPRINT_CONFIG, mode='full'
                )

            # Validate blueprint
            if not full_blueprint_tags or not full_blueprint_tags.get(
                    'primary_genre'):
                print("Skipping tag update due to empty or invalid blueprint.")
                insert_track_data(
                    track_name, artist, track.get('AverageBpm'),
                    track.get('Tonality'), track.get('Genre'),
                    track.get('Label'), track.get('Comments'),
                    track.get('Grouping'), None
                )
                continue

            # DYNAMIC RENDERING
            tags_for_xml = apply_user_config_to_tags(
                full_blueprint_tags, config
            )

            clear_ai_tags(track)

            def ensure_list(value):
                if isinstance(value, str):
                    return [value]
                if isinstance(value, list):
                    return value
                return []

            # Update XML Element
            primary_genre = ensure_list(tags_for_xml.get('primary_genre'))
            sub_genre = ensure_list(tags_for_xml.get('sub_genre'))
            new_genre_string = ", ".join(
                g for g in primary_genre + sub_genre if g
            )
            track.set('Genre', new_genre_string if new_genre_string
                      else track.get('Genre', ''))

            # Format comments
            tag_order_and_prefixes = {
                'situation_environment': 'Sit',
                'energy_vibe': 'Vibe',
                'components': 'Comp',
                'time_period': 'Time'
            }
            formatted_parts = []
            energy_level = tags_for_xml.get('energy_level')
            if isinstance(energy_level, int):
                formatted_parts.append(f"E: {str(energy_level).zfill(2)}")
            for key, prefix in tag_order_and_prefixes.items():
                tags = ensure_list(tags_for_xml.get(key))
                if tags:
                    tag_string = ", ".join(
                        [t.strip().capitalize() for t in tags if t]
                    )
                    if tag_string:
                        formatted_parts.append(f"{prefix}: {tag_string}")
            final_comments_content = ' / '.join(formatted_parts)
            existing_comments = track.get('Comments', '').strip()
            new_comments = (f"/* {final_comments_content} */"
                            if final_comments_content else "")
            track.set('Comments',
                      f"{existing_comments} {new_comments}".strip())

            # Set Colour
            if track.get('Colour') != '0xFF0000':
                energy_level = tags_for_xml.get('energy_level')
                track_colour_hex, track_colour_name = None, None
                if isinstance(energy_level, int):
                    if energy_level >= 9:
                        track_colour_hex = '0xFF007F'
                        track_colour_name = "Pink"
                    elif energy_level == 8:
                        track_colour_hex = '0xFFA500'
                        track_colour_name = "Orange"
                    elif energy_level >= 6:
                        track_colour_hex = '0xFFFF00'
                        track_colour_name = "Yellow"
                    elif energy_level >= 4:
                        track_colour_hex = '0x00FF00'
                        track_colour_name = "Green"
                    else:
                        track_colour_hex = '0x25FDE9'
                        track_colour_name = "Aqua"
                if track_colour_hex:
                    track.set('Colour', track_colour_hex)
                    track.set('Grouping', track_colour_name)
                    print(f"Colour-coded track as {track_colour_name} "
                          f"based on energy: {energy_level}/10")
                else:
                    if 'Colour' in track.attrib:
                        del track.attrib['Colour']
                    if 'Grouping' in track.attrib:
                        del track.attrib['Grouping']

            # Set Star Rating
            energy_level = tags_for_xml.get('energy_level')
            rating_value = (convert_energy_to_rating(energy_level)
                            if energy_level is not None else 0)
            track.set('Rating', str(rating_value))
            print(f"Assigned star rating based on energy level: "
                  f"{energy_level}/10 -> {rating_value}")

            print(f"Updated XML for: {track_name}")

            # Count tags written to XML
            rendered_tags_set = set()
            for category_value in tags_for_xml.values():
                if isinstance(category_value, list):
                    rendered_tags_set.update(
                        t for t in category_value
                        if isinstance(t, str) and t.strip()
                    )
                elif isinstance(category_value, str) and category_value.strip():
                    rendered_tags_set.add(category_value.strip())
            print(f"Wrote {len(rendered_tags_set)} tags to XML "
                  f"for this track.")

            processed_count += 1

            # SAVE BLUEPRINT
            insert_track_data(
                track_name, artist, track.get('AverageBpm'),
                track.get('Tonality'),
                new_genre_string if new_genre_string
                else track.get('Genre', ''),
                track.get('Label'), track.get('Comments'),
                track.get('Grouping'), full_blueprint_tags
            )

        # Update COLLECTION entries count
        collection.set('Entries', str(len(collection.findall('TRACK'))))

        tree.write(output_path, encoding='UTF-8', xml_declaration=True)
        log_job_end(log_id, 'Completed', total_tracks, output_path)
        print(f"\nTagging process complete! {processed_count}/"
              f"{total_tracks} tracks processed. "
              f"New file saved at: {output_path}")
        return {
            "message": "Success! Your new library file is ready.",
            "filePath": output_path
        }

    except Exception as e:
        log_job_end(log_id, 'Failed', 0, output_path)
        print(f"FATAL error during tagging job {log_id}: {e}")
        return {"error": f"Failed to process XML: {str(e)}"}


# --- FLASK ROUTES ---

@app.route('/')
def hello_ai():
    """Confirm server is running."""
    return 'Hello, Tag Genius!'


@app.route('/upload_library', methods=['POST'])
def upload_library():
    """Handle XML upload and dispatch correct background task."""
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    config_str = request.form.get('config')
    if not config_str:
        return jsonify({"error": "No config provided"}), 400
    try:
        config = json.loads(config_str)
        if not isinstance(config, dict) or 'level' not in config:
            raise ValueError("Invalid config format")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Invalid config received: {config_str}, Error: {e}")
        return jsonify({"error": f"Invalid config format: {e}"}), 400

    if file:
        try:
            original_filename = file.filename
            name, ext = os.path.splitext(original_filename)

            now = datetime.now()
            timestamp = now.strftime("%Y%m%d-%H%M%S")
            selected_mode = config.get('level')

            if selected_mode == 'Split':
                job_folder_name = f"{timestamp}_{name}_split"
                job_folder_path = os.path.join("outputs", job_folder_name)
                os.makedirs(job_folder_path, exist_ok=True)

                input_path = os.path.join(job_folder_path,
                                          "original_library.xml")
                file.seek(0)
                file.save(input_path)

                human_readable_time = now.strftime("%b %d, %I:%M %p")
                job_display_name = (f"{name} - Split Job "
                                    f"({human_readable_time})")

                log_id = log_job_start(original_filename, input_path,
                                       'split', job_display_name)
                if not log_id:
                    return jsonify({
                        "error": "Failed to create a job log entry."
                    }), 500

                split_library_task.delay(log_id, input_path, job_folder_path)
                print(f"Split job dispatched with ID {log_id} "
                      f"for {original_filename}.")

                return jsonify({
                    "message": "Success! Your library is now being split "
                               "in the background.",
                    "job_id": log_id
                }), 202

            else:
                unique_input_filename = f"{name}_{timestamp}{ext}"
                unique_output_filename = f"tagged_{name}_{timestamp}{ext}"

                upload_folder, output_folder = "uploads", "outputs"
                os.makedirs(upload_folder, exist_ok=True)
                os.makedirs(output_folder, exist_ok=True)

                input_path = os.path.join(upload_folder,
                                          unique_input_filename)
                output_path = os.path.join(output_folder,
                                           unique_output_filename)

                file.seek(0)
                file.save(input_path)

                human_readable_time = now.strftime("%b %d, %I:%M %p")
                job_display_name = (f"{name} - Tagging Job "
                                    f"({selected_mode}) "
                                    f"({human_readable_time})")

                log_id = log_job_start(original_filename, input_path,
                                       'tagging', job_display_name)
                if not log_id:
                    return jsonify({
                        "error": "Failed to create a job log entry."
                    }), 500

                process_library_task.delay(log_id, input_path,
                                           output_path, config)

                print(f"Tagging job dispatched with ID {log_id} "
                      f"for {original_filename}.")

                return jsonify({
                    "message": "Success! Your library is now being "
                               "processed in the background.",
                    "job_id": log_id
                }), 202

        except Exception as e:
            print(f"Error during file save or task dispatch "
                  f"for {file.filename}: {e}")
            return jsonify({
                "error": "Failed to save file or start processing task."
            }), 500

    return jsonify({"error": "Unknown error during upload."}), 500


@app.route('/analyze_library', methods=['POST'])
def analyze_library():
    """Scan uploaded XML to count tracks missing genre tag."""
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file:
        try:
            file.seek(0)
            tree = ET.parse(file)
            root = tree.getroot()
            collection = root.find('COLLECTION')
            if collection is None:
                raise ValueError("COLLECTION element not found.")
            tracks = collection.findall('TRACK')

            untagged_count = 0
            for track in tracks:
                genre_str = track.get('Genre', '').strip()
                if not genre_str:
                    untagged_count += 1

            file.seek(0)
            print(f"Analyzed {file.filename}: "
                  f"Found {untagged_count} untagged tracks.")
            return jsonify({"untagged_count": untagged_count}), 200

        except ET.ParseError as e:
            print(f"XML Parse Error in analyze_library "
                  f"for {file.filename}: {e}")
            return jsonify({
                "error": "Failed to parse XML: Invalid format"
            }), 400
        except ValueError as e:
            print(f"XML Structure Error in analyze_library "
                  f"for {file.filename}: {e}")
            return jsonify({
                "error": f"Invalid XML Structure: {e}"
            }), 400
        except Exception as e:
            print(f"Unexpected error in analyze_library "
                  f"for {file.filename}: {e}")
            return jsonify({
                "error": "An unexpected error occurred during analysis."
            }), 500

    return jsonify({"error": "Unknown error during analysis."}), 500


@app.route('/tag_split_file', methods=['POST'])
def tag_split_file():
    """Dispatch tagging job for existing split file."""
    data = request.get_json()
    if not data or 'file_path' not in data or 'config' not in data:
        return jsonify({
            "error": "Missing file_path or config in request"
        }), 400

    relative_file_path = data['file_path']
    config = data['config']

    # Security Check
    safe_base_path = os.path.abspath("outputs")
    requested_path = os.path.abspath(
        os.path.join(safe_base_path, relative_file_path)
    )
    if (not requested_path.startswith(safe_base_path) or
            not os.path.exists(requested_path)):
        return jsonify({"error": "Invalid or non-existent file path"}), 404

    try:
        original_filename = os.path.basename(requested_path)
        name, ext = os.path.splitext(original_filename)
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d-%H%M%S")

        output_folder = "outputs"
        unique_output_filename = f"tagged_{name}_{timestamp}{ext}"
        output_path = os.path.join(output_folder, unique_output_filename)

        input_path = requested_path

        human_readable_time = now.strftime("%b %d, %I:%M %p")
        detail_level = config.get('level', 'Unknown')
        job_display_name = (f"{name} - Tagging Job ({detail_level}) "
                            f"({human_readable_time})")

        log_id = log_job_start(original_filename, input_path,
                               'tagging', job_display_name)
        if not log_id:
            return jsonify({
                "error": "Failed to create a job log entry."
            }), 500

        process_library_task.delay(log_id, input_path, output_path, config)

        print(f"Tagging job for split file dispatched with ID {log_id}.")

        return jsonify({
            "message": f"Tagging job for {original_filename} started.",
            "job_id": log_id
        }), 202

    except Exception as e:
        print(f"Error dispatching tag job for split file: {e}")
        return jsonify({
            "error": "Failed to start tagging task for the specified file."
        }), 500


@app.route('/download_split_file', methods=['GET'])
def download_split_file():
    """Serve single split XML file for download with security checks."""
    relative_file_path = request.args.get('path')
    if not relative_file_path:
        return jsonify({
            "error": "File path parameter 'path' is required"
        }), 400

    print(f"\n--- DOWNLOAD DEBUG ---")
    print(f"1. Received raw path from browser: '{relative_file_path}'")

    relative_file_path = os.path.normpath(relative_file_path).lstrip('./\\')
    if '..' in relative_file_path.split(os.path.sep):
        print(f"Attempted directory traversal detected: "
              f"{relative_file_path}")
        return jsonify({
            "error": "Invalid file path (Traversal attempt)"
        }), 400

    print(f"2. Normalized path: '{relative_file_path}'")

    safe_base_path = os.path.abspath("outputs")
    requested_path = os.path.join(safe_base_path, relative_file_path)

    print(f"3. Constructed absolute path to check: '{requested_path}'")

    if not os.path.abspath(requested_path).startswith(safe_base_path):
        print(f"SECURITY VIOLATION: Path resolved outside base directory: "
              f"{requested_path}")
        return jsonify({
            "error": "Invalid file path (Security violation)"
        }), 403

    if os.path.exists(requested_path) and os.path.isfile(requested_path):
        print(f"4. SUCCESS: File found. Serving for download.")
        print(f"--- END DEBUG ---\n")
        return send_file(requested_path, as_attachment=True)
    else:
        print(f"4. FAILED: File not found at the constructed path.")
        print(f"--- END DEBUG ---\n")
        return jsonify({"error": "Requested file not found"}), 404


@app.route('/download_job/<int:job_id>', methods=['GET'])
def download_job_package(job_id):
    """Zip job files and send archive for download."""
    input_path, output_path = None, None
    original_filename = f"job_{job_id}_files"
    try:
        with db_cursor() as cursor:
            cursor.execute(
                "SELECT original_filename, input_file_path, "
                "output_file_path FROM processing_log WHERE id = %s",
                (job_id,)
            )
            log_entry = cursor.fetchone()

        if not log_entry:
            return jsonify({"error": f"Job ID {job_id} not found"}), 404

        input_path = log_entry['input_file_path']
        output_path = log_entry['output_file_path']
        original_filename = os.path.splitext(
            log_entry['original_filename']
        )[0]

        if not input_path or not os.path.exists(input_path):
            return jsonify({
                "error": f"Original input file missing for job {job_id}."
            }), 404
        if not output_path or not os.path.exists(output_path):
            return jsonify({
                "error": f"Tagged output file missing for job {job_id}."
            }), 404

        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w',
                             zipfile.ZIP_DEFLATED) as zf:
            zf.write(input_path,
                     arcname=f'original_{os.path.basename(input_path)}')
            zf.write(output_path,
                     arcname=f'tagged_{os.path.basename(output_path)}')
        memory_file.seek(0)

        print(f"Prepared archive for job {job_id}")
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=(f'tag_genius_job_{job_id}_'
                           f'{original_filename}_archive.zip')
        )
    except psycopg.Error as e:
        print(f"Database error finding job {job_id}: {e}")
        return jsonify({
            "error": "Database error retrieving job details."
        }), 500
    except FileNotFoundError:
        missing = (input_path if not os.path.exists(input_path)
                   else output_path)
        print(f"File not found during zipping for job {job_id}: {missing}")
        return jsonify({"error": "Archive file(s) missing on server."}), 404
    except Exception as e:
        print(f"Error creating zip package for job {job_id}: {e}")
        return jsonify({"error": "Failed to create download package."}), 500


@app.route('/export_xml', methods=['GET'])
def export_xml():
    """Download most recently generated tagged XML file."""
    try:
        with db_cursor() as cursor:
            log_entry = cursor.execute(
                "SELECT output_file_path FROM processing_log "
                "WHERE status = 'Completed' AND job_type = 'tagging' "
                "ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()

        if not log_entry:
            print("Export request failed: No completed tagging job "
                  "found in database.")
            return jsonify({
                "error": "No tagged file available to export."
            }), 404

        latest_xml_path = log_entry['output_file_path']

        if (latest_xml_path and os.path.exists(latest_xml_path) and
                os.path.isfile(latest_xml_path)):
            print(f"Exporting latest tagged file from DB: "
                  f"{latest_xml_path}")
            return send_file(latest_xml_path, as_attachment=True)
        else:
            print(f"Export request failed: File not found at path: "
                  f"{latest_xml_path}")
            return jsonify({
                "error": "Tagged file path found in DB, but file "
                         "missing on server."
            }), 404

    except psycopg.Error as e:
        print(f"Database error during export lookup: {e}")
        return jsonify({
            "error": "Database error retrieving file path."
        }), 500


@app.route('/history', methods=['GET'])
def get_history():
    """Retrieve log of all past jobs."""
    try:
        with db_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM processing_log ORDER BY timestamp DESC"
            )
            logs = cursor.fetchall()
        history_list = [dict(row) for row in logs]
        return jsonify(history_list)
    except psycopg.Error as e:
        print(f"Database error in get_history: {e}")
        return jsonify({"error": "Failed to retrieve job history"}), 500


@app.route('/log_action', methods=['POST'])
def log_action():
    """Receive and log action description from frontend."""
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    description = data.get('action_description')
    if not description or not isinstance(description, str):
        return jsonify({
            "error": "Valid 'action_description' string is required"
        }), 400

    try:
        with db_cursor() as cursor:
            cursor.execute(
                "INSERT INTO user_actions (action_description) VALUES (%s)",
                (description,)
            )
        return jsonify({"message": "Action logged successfully"}), 201
    except psycopg.Error as e:
        print(f"Database error logging action: {description} - {e}")
        return jsonify({
            "error": "Failed to log action due to database error"
        }), 500


@app.route('/get_actions', methods=['GET'])
def get_actions():
    """Retrieve all logged user actions."""
    try:
        with db_cursor() as cursor:
            cursor.execute(
                "SELECT timestamp, action_description FROM user_actions "
                "ORDER BY timestamp DESC"
            )
            actions = cursor.fetchall()
        action_list = [
            {
                "timestamp": row['timestamp'],
                "description": row['action_description']
            }
            for row in actions
        ]
        return jsonify(action_list)
    except psycopg.Error as e:
        print(f"Database error retrieving actions: {e}")
        return jsonify({
            "error": "Failed to retrieve actions due to database error"
        }), 500


# --- Main Execution Guard ---
if __name__ == '__main__':
    cleanup_stale_jobs()
    print("Starting Flask development server on http://127.0.0.1:5001")
    app.run(host='0.0.0.0', port=5001, debug=True)