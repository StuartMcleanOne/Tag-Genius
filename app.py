import os
import sqlite3
import xml.etree.ElementTree as ET
import json
import requests
import time
import io
import zipfile
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

# --- CONSTANTS ---
CONTROLLED_VOCABULARY = {
    "primary_genre": [
        "House", "Techno", "Drum & Bass", "Breaks", "Trance", "Ambient/Downtempo",
        "Funk/Soul/Disco", "Hip Hop / Rap", "Reggae", "Jazz", "Blues", "Rock",
        "Pop", "Classical", "Latin", "Caribbean", "World", "Film/Theatrical"
    ],
    # sub_genre list is removed for AI "Guided Discovery"

    "components": [
        # Mix Types
        "Vocal", "Instrumental", "Acapella", "Remix", "Intro", "Extended", "Edit",
        # Specific Instruments
        "Piano", "Keys", "Guitar", "Strings", "Orchestral", "Saxophone", "Trumpet", "Wind", "Brass"
    ],
    "energy_vibe": [
        "Aggressive", "Calm", "Dark", "Driving", "Energetic", "Funky",
        "Happy", "Hypnotic", "Mellow", "Romantic", "Soulful", "Uplifting"
    ],
    # Timing or environments
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


# --- DATABASE FUNCTIONS ---

def get_db_connection():
    """Establishes and returns a connection to the SQLite database."""

    conn = sqlite3.connect('tag_genius.db')
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db_cursor():
    """ A context manager for handling database connections anc cursors. """

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 'yield' passes the cursor to the 'width' block.
        yield cursor
        # If everything in the 'with' block was successful, commit the changes.
        conn.commit()
    except sqlite3.Error as e:
        # If any database error occurs, roll back the changes.
        conn.rollback()
        # Re-raise the exception so we can still see the error in our logs.
        raise e
    finally:
        # The part always runs ensuring the connection is closed.
        conn.close()


@app.cli.command('init-db')
def init_db():
    """A Flask CLI command to initialize the database with all tables."""

    try:
        with db_cursor() as cursor:

            # Tracks Table.

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

            # Tags Table.

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

            # Track_tags Link Table.

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
                           ),
                               FOREIGN KEY
                           (
                               tag_id
                           ) REFERENCES tags
                           (
                               id
                           ),
                               PRIMARY KEY
                           (
                               track_id,
                               tag_id
                           )
                               );
                           """)

            # The  processing_log table for conversation history.

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
        print('Database with all tables initialized successfully.')
    except sqlite3.Error as e:
        print(f"Database initialisation failed: {e}")


@app.cli.command('drop-tables')
def drop_tables():
    """Drops all tables from the database."""
    try:
        with db_cursor() as cursor:
            print("Dropping all tables...")
            # Drop tables in reverse order of creation to respect foreign keys
            cursor.execute("DROP TABLE IF EXISTS track_tags")
            cursor.execute("DROP TABLE IF EXISTS tags")
            cursor.execute("DROP TABLE IF EXISTS tracks")
            cursor.execute("DROP TABLE IF EXISTS processing_log")
            # Add any other tables here in the future
            print("All tables dropped successfully.")
    except sqlite3.Error as e:
        print(f"Failed to drop tables: {e}")

# --- EXTERNAL API FUNCTIONS ---

def call_lexicon_api(artist, name):
    """Calls the local Lexicon DJ application API to get enriched track data."""

    api_url = 'http://localhost:48624/v1/search/tracks'
    try:
        params = {"filter": {"artist": artist, "title": name}}
        response = requests.get(api_url, json=params, timeout=10)
        response.raise_for_status()
        tracks = response.json().get('tracks', [])
        return tracks[0] if tracks else {}
    except requests.exceptions.RequestException as e:
        print(f"Lexicon API call failed for {artist} - {name}: {e}")
        return {}


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

            cursor.execute(
                "SELECT id FROM tracks WHERE name = ? AND artist = ?", (name, artist)
            )
            existing_track = cursor.fetchone()
            if existing_track:
                print(f"Skipping duplicate track: {name} by {artist}")
                return

            # MODIFIED: Convert the dictionary to a JSON string here, right before saving.

            tags_json_string = json.dumps(tags_dict)

            cursor.execute(
                "INSERT INTO tracks (name, artist, bpm, track_key, genre, label, comments, grouping, tags_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (name, artist, bpm, track_key, genre, label, comments, grouping, tags_json_string)
            )
            track_id = cursor.lastrowid
            print(f"Successfully inserted track: {name} by {artist} (ID: {track_id})")

            # Now, process and link the tags from the dictionary

            all_tags = set()

            # This loop will now work correctly because tags_dict is a dictionary

            for category in tags_dict.values():
                if isinstance(category, list):
                    for tag in category:
                        all_tags.add(tag)
                elif isinstance(category, str):
                    all_tags.add(category)

            for tag_name in all_tags:
                cursor.execute(
                    "SELECT id FROM tags WHERE name = ?", (tag_name,)
                )
                tag_row = cursor.fetchone()

                if tag_row:
                    tag_id = tag_row['id']
                else:
                    cursor.execute(
                        "INSERT INTO tags (name) VALUES (?)", (tag_name,)
                    )
                    tag_id = cursor.lastrowid

                    cursor.execute(
                        "INSERT INTO track_tags (track_id, tag_id) VALUES (?, ?)", (track_id, tag_id)
                    )

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
            log_id = cursor.lastrowid
            print(f"Start logging for job ID: {log_id}")
            return log_id
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
            print(f"Finished loggin for job ID: {log_id} with status: {status}")
    except sqlite3.Error as e:
        print(f"Failed to update log entry:{e}")


def call_llm_for_tags(track_data, config):
    """Calls the OpenAI API to generate tags, including a numerical energy level."""

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set. Using mock tags.")
        return {"primary_genre": ["mock techno"], "sub_genre": ["Minimal"], "energy_level": 7}

    # Dynamically build the prompt parts from our vocabulary
    primary_genre_list = ", ".join(CONTROLLED_VOCABULARY["primary_genre"])
    components_list = ", ".join(CONTROLLED_VOCABULARY["components"])
    energy_vibe_list = ", ".join(CONTROLLED_VOCABULARY["energy_vibe"])
    situation_environment_list = ", ".join(CONTROLLED_VOCABULARY["situation_environment"])
    time_period_list = ", ".join(CONTROLLED_VOCABULARY["time_period"])

    prompt_text = (
        f"You are an expert musicologist specializing in electronic dance music. Your mission is to provide structured, consistent tags for a DJ's library.\n\n"
        f"Here is the track data:\n"
        f"Track: '{track_data.get('ARTIST')} - {track_data.get('TITLE')}'\n"
        f"Existing Genre: {track_data.get('GENRE')}\nYear: {track_data.get('YEAR')}\n\n"
        f"Please provide a JSON object with the following keys, following these specific instructions:\n\n"
        f"1. 'primary_genre': Choose EXACTLY ONE foundational genre from this list that best represents the track's core identity:\n"
        f"   {primary_genre_list}\n\n"
        f"2. 'sub_genre': Using your expert knowledge, provide up to {config.get('sub_genre', 2)} specific and widely-recognized sub-genres for this track (e.g., 'French House', 'Liquid Drum & Bass'). Do not invent obscure genres.\n\n"
        f"3. 'energy_level': Provide a single integer from 1 (lowest energy) to 10 (highest energy). Your rating MUST be calibrated for a DJ who plays electronic dance music.\n"
        f"   - A '10/10' is for the most intense, peak-time festival anthems (e.g., hard techno, big room house).\n"
        f"   - A '1/10' or '2/10' is for very low-energy tracks, such as ambient, downtempo, or chill-out music suitable for the start of a warm-up set.\n"
        f"   - Be decisive and use the full 1-10 scale to show the difference between genres. A classic house track might be a '7' or '8', while a driving techno track could be a '9'.\n"
        f"   - IMPORTANT: Do not be afraid to use the 1, 2, or 3 ratings. Overrating a low-energy track is a significant error. If a track is ambient, chill, or very sparse, it should receive a low score.\n\n"
        f"4. 'components': Identify up to {config.get('components', 3)} prominent musical elements. Prioritize specific instruments or mix types from this list: {components_list}. If you identify a specific synthesizer or drum machine (e.g., 'TB-303', '808 Drums'), you are encouraged to use that term. Avoid overly generic terms like 'Synth' or 'Drums'.\n\n"
        f"5. For the remaining categories, choose up to the specified number of tags from their respective lists:\n"
        f"   - 'energy_vibe' (up to {config.get('energy_vibe', 2)}): {energy_vibe_list}\n"
        f"   - 'situation_environment' (up to {config.get('situation_environment', 2)}): {situation_environment_list}\n"
        f"   - 'time_period' (up to {config.get('time_period', 1)}): {time_period_list}\n\n"
        f"IMPORTANT: Your response MUST be a single, valid JSON object and nothing else."
    )

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
            response.raise_for_status()  # This will raise an HTTPError for bad responses (4xx or 5xx)

            text_part = response.json().get("choices", [{}])[0].get("message", {}).get("content")
            if text_part:
                print(f"Successfully tagged: {track_data.get('ARTIST')} - {track_data.get('TITLE')}")
                json_response = json.loads(text_part)
                if isinstance(json_response.get('primary_genre'), str):
                    json_response['primary_genre'] = [json_response['primary_genre']]
                return json_response

        except requests.exceptions.RequestException as e:
            delay = initial_delay * (2 ** attempt)
            print(f"A network error occurred ('{type(e).__name__}'). Retrying in {delay} seconds...")
            time.sleep(delay)

        except json.JSONDecodeError as e:
            # If the response is not valid JSON, retrying won't help. Fail immediately.
            print(f"Error: Failed to decode JSON response from server. {e}")
            return {}

    # This part is only reached if all retries in the loop fail
    print(f"Max retries exceeded for track: {track_data.get('ARTIST')} - {track_data.get('TITLE')}")
    return {}

    # This part is only reached if all retries in the loop fail
    print(f"Max retries exceeded for track: {track_data.get('ARTIST')} - {track_data.get('TITLE')}")
    return {}

    # This part is only reached if all retries in the loop fail
    print(f"Max retries exceeded for track: {track_data.get('ARTIST')} - {track_data.get('TITLE')}")
    return {}


def convert_energy_to_rating(energy_level):
    """Converts a 1-10 energy level to a Rekordbox 1-5 star rating value."""
    if not isinstance(energy_level, (int, float)):
        return 0  # Default to 0 stars if input is not a number

    if energy_level >= 9:
        return 255  # 5 Stars
    elif energy_level >= 7:
        return 204  # 4 Stars
    elif energy_level >= 4:
        return 153  # 3 Stars
    elif energy_level >= 2:
        return 102  # 2 Stars
    elif energy_level == 1:
        return 51  # 1 Star
    else:
        return 0  # 0 Stars


# --- CORE LOGIC ---

@celery.task
def process_library_task(input_path, output_path, config):
    """Orchestrates the entire tagging process, including colour-coding and star ratings as background celery task."""

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

            track_data = {'ARTIST': artist, 'TITLE': track_name, 'GENRE': track.get('Genre'), 'YEAR': track.get('Year')}
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
            # Define the desired order and prefixes for the tags.
            tag_order_and_prefixes = {
                'situation_environment': 'Sit',
                'energy_vibe': 'Vibe',
                'components': 'Comp',
                'time_period': 'Time'
            }

            formatted_parts = []
            for key, prefix in tag_order_and_prefixes.items():
                tags = ensure_list(generated_tags.get(key))
                if tags:
                    # Capitalize each tag and join them with a comma
                    tag_string = ", ".join([tag.strip().capitalize() for tag in tags])
                    formatted_parts.append(f"{prefix}: {tag_string}")

            # Join the formatted parts (e.g., "Sit: Peak Time / Vibe: Upbeat")
            final_comments_content = ' / '.join(formatted_parts)
            final_comments = f"/* {final_comments_content} */" if final_comments_content else ""
            track.set('Comments', final_comments)

            # Set Colour based on Energy Level

            # FIRST, check if the track is already manually set to Red.
            if track.get('Colour') == '0xFF0000':
                print("Track is marked as Red, skipping automatic color-coding.")
            else:
                # If the track is not red, proceed with our automatic logic.
                energy_level = generated_tags.get('energy_level')
                track_colour_hex = None
                track_colour_name = "None"

                if isinstance(energy_level, int):
                    if energy_level >= 9:
                        track_colour_hex = '0xFF0080'  # Pink (Hottest)
                        track_colour_name = "Pink"
                    elif energy_level >= 7:
                        track_colour_hex = '0xFFA500'  # Orange (Hot)
                        track_colour_name = "Orange"
                    elif energy_level >= 5:
                        track_colour_hex = '0xFFFF00'  # Yellow (Warm)
                        track_colour_name = "Yellow"
                    elif energy_level >= 3:
                        track_colour_hex = '0x00FF00'  # Green (Neutral)
                        track_colour_name = "Green"
                    elif energy_level >= 1:
                        track_colour_hex = '0x00FFFF'  # Aqua (Coldest)
                        track_colour_name = "Aqua"

                    if track_colour_hex:
                        track.set('Colour', track_colour_hex)
                        track.set('Grouping', track_colour_name)
                        print(f"Colour-coded track as {track_colour_name} based on energy: {energy_level}/10")
                    else:
                        # If no energy level or colour was determined, remove any old colour attribute
                        if 'Colour' in track.attrib:
                            del track.attrib['Colour']

            # ADDED: Logic for automatic star rating
            energy_level = generated_tags.get('energy_level')
            if energy_level is not None:
                rating_value = convert_energy_to_rating(energy_level)
                track.set('Rating', str(rating_value))  # Rating must be a string in XML
                print(f"Assigned star rating based on energy level: {energy_level}/10")

            print(f"Updated XML for: {track_name}")

            # Save to database
            insert_track_data(
                track_name, artist, track.get('AverageBpm'), track.get('Tonality'),
                new_genre_string, track.get('Label'), final_comments, track.get('Grouping'),
                generated_tags
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
        # Get original filename and split it into name and extension.
        original_filename = file.filename
        name, ext = os.path.splitext(original_filename)

        # Create a unique string (e.g., "20251002-124530")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        # Create the new unique filenames for the input and output files
        unique_input_filename = f"{name}_{timestamp}{ext}"
        unique_output_filename = f"tagged_{name}_{timestamp}{ext}"

        # Define the full paths for saving
        upload_folder, output_folder = "uploads", "outputs"
        os.makedirs(upload_folder, exist_ok=True)
        os.makedirs(output_folder, exist_ok=True)

        input_path = os.path.join(upload_folder, unique_input_filename)
        output_path = os.path.join(output_folder, unique_output_filename)

        # Save the uploaded file with its new unique file name
        file.save(input_path)

        # Pass the unique paths to the background task
        process_library_task.delay(input_path, output_path, config)

        LATEST_XML_PATH = output_path

        return jsonify({"message": "Success! Your library is now being processed in the background."}), 202

    return jsonify({"error": "Unknown error"}), 500


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
        # Convert the database rows to a list of dictionaries
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

        # Create an in-memory zip file

        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w') as zf:

            # Add the 'before' and 'after' files to the zip with clean names

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
                if track.get('tags'):
                    try:
                        track['tags'] = json.loads(track['tags'])
                    except json.JSONDecodeError:
                        track['tags'] = {"error": "Invalid JSON"}
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
            if track_dict.get('tags'):
                try:
                    track_dict['tags'] = json.loads(track_dict['tags'])
                except json.JSONDecodeError:
                    track_dict['tags'] = {"error": "Invalid JSON"}
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
            cursor.execute(
                "SELECT * FROM tracks WHERE id = ?", (track_id,)
            )
            if cursor.fetchone() is None:
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
            cursor.execute(
                "SELECT * FROM tracks WHERE id = ?", (track_id,)
            )
            if cursor.fetchone() is None:
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