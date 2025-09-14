import os
import sqlite3
import xml.etree.ElementTree as ET
import json
import requests
import time
from flask import Flask, jsonify, request
from dotenv import load_dotenv
from flask_cors import CORS

load_dotenv()

app = Flask(__name__)
CORS(app)


# --- Database Functions (Unchanged) ---
def get_db_connection():
    conn = sqlite3.connect('tag_genius.db')
    conn.row_factory = sqlite3.Row
    return conn


@app.cli.command('init-db')
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
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
                       tags
                       TEXT
                   );
                   """)
    conn.commit()
    conn.close()
    print('Database initialized successfully.')


def insert_track_data(name, artist, bpm, track_key, genre, label, comments, grouping, tags):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM tracks WHERE name = ? AND artist = ?", (name, artist))
        if cursor.fetchone():
            print(f"Skipping duplicate track: {name} by {artist}")
            return
        cursor.execute(
            "INSERT INTO tracks (name, artist, bpm, track_key, genre, label, comments, grouping, tags) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, artist, bpm, track_key, genre, label, comments, grouping, tags)
        )
        conn.commit()
        print(f"Successfully inserted: {name} by {artist}")
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error: {e}")
    finally:
        conn.close()


# --- External API Functions ---
def call_lexicon_api(artist, name):
    api_url = 'http://localhost:48624/v1/search/tracks'
    try:
        params = {"filter": {"artist": artist, "title": name}}
        response = requests.get(api_url, json=params)
        response.raise_for_status()
        tracks = response.json().get('tracks', [])
        return tracks[0] if tracks else {}
    except requests.exceptions.RequestException as e:
        print(f"Lexicon API call failed: {e}")
        return {}


# MODIFIED: This function now includes a robust retry mechanism
def call_llm_for_tags(track_data, config):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set. Using mock tags.")
        return {"primary_genre": ["mock techno"]}

    prompt_text = (
        f"You are a master music curator, 'Tag Genius.' Your mission is to provide concise, structured tags for a DJ's library. Here is the track:\n\n"
        f"Track: '{track_data.get('ARTIST')} - {track_data.get('TITLE')}'\n"
        f"Existing Genre: {track_data.get('GENRE')}\nYear: {track_data.get('YEAR')}\n\n"
        f"Provide a JSON object with these keys and up to the specified number of lowercase, string tags for each:\n"
        f"- primary_genre: {config.get('primary_genre', 1)}\n- sub_genre: {config.get('sub_genre', 1)}\n"
        f"- energy_vibe: {config.get('energy_vibe', 1)}\n- situation_environment: {config.get('situation_environment', 1)}\n"
        f"- components: {config.get('components', 1)}\n- time_period: {config.get('time_period', 1)}\n"
        f"Respond with a valid JSON object only."
    )

    api_url = "https://api.openai.com/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {
        "model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt_text}],
        "response_format": {"type": "json_object"}
    }

    # Exponential backoff logic
    max_retries = 5
    initial_delay = 2  # start with a 2-second delay
    for attempt in range(max_retries):
        try:
            response = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=30)
            response.raise_for_status()  # This will raise an exception for 4xx or 5xx status codes
            text_part = response.json().get("choices", [{}])[0].get("message", {}).get("content")
            if text_part:
                return json.loads(text_part)
            else:
                print("LLM response was empty or malformed.")
                return {}
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                delay = initial_delay * (2 ** attempt)
                print(f"Rate limit hit. Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                print(f"HTTP error occurred: {e}")
                return {}  # Fail on other HTTP errors
        except requests.exceptions.RequestException as e:
            print(f"API call failed: {e}")
            return {}
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON from LLM response: {e}")
            return {}

    print("Max retries exceeded. Moving to the next track.")
    return {}


# ... (The CRUD routes for /tracks are unchanged) ...

@app.route('/')
def hello_ai(): return 'Hello, Ai!'


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


@app.route('/upload_library', methods=['POST'])
def upload_library():
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
        file_path = os.path.join("uploads", file.filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        file.save(file_path)
        result = process_library(file_path, config)
        return jsonify(result), 200

    return jsonify({"error": "Unknown error"}), 500


def process_library(xml_path, config):
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        tracks = root.find('COLLECTION').findall('TRACK')
        print(f"Found {len(tracks)} tracks in the XML file.")

        for track in tracks:
            track_name = track.get('Name')
            artist = track.get('Artist')
            # ... (extract other data)
            bpm = track.get('AverageBpm')
            track_key = track.get('Tonality')
            genre = track.get('Genre')
            label = track.get('Label')
            comments = track.get('Comments')
            grouping = track.get('Grouping')

            lexicon_data = call_lexicon_api(artist, track_name)
            track_data = {
                'ARTIST': artist, 'TITLE': track_name, 'GENRE': genre,
                'YEAR': track.get('Year'), 'lexicon_data': lexicon_data
            }

            # REMOVED: The simple time.sleep(1) is no longer needed here.
            # The retry logic in call_llm_for_tags handles timing automatically.

            generated_tags = call_llm_for_tags(track_data, config)
            tags_string = json.dumps(generated_tags)
            insert_track_data(track_name, artist, bpm, track_key, genre, label, comments, grouping, tags_string)

        return {"message": f"{len(tracks)} tracks processed and saved to the database."}
    except Exception as e:
        return {"error": f"Failed to process XML: {e}"}


@app.route('/export_xml', methods=['GET'])
def export_xml():
    return jsonify({"message": "Export functionality not yet implemented."}), 501


@app.route('/clear_tags', methods=['PUT'])
def clear_tags():
    return jsonify({"message": "Clear tags functionality not yet implemented."}), 501


if __name__ == '__main__':
    app.run(debug=True, port=5001)