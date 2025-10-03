# Tag Genius

## Overview

Tag Genius is an AI-powered music library management tool designed to automate the tedious process of tagging and organizing a DJ's music library.

The application uses a Flask backend, a multi-table SQLite database, and the OpenAI API to parse a user's XML file. It generates consistent, structured tags (Genres, Vibes, etc.), automatically assigns a track colour based on an AI-generated energy level, and adds a star rating based on the same metric. The final output is a new, enhanced XML file with clean, machine-readable comments.

***
## Key Features

* **Asynchronous Processing**: Built to scale using **Celery** and **Redis**, the application processes large libraries in a background task queue. This provides an instant response to the user and prevents server timeouts.
* **Real-Time Frontend Updates**: A JavaScript **polling** mechanism communicates with the backend, providing the user with real-time feedback on the job's status and automatically enabling the download button upon completion.
* **Intelligent Genre Grouping**: Utilizes a sophisticated **"Guided Discovery"** model. The AI first assigns a single high-level **Primary Genre** and then uses its own knowledge to determine specific, accurate **Sub-Genres** (e.g., "French House"), providing a perfect balance of structure and AI-driven intelligence.
* **Energy-Based Color & Star Ratings**:
    * **Color**: Automatically assigns a color from a "hot-to-cold" scale (Pink → Aqua) based on the AI's objective 1-10 energy score, providing a consistent, at-a-glance energy indicator.
    * **Star Rating**: Converts the same 1-10 energy score to a 1-5 star rating using a refined scale that ensures a meaningful and useful distribution of ratings.
* **User Override Protection**: Respects a user's manual workflow by automatically detecting and preserving any tracks manually colored "Red" in Rekordbox, preventing them from being overwritten.
* **Organized Comment Formatting**: All generated tags are written to the `Comments` field in a clean, prefixed, and logically ordered format (`/* Sit: ... / Vibe: ... */`) for improved readability.
* **Job Archiving & History**: Fulfills the "Retaining Conversation History" MVP requirement. For every job, a "before" (original) and "after" (tagged) XML file is archived with a unique timestamp. A dedicated API endpoint allows for downloading these files as a `.zip` package, providing a crucial safety and rollback feature.

## Tech Stack

* **Backend**: Python, Flask
* **Task Queue**: Celery
* **Message Broker**: Redis (run via Docker)
* **Database**: SQLite
* **Core APIs**: OpenAI API, Lexicon Local API

## API Endpoints

* **POST /upload_library:** The main endpoint for uploading an XML file and a configuration object. Kicks off the asynchronous tagging process and returns a 202 Accepted status.


* **GET /history:** Retrieves a JSON list of all past processing jobs, ordered from newest to oldest. This is used by the frontend for status polling.


* **GET /download_job/<int:job_id>:** Downloads a .zip package containing the archived "before" (original) and "after" (tagged) XML files for a specific job run.


* **GET /export_xml:** Allows the user to download the most recently generated tagged XML file.

## Setup and Installation

