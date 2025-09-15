import os
import sqlite3
import xml.etree.ElementTree as ET
import json
import requests
import time
from flask import Flask, jsonify, request, send_file
from dotenv import load_dotenv
from flask_cors import CORS

# --- SETUP ---
# Load environment variables from a .env file
load_dotenv()
# Initialize the Flask application
app = Flask(__name__)
# Enable Cross-Origin Resource Sharing (CORS) to allow the front-end to communicate with the backend
CORS(app)
# Global variable to store the path of the last generated XML file for the export function
LATEST_XML_PATH = None

# --- CONSTANTS ---
# A predefined dictionary of tags to ensure the AI's output is consistent and predictable.
CONTROLLED_VOCABULARY = {
    "energy_vibe": ["upbeat", "energetic", "calm", "mellow", "dark", "uplifting", "groovy", "soulful"],
    "situation_environment": ["warmup", "peak time", "after-hours", "lounge", "club", "festival", "beach", "party"],
    "components": ["vocal", "instrumental", "synth", "bass", "piano", "percussion", "remix", "acapella"],
    "time_period": ["1980s", "1990s", "2000s", "2010s", "2020s"]
}


# --- DATABASE FUNCTIONS ---
def get_db_connection():
    """Establishes and returns a connection to the SQLite database."""
    conn = sqlite3.connect('tag_genius.db')
    conn.row_factory = sqlite3.Row
    return conn


@app.cli.command('init-db')
def init_db():
    """A Flask CLI command to initialize the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, artist TEXT,
            bpm REAL, track_key TEXT, genre TEXT, label TEXT, comments TEXT,
            grouping TEXT, tags TEXT
        );
    """)
    conn.commit()
    conn.close()
    print('Database initialized successfully.')


