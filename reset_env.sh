#!/bin/bash

# Exit immediately if a command fails
set -e

echo "--- Stopping and removing old services... ---"
# Stop and remove the old Redis container if it exists
docker stop tag-genius-redis || true
docker rm tag-genius-redis || true

echo "--- Resetting the database... ---"
# Activate virtual environment, drop all tables, and re-initialize
source venv/bin/activate
flask drop-tables
flask init-db

echo "--- Starting Redis in the background... ---"
# Start Redis in detached mode
docker run -d --name tag-genius-redis -p 6379:6379 redis:latest

echo ""
echo "--- Environment is ready! ---"
echo "Next steps:"
echo "1. In a new terminal, run: venv/bin/python3 app.py"
echo "2. In another new terminal, run: venv/bin/celery -A app:celery worker --loglevel=info"