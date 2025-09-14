import os
import sqlite3
import xml.etree.ElementTree as ET
import json
import requests
from flask import Flask, jsonify, request
from dotenv import load_dotenv
from flask_cors import CORS # ADDED: Import CORS

load_dotenv()

app = Flask(__name__)
CORS(app) # ADDED: Enable CORS for the entire application

# REMOVED: The global tag_limit variable is no longer needed.

def get_db_connection():
    """
    Establishes a connection to the SQLite database.
    """
    conn = sqlite3.connect('tag_genius.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.cli.command('init-db')
def init_db():
    """
    Initializes the database by creating the tracks table.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            artist TEXT,
            bpm REAL,
            track_key TEXT,
            genre TEXT,
            label TEXT,
            comments TEXT,
            grouping TEXT,
            tags TEXT
        );
    """)
    conn.commit()
    conn.close()
    print('Database initialized successfully.')

def insert_track_data(name, artist, bpm, track_key, genre, label, comments, grouping, tags):
    """
    Inserts a single track's metadata into the database.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM tracks WHERE name = ? AND artist = ?", (name, artist))
        existing_track = cursor.fetchone()
        if existing_track:
            print(f"Skipping duplicate track: {name} by {artist}")
            return
        cursor.execute("""
                       INSERT INTO tracks (name, artist, bpm, track_key, genre, label, comments, grouping, tags)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       """, (name, artist, bpm, track_key, genre, label, comments, grouping, tags))
        conn.commit()
        print(f"Successfully inserted: {name} by {artist}")
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error: {e}")
    finally:
        conn.close()

def call_lexicon_api(artist, name):
    """
    Calls the Lexicon Local API to get enriched track data.
    """
    api_url = 'http://localhost:48624/v1/search/tracks'
    try:
        params = { "filter": { "artist": artist, "title": name } }
        response = requests.get(api_url, json=params)
        response.raise_for_status()
        lexicon_data = response.json()
        tracks = lexicon_data.get('tracks', [])
        return tracks[0] if tracks else {}
    except requests.exceptions.RequestException as e:
        print(f"Lexicon API call failed: {e}")
        return {}

# MODIFIED: The function now accepts a 'config' dictionary
def call_llm_for_tags(track_data, config):
    """
    Calls an LLM to generate a structured set of tags for a music track.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY environment variable not set. Using mock tags.")
        # This mock response can be updated to reflect the new structure
        return {
            "primary_genre": ["techno"],
            "sub_genre": ["hard techno"],
            "energy_vibe": ["peak hour"],
            "situation_environment": ["main floor"],
            "components": ["vocal", "remix"],
            "time_period": ["2010s"]
        }

    # MODIFIED: The prompt is now dynamically built based on the config.
    # We will fully implement this logic in the next step. For now, we just accept the config.
    prompt_text = (
        f"You are a master music curator, 'Tag Genius.' Your mission is to provide concise, structured, "
        f"and expertly curated tags for a DJ's library. Here is the track:\n\n"
        f"Track: '{track_data.get('ARTIST')} - {track_data.get('TITLE')}'\n"
        f"Existing Genre: {track_data.get('GENRE')}\n"
        f"Year: {track_data.get('YEAR')}\n"
        f"Lexicon Data: {json.dumps(track_data.get('lexicon_data', {}))}\n\n"
        f"Based on the user's desired detail level, provide a specific number of tags for each category listed below. "
        f"Your task is to provide tags as a JSON object with these keys and tag counts:\n"
        f"- primary_genre: {config.get('primary_genre', 1)} tag(s)\n"
        f"- sub_genre: {config.get('sub_genre', 1)} tag(s)\n"
        f"- energy_vibe: {config.get('energy_vibe', 1)} tag(s)\n"
        f"- situation_environment: {config.get('situation_environment', 1)} tag(s)\n"
        f"- components: {config.get('components', 1)} tag(s)\n"
        f"- time_period: {config.get('time_period', 1)} tag(s)\n"
        f"Each key must map to a list of strings. Each tag should be concise and in lowercase. "
        f"Respond with a JSON object only, no additional text."
    )

    api_url = "https://api.openai.com/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt_text}],
        "response_format": {"type": "json_object"}
    }

    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        api_result = response.json()
        text_part = api_result.get("choices", [{}])[0].get("message", {}).get("content")
        if text_part:
            return json.loads(text_part)
        else:
            print("LLM response was not in the expected format.")
            return {}
    except requests.exceptions.RequestException as e:
        print(f"API call failed: {e}")
        return {}
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON from LLM response: {e}")
        return {}