def insert_track_data(name, artist, bpm, track_key, genre, label, comments, grouping, tags):
    """Inserts a single track's metadata into the database, preventing duplicates."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM tracks WHERE name = ? AND artist = ?", (name, artist))
        if cursor.fetchone(): return
        cursor.execute(
            "INSERT INTO tracks (name, artist, bpm, track_key, genre, label, comments, grouping, tags) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, artist, bpm, track_key, genre, label, comments, grouping, tags)
        )
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error: {e}")
    finally:
        conn.close()


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


def call_llm_for_tags(track_data, config):
    """Calls the OpenAI API to generate tags, with a robust retry mechanism."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set. Using mock tags.")
        return {"primary_genre": ["mock techno"], "energy_vibe": ["mock_upbeat"]}

    vocab_prompt_part = "\n".join(
        f"- For '{key}', you MUST choose from this list: {', '.join(values)}"
        for key, values in CONTROLLED_VOCABULARY.items()
    )
    prompt_text = (
        f"You are a master music curator, 'Tag Genius.' Your mission is to provide concise, structured tags for a DJ's library. Here is the track:\n\n"
        f"Track: '{track_data.get('ARTIST')} - {track_data.get('TITLE')}'\n"
        f"Existing Genre: {track_data.get('GENRE')}\nYear: {track_data.get('YEAR')}\n\n"
        f"Provide a JSON object with these keys and up to the specified number of lowercase, string tags for each:\n"
        f"- primary_genre: {config.get('primary_genre', 1)}\n- sub_genre: {config.get('sub_genre', 1)}\n"
        f"{vocab_prompt_part}\n"
        f"Your choices for all categories except primary_genre and sub_genre must come from the lists provided. Respond with a valid JSON object only."
    )

    api_url = "https://api.openai.com/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {
        "model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt_text}],
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
                print(f"Successfully tagged: {track_data.get('ARTIST')} - {track_data.get('TITLE')}")
                return json.loads(text_part)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                delay = initial_delay * (2 ** attempt)
                print(f"Rate limit hit. Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                print(f"HTTP error occurred: {e}")
                return {}
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            print(f"An error occurred: {e}")
            return {}

    print(f"Max retries exceeded for track: {track_data.get('ARTIST')} - {track_data.get('TITLE')}")
    return {}


# --- CORE LOGIC ---
def process_library(input_path, output_path, config):
    """Orchestrates the entire tagging process from XML parsing to final XML writing."""
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

            primary_genre = ensure_list(generated_tags.get('primary_genre'))
            sub_genre = ensure_list(generated_tags.get('sub_genre'))
            new_genre_string = ", ".join(primary_genre + sub_genre)

            my_tag_categories = [
                ensure_list(generated_tags.get('energy_vibe')),
                ensure_list(generated_tags.get('situation_environment')),
                ensure_list(generated_tags.get('components')),
                ensure_list(generated_tags.get('time_period'))
            ]
            flat_my_tags = [tag for sublist in my_tag_categories for tag in sublist]
            hashtag_list = [f"#{tag.replace(' ', '_')}" for tag in flat_my_tags if tag]
            new_comment_block = " ".join(hashtag_list)
            original_comments = track.get('Comments', "")
            final_comments = f"{original_comments} {new_comment_block}".strip() if original_comments else new_comment_block

            track.set('Genre', new_genre_string)
            track.set('Comments', final_comments)
            print(f"Updated XML for: {track_name}")

            insert_track_data(
                track_name, artist, track.get('AverageBpm'), track.get('Tonality'),
                new_genre_string, track.get('Label'), final_comments, track.get('Grouping'),
                json.dumps(generated_tags)
            )

        tree.write(output_path, encoding='UTF-8', xml_declaration=True)
        print(f"\nProcessing complete! New file saved at: {output_path}")
        return {"message": "Success! Your new library file is ready.", "filePath": output_path}
    except Exception as e:
        print(f"An error occurred during processing: {e}")
        return {"error": f"Failed to process XML: {e}"}


# --- FLASK ROUTES ---
@app.route('/')
def hello_ai():
    """A simple route to confirm the server is running."""
    return 'Hello, Ai!'


@app.route('/upload_library', methods=['POST'])
def upload_library():
    """Handles the XML file upload and initiates the tagging process."""
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
        upload_folder, output_folder = "uploads", "outputs"
        os.makedirs(upload_folder, exist_ok=True);
        os.makedirs(output_folder, exist_ok=True)
        input_path = os.path.join(upload_folder, file.filename)
        output_path = os.path.join(output_folder, f"tagged_{file.filename}")
        file.save(input_path)
        result = process_library(input_path, output_path, config)
        if "error" not in result: LATEST_XML_PATH = output_path
        return jsonify(result), 200

    return jsonify({"error": "Unknown error"}), 500


@app.route('/export_xml', methods=['GET'])
def export_xml():
    """Allows the user to download the most recently generated XML file."""
    global LATEST_XML_PATH
    if LATEST_XML_PATH and os.path.exists(LATEST_XML_PATH):
        return send_file(LATEST_XML_PATH, as_attachment=True)
    return jsonify({"error": "No file available to export"}), 404


# --- Standard CRUD routes for direct database management ---
@app.route('/tracks', methods=['GET'])
def get_tracks():
    """Retrieves all tracks from the local database."""
    conn = get_db_connection()
    tracks = conn.execute('SELECT * FROM tracks').fetchall()
    conn.close()
    tracks_list = [dict(row) for row in tracks]
    for track in tracks_list:
        if track.get('tags'):
            try:
                track['tags'] = json.loads(track['tags'])
            except json.JSONDecodeError:
                track['tags'] = {"error": "Invalid JSON"}
    return jsonify(tracks_list)


@app.route('/tracks', methods=['POST'])
def add_track():
    """Adds a new track to the database from a JSON payload."""
    data = request.get_json()
    name = data.get('name')
    artist = data.get('artist')
    if not name or not artist:
        return jsonify({"error": "Name and artist are required."}), 400
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO tracks (name, artist) VALUES (?, ?)", (name, artist))
        conn.commit()
        return jsonify({"message": "Track added successfully."}), 201
    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route('/tracks/<int:track_id>', methods=['GET'])
def get_track(track_id):
    """Retrieves a single track by its ID from the local database."""
    conn = get_db_connection()
    track = conn.execute('SELECT * FROM tracks WHERE id = ?', (track_id,)).fetchone()
    conn.close()
    if track is None: return jsonify({"error": "Track not found"}), 404
    track_dict = dict(track)
    if track_dict.get('tags'):
        try:
            track_dict['tags'] = json.loads(track_dict['tags'])
        except json.JSONDecodeError:
            track_dict['tags'] = {"error": "Invalid JSON"}
    return jsonify(track_dict)


@app.route('/tracks/<int:track_id>', methods=['PUT'])
def update_track(track_id):
    """Updates an existing track by its unique ID."""
    data = request.get_json()
    name = data.get('name')
    artist = data.get('artist')
    if not name or not artist:
        return jsonify({"error": "Name and artist are required"}), 400
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM tracks WHERE id = ?", (track_id,))
        if cursor.fetchone() is None:
            return jsonify({"error": "Track not found"}), 404
        cursor.execute("UPDATE tracks SET name = ?, artist = ? WHERE id = ?", (name, artist, track_id))
        conn.commit()
        return jsonify({"message": "Track updated successfully"}), 200
    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route('/tracks/<int:track_id>', methods=['DELETE'])
def delete_track(track_id):
    """Deletes a single track by its unique ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM tracks WHERE id = ?", (track_id,))
        if cursor.fetchone() is None:
            return jsonify({"error": "Track not found"}), 404
        cursor.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
        conn.commit()
        return jsonify({"message": "Track deleted successfully"}), 200
    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


if __name__ == '__main__':
    # Runs the Flask development server on port 5001
    app.run(debug=True, port=5001)