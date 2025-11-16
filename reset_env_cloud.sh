#!/bin/bash

# Exit immediately if a command fails
set -e

echo "--- Checking for Docker... ---"
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running. Please start Docker Desktop and try again."
    exit 1
fi

echo "--- Stopping and removing old services... ---"
docker stop tag-genius-redis || true
docker rm tag-genius-redis || true

echo "--- Resetting the CLOUD database... ---"
echo "⚠️  WARNING: This will delete ALL data in your Supabase database!"
read -p "Are you sure you want to continue? (yes/no): " confirm

if [ "$confirm" = "yes" ]; then
    echo "Dropping and recreating tables in Supabase..."

    source venv/bin/activate
    python3 -c "
import os
import psycopg2

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print('ERROR: DATABASE_URL not found in environment')
    exit(1)

conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

print('Dropping existing tables...')
cursor.execute('DROP TABLE IF EXISTS track_tags CASCADE')
cursor.execute('DROP TABLE IF EXISTS tags CASCADE')
cursor.execute('DROP TABLE IF EXISTS tracks CASCADE')
cursor.execute('DROP TABLE IF EXISTS processing_log CASCADE')
cursor.execute('DROP TABLE IF EXISTS user_actions CASCADE')

print('Creating fresh tables...')
cursor.execute('''
    CREATE TABLE tracks (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        artist TEXT,
        bpm REAL,
        tonality TEXT,
        genre TEXT,
        label TEXT,
        comments TEXT,
        grouping TEXT,
        tags_json TEXT
    )
''')

cursor.execute('''
    CREATE TABLE tags (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL UNIQUE
    )
''')

cursor.execute('''
    CREATE TABLE track_tags (
        track_id INTEGER,
        tag_id INTEGER,
        FOREIGN KEY (track_id) REFERENCES tracks (id) ON DELETE CASCADE,
        FOREIGN KEY (tag_id) REFERENCES tags (id) ON DELETE CASCADE,
        PRIMARY KEY (track_id, tag_id)
    )
''')

cursor.execute('''
    CREATE TABLE processing_log (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        job_display_name TEXT,
        original_filename TEXT NOT NULL,
        input_file_path TEXT,
        output_file_path TEXT,
        track_count INTEGER,
        status TEXT NOT NULL,
        job_type TEXT NOT NULL,
        result_data TEXT,
        checkpoint_data TEXT
    )
''')

cursor.execute('''
    CREATE TABLE user_actions (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        action_description TEXT NOT NULL
    )
''')

cursor.execute('CREATE INDEX idx_tracks_name_artist ON tracks(name, artist)')
cursor.execute('CREATE INDEX idx_processing_log_timestamp ON processing_log(timestamp DESC)')
cursor.execute('CREATE INDEX idx_processing_log_status ON processing_log(status)')
cursor.execute('CREATE INDEX idx_processing_log_job_type ON processing_log(job_type)')

conn.commit()
cursor.close()
conn.close()

print('✅ Database reset complete!')
"

else
    echo "Database reset cancelled."
    exit 0
fi

echo "--- Starting Redis in the background... ---"
docker run -d --name tag-genius-redis -p 6379:6379 redis:latest

echo ""
echo "--- Environment is ready! ---"
echo "Next steps:"
echo "1. In a new terminal, run: source venv/bin/activate"
echo "2. Then run: python3 app.py"
echo ""
echo "3. In another new terminal, run: source venv/bin/activate"
echo "4. Then run: celery -A app:celery worker --loglevel=info"