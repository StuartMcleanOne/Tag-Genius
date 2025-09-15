import os
import sqlite3
import xml.etree.ElementTree as ET
import json
import requests
import time
from flask import Flask, jsonify, request, send_file # ADDED: send_file
from dotenv import load_dotenv
from flask_cors import CORS

load_dotenv()

app = Flask(__name__)
CORS(app)

# ADDED: A global variable to store the path of the last generated file
LATEST_XML_PATH = None

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
        # Quieter success message for cleaner logs
        # print(f"Successfully inserted: {name} by {artist}")
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
        print(f"Lexicon API call failed for {artist} - {name}: {e}")
        return {}


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
                return {}
        except requests.exceptions.RequestException as e:
            print(f"API call failed: {e}")
            return {}
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON from LLM response: {e}")
            return {}

    print(f"Max retries exceeded for track: {track_data.get('ARTIST')} - {track_data.get('TITLE')}")
    return {}


# --- Flask Routes ---
@app.route('/')
def hello_ai(): return 'Hello, Ai!'


@app.route('/upload_library', methods=['POST'])
def upload_library():
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
        upload_folder = "uploads"
        output_folder = "outputs"
        os.makedirs(upload_folder, exist_ok=True)
        os.makedirs(output_folder, exist_ok=True)

        input_path = os.path.join(upload_folder, file.filename)
        output_path = os.path.join(output_folder, f"tagged_{file.filename}")

        file.save(input_path)

        result = process_library(input_path, output_path, config)

        if "error" not in result:
            LATEST_XML_PATH = output_path  # Save the path for the export button

        return jsonify(result), 200

    return jsonify({"error": "Unknown error"}), 500


# MODIFIED: This is now the main event, writing the XML file
def process_library(input_path, output_path, config):
    try:
        tree = ET.parse(input_path)
        root = tree.getroot()
        tracks = root.find('COLLECTION').findall('TRACK')
        total_tracks = len(tracks)
        print(f"Found {total_tracks} tracks in the XML file. Starting processing...")

        for index, track in enumerate(tracks):
            track_name = track.get('Name')
            artist = track.get('Artist')

            print(f"\nProcessing track {index + 1}/{total_tracks}: {artist} - {track_name}")

            # 1. Get enriched data
            lexicon_data = call_lexicon_api(artist, track_name)
            track_data = {
                'ARTIST': artist, 'TITLE': track_name, 'GENRE': track.get('Genre'),
                'YEAR': track.get('Year'), 'lexicon_data': lexicon_data
            }

            # 2. Get AI tags
            generated_tags = call_llm_for_tags(track_data, config)
            if not generated_tags:
                print("Skipping tag update due to empty AI response.")
                continue

            # 3. Format tags for Rekordbox
            primary_genre = generated_tags.get('primary_genre', [])
            sub_genre = generated_tags.get('sub_genre', [])
            new_genre_string = ", ".join(primary_genre + sub_genre)

            other_tags = [
                *generated_tags.get('energy_vibe', []),
                *generated_tags.get('situation_environment', []),
                *generated_tags.get('components', []),
                *generated_tags.get('time_period', [])
            ]

            # Create the Rekordbox-formatted comment block
            new_comment_block = f"/* {' / '.join(tag for tag in other_tags if tag)} */"

            original_comments = track.get('Comments', "")

            # Non-destructively append our block
            final_comments = f"{original_comments} {new_comment_block}".strip()

            # 4. Modify the XML element in memory
            track.set('Genre', new_genre_string)
            track.set('Comments', final_comments)
            print(f"Updated XML for: {track_name}")

            # 5. (Optional) Save to DB for the API
            insert_track_data(
                track_name, artist, track.get('AverageBpm'), track.get('Tonality'),
                new_genre_string, track.get('Label'), final_comments, track.get('Grouping'),
                json.dumps(generated_tags)
            )

        # 6. Save the entire modified XML tree to the new file
        tree.write(output_path, encoding='UTF-8', xml_declaration=True)

        print(f"\nProcessing complete! New file saved at: {output_path}")
        return {"message": f"Success! Your new library file is ready.", "filePath": output_path}

    except Exception as e:
        print(f"An error occurred during processing: {e}")
        return {"error": f"Failed to process XML: {e}"}


# MODIFIED: The export route is now functional
@app.route('/export_xml', methods=['GET'])
def export_xml():
    global LATEST_XML_PATH
    if LATEST_XML_PATH and os.path.exists(LATEST_XML_PATH):
        try:
            return send_file(LATEST_XML_PATH, as_attachment=True)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "No file available to export"}), 404


# ... (You can add the /clear_tags route later if needed) ...

if __name__ == '__main__':
    app.run(debug=True, port=5001)