1.  **Install Docker Desktop**: Download and install from the [official website](https://www.docker.com/products/docker-desktop/). This is required to run the Redis message broker.
2.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    ```
3.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
4.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
5.  **Create `.env` file:** Create a file named `.env` in the root directory and add your OpenAI API key:
    ```
    OPENAI_API_KEY='your_key_here'
    ```
6.  **Initialize the database:**
    ```bash
    flask init-db
    ```

## How to Run the Application

The application now runs as three separate services in three separate terminals. All commands should be run from the project's root directory.

### **Terminal 1: Start Redis**
This command starts the Redis message broker using Docker.
```bash
docker run -d --name tag-genius-redis -p 6379:6379 redis:latest
```

### **Terminal 2: Start the Flask Web Server**
This terminal runs the main web application.
```bash
# Activate the virtual environment
source venv/bin/activate

# Run the app using the venv's python
venv/bin/python app.py
```


###  **Terminal 3: Start the Celery Worker**
This terminal runs the background worker that processes the tagging jobs.
```bash
# Activate the virtual environment
source venv/bin/activate

# Run the Celery worker
celery -A app:celery worker --loglevel=info
```

Once all three services are running, you can open the index.html file in a web browser to use the application.

---

## Development Process & Key Decisions

This section outlines the major phases of the MVP's development.including challenges faced and the solutions implemented.

### Phase 1: Project Genesis & The "Flash Model" Crisis

The project began with a clear and practical goal: to build an AI-powered tool to solve the "common pain point of disorganized and inconsistent track metadata" for DJs. The initial vision was to create a system that could parse a Rekordbox XML file and use AI to generate simplified, organized tags based on user preference.

However, early development was severely hampered by the limitations of the initial AI model. The "flash model just lost the plot," forgot objectives, and deleted core functions, resulting in the loss of nearly 20 hours of work. This crisis was a critical turning point. The experience highlighted a stark contrast between the capabilities of free and professional AI tools, leading to the reflection that access to more powerful models provides a significant advantage. 

The solution was a complete "Project Reset". This involved abandoning the corrupted work, upgrading to a more capable Pro model, and establishing a new, safer workflow built on a solid foundation: using Git to revert to a known-good state and creating a new, clean development branch to move forward with confidence.

---

### Phase 2: Rebuilding with a Professional Workflow

The project rebuild began with a user-first approach, focusing on defining a clear data schema before writing code to ensure all future features could be supported. The initial database setup encountered a timing issue where the server would start before the database table was created, causin g a "no such table: tracks" error. 

This was resolved by adopting a more robust, standard practice: moving the database initialization to a separate Flask CLI command (`flask init-db`), which guarantees the database is ready before the application runs.

This phase also involved a significant learning process around the Lexicon API. The initial assumption was that it was a web-based enrichment tool. Through research and analyzing the API documentation, it was correctly identified as a local API for accessing the user's personal Lexicon library data. This understanding led to a more efficient implementation, using the dedicated `/search/tracks` endpoint instead of pulling and searching through a large list of tracks manually.

---

### Phase 3: Overcoming API Rate Limits

With the database and Lexicon API calls functioning correctly, the most significant technical hurdle emerged: OpenAI's API rate limits. Initial tests showed that after processing a small "burst" of 6-7 tracks, the application would be flooded with `429 Too Many Requests` errors.

An initial, simple solution of adding a fixed one-second delay between API calls proved insufficient. This necessitated a more professional solution. The script was upgraded to implement "exponential backoff"—an industry-standard error-handling technique. With this new logic, the application could now intelligently react to the `429` error by catching it, waiting for a progressively longer period (2, 4, 8, 16 seconds), and then retrying the request. This change was a major breakthrough, transforming the script from a brittle process into a resilient one that could gracefully handle API limitations.
 
---

### Phase 4: From Technical Success to a User-Focused Product

With the core engine fully functional, the project entered its final and most important phase: refining the user experience (UX). The user noted that the raw output in the Comments field was a "wall of text" that gave them a "headache" to read. The true goal was not just to store data, but to populate Rekordbox's native, filterable "My Tag" feature.

This user-focused feedback, combined with crucial insights from the Lexicon documentation about Rekordbox's limitations (a 4-category limit for MyTags and the use of hashtags for data transfer), led to the final, elegant solution. The application's output was completely redesigned. The AI's six tag categories were strategically mapped to Rekordbox's native Genre field plus its four available "My Tag" slots. The Comments field was repurposed to carry this data using a clean, industry-standard hashtag format (e.g., `#peak_time #synth`). This final pivot ensured the tool was not just technically functional but truly useful, transforming a "headache" into a clean, organized, and professionally tagged music library.

### Phase 5: Implementing the "Genre Grouping" Model

After the initial MVP, the project underwent a significant refactoring to improve the quality of the AI's output. The original flat vocabulary system was replaced with a sophisticated "Genre Grouping" model. This involved redesigning the controlled vocabulary into a two-tiered system (`primary_genre` and `sub_genre` descriptors) and rewriting the AI prompt to support this more nuanced and logical approach to music categorization. During this phase, the database connection logic was also refactored to use a context manager for improved safety and code cleanliness.


### Phase 6: Application Scaling and UI Feedback

With the core tagging logic refined, the project's final major architectural hurdle was scalability. The synchronous design meant the app would time out on large libraries. The solution was to re-architect the application to be asynchronous using a Celery task queue with Redis as the message broker. This involved creating a background worker to handle all slow API calls, freeing up the web server to respond instantly.

This change introduced a new UX problem: the user had no feedback on the job's status. To solve this, a JavaScript polling mechanism was added to the frontend. The UI now periodically calls the /history API to check the job's status and automatically updates to inform the user when the process is complete, creating a robust and user-friendly experience.

### Phase 7: User-Driven Refinement Sprint

Following the successful implementation of the asynchronous architecture, a full end-to-end test was conducted. Based on a critical review of the AI's output, a series of user-driven refinements were implemented to elevate the application from "functional" to "genuinely useful." This included overhauling the genre model to a "Guided Discovery" system, linking color-coding directly to an objective energy score, refining the star-rating scale for better distribution, and improving the formatting of the final comment tags for readability. This phase was a crucial example of using real-world testing to inform product design.

### Phase 8: Fulfilling the "Conversation History" MVP Requirement
To meet the final MVP requirement, a user-centric "Job Archiving" feature was designed and implemented. This feature interprets "Conversation History" as a tangible "before and after" snapshot of each processing job. The backend was updated to save unique, timestamped copies of both the input and output XML files, and the `processing_log` database table was modified to store the paths to this archive. A new API endpoint was created to allow the user to download these paired files as a `.zip` package, providing a robust rollback and comparison capability.

## Future Improvements (Roadmap)

UI/UX Refinements: Develop a more polished front-end, providing richer feedback to the user (e.g., progress bars, detailed error messages).

New Features: Implement the "Clear Tags" button functionality and allow users to customize the controlled vocabulary.