# --- Standard API Routes (Mostly Unchanged) ---

@app.route('/')
def hello_ai():
    return 'Hello, Ai!'

@app.route('/tracks', methods=['GET'])
def get_tracks():
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

# ... (The other CRUD routes like POST, GET, DELETE, PUT for /tracks remain the same) ...

@app.route('/tracks', methods=['POST'])
def add_track():
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
    conn = get_db_connection()
    track = conn.execute('SELECT * FROM tracks WHERE id = ?', (track_id,)).fetchone()
    conn.close()
    if track is None:
        return jsonify({"error": "Track not found"}), 404
    track_dict = dict(track)
    if track_dict.get('tags'):
        try:
            track_dict['tags'] = json.loads(track_dict['tags'])
        except json.JSONDecodeError:
            track_dict['tags'] = {"error": "Invalid JSON"}
    return jsonify(track_dict)


@app.route('/tracks/<int:track_id>', methods=['DELETE'])
def delete_track(track_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM tracks WHERE id = ?", (track_id,))
        track = cursor.fetchone()
        if track is None:
            return jsonify({"error": "Track not found"}), 404
        cursor.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
        conn.commit()
        return jsonify({"message": "Track deleted successfully"}), 200
    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route('/tracks/<int:track_id>', methods=['PUT'])
def update_track(track_id):
    data = request.get_json()
    name = data.get('name')
    artist = data.get('artist')
    if not name or not artist:
        return jsonify({"error": "Name and artist are required"}), 400
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM tracks WHERE id = ?", (track_id,))
        track = cursor.fetchone()
        if track is None:
            return jsonify({"error": "Track not found"}), 404
        cursor.execute("UPDATE tracks SET name = ?, artist = ? WHERE id = ?",
                       (name, artist, track_id))
        conn.commit()
        return jsonify({"message": "Track updated successfully"}), 200
    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# REMOVED: The old /set_tag_limit route is no longer needed.

# --- Main Application Logic ---

@app.route('/upload_library', methods=['POST'])
def upload_library():
    """
    Handles the upload of a music library XML file and starts the parsing process.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # MODIFIED: Get the configuration from the form data
    config_str = request.form.get('config')
    if not config_str:
        return jsonify({"error": "No tagging configuration provided"}), 400

    try:
        config = json.loads(config_str)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid configuration format"}), 400

    if file:
        file_path = os.path.join("uploads", file.filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        file.save(file_path)

        # MODIFIED: Pass the config to the processing function
        processing_result = process_library(file_path, config)
        return jsonify(processing_result), 200

    return jsonify({"error": "An unknown error occurred"}), 500

# MODIFIED: The function now accepts a 'config' dictionary
def process_library(xml_path, config):
    """
    Parses the XML file, extracts track data, and inserts it into the database.
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        collection = root.find('COLLECTION')
        tracks = collection.findall('TRACK')
        print(f"Found {len(tracks)} tracks in the XML file.")

        for track in tracks:
            track_name = track.get('Name')
            artist = track.get('Artist')
            # ... (rest of the data extraction is the same)
            bpm = track.get('AverageBpm')
            track_key = track.get('Tonality')
            genre = track.get('Genre')
            label = track.get('Label')
            comments = track.get('Comments')
            grouping = track.get('Grouping')


            lexicon_data = call_lexicon_api(artist, track_name)
            track_data = {
                'ARTIST': artist,
                'TITLE': track_name,
                'GENRE': genre,
                'YEAR': track.get('Year'),
                'lexicon_data': lexicon_data
            }

            # MODIFIED: Pass the config to the LLM call
            generated_tags = call_llm_for_tags(track_data, config)
            tags_string = json.dumps(generated_tags)
            insert_track_data(track_name, artist, bpm, track_key, genre, label, comments, grouping, tags_string)

        # In the next step, we will add the logic here to write the modified XML back to a file.
        return {"message": f"{len(tracks)} tracks processed and saved to the database."}

    except Exception as e:
        return {"error": f"Failed to process XML: {e}"}


# ADDED: Placeholder routes for front-end functionality
@app.route('/export_xml', methods=['GET'])
def export_xml():
    # This will be implemented in a future step.
    return jsonify({"message": "Export functionality not yet implemented."}), 501

@app.route('/clear_tags', methods=['PUT'])
def clear_tags():
    # This will be implemented in a future step.
    return jsonify({"message": "Clear tags functionality not yet implemented."}), 501


if __name__ == '__main__':
    # MODIFIED: Changed port to 5001 to match the front-end's expectation
    app.run(debug=True, port=5001)