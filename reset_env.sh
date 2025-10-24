#!/bin/bash

# Exit immediately if a command fails
set -e

echo "--- Checking for Docker... ---"
# Check if the Docker daemon is running. If not, print an error and exit.
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running. Please start Docker Desktop and try again."
    exit 1
fi

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
echo "1. In a new terminal, run: source venv/bin/activate"
echo "2. Then run: python3 app.py"
echo ""
echo "3. In another new terminal, run: source venv/bin/activate"
echo "4. Then run: celery -A app:celery worker --loglevel=info"