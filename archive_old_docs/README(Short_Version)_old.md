# Tag Genius

## Overview

Tag Genius is an AI-powered music library management tool designed to automate the tedious process of tagging and organizing a DJ's music library.

The application uses a Flask backend, a multi-table SQLite database, and the OpenAI API to parse a user's XML file. It generates consistent, structured tags (Genres, Vibes, etc.), automatically assigns a track colour based on an AI-generated energy level, and adds a star rating based on the same metric. The final output is a new, enhanced XML file with clean, machine-readable comments.

***
## Key Features

* **Asynchronous Processing**: Built to scale using **Celery** and **Redis**, the application processes large libraries in a background task queue. This provides an instant response to the user and prevents server timeouts.
* **Library Splitting**: Instantly parses a large Rekordbox XML and splits it into smaller, genre-specific files, creating an interactive workspace for targeted tagging.
* **Real-Time Frontend Updates**: A JavaScript **polling** mechanism communicates with the backend, providing the user with real-time feedback on the job's status and automatically enabling the download button upon completion.
* **Intelligent Genre Grouping**: Utilizes a sophisticated **"Guided Discovery"** model. The AI first assigns a single high-level **Primary Genre** and then uses its own knowledge to determine specific, accurate **Sub-Genres** (e.g., "French House"), providing a perfect balance of structure and AI-driven intelligence.
* **Energy-Based Color & Star Ratings**:
    * **Color**: Automatically assigns a color from a "hot-to-cold" scale (Pink → Aqua) based on the AI's objective 1-10 energy score, providing a consistent, at-a-glance energy indicator.
    * **Star Rating**: Converts the same 1-10 energy score to a 1-5 star rating using a refined scale that ensures a meaningful and useful distribution of ratings.
* **User Override Protection**: Respects a user's manual workflow by automatically detecting and preserving any tracks manually colored "Red" in Rekordbox, preventing them from being overwritten.
* **Organized Comment Formatting**: All generated tags are written to the `Comments` field in a clean, prefixed, and logically ordered format, now prepended with a sortable energy score (e.g., `/* E: 08 / Sit: ... */`) to align with standard DJ workflows.
* **Job Archiving & History**: Fulfills the "Retaining Conversation History" MVP requirement. For every job, a "before" (original) and "after" (tagged) XML file is archived with a unique timestamp. A dedicated API endpoint allows for downloading these files as a `.zip` package, providing a crucial safety and rollback feature.

## Tech Stack

* **Backend**: Python, Flask
* **Task Queue**: Celery
* **Message Broker**: Redis (run via Docker)
* **Database**: SQLite
* **Core APIs**: OpenAI API, Lexicon Local API

## API Endpoints

---

## API Endpoints

* **`POST /upload_library`**: Kicks off the asynchronous tagging process for an uploaded file and returns a unique `job_id`.
* **`POST /split_library`**: Kicks off the asynchronous splitting process for an uploaded file and returns a unique `job_id`.
* **`POST /tag_split_file`**: Kicks off an asynchronous tagging job for a specific, pre-existing split file on the server.
* **`GET /history`**: Retrieves a JSON list of all past processing jobs for status polling.
* **`GET /download_job/<int:job_id>`**: Downloads a `.zip` archive containing the "before" and "after" files for a specific tagging job.
* **`GET /download_split_file`**: Downloads a single, specified file from a library split job.
* **`GET /export_xml`**: Downloads the most recently generated tagged XML file from a main tagging job.
* **`POST /log_action`**: Logs a user interaction (e.g., a button click) to the database.
* **`GET /get_actions`**: Retrieves the history of all logged user actions.

---

## Setup and Installation

1. Install Docker Desktop: Required to run the Redis message broker.

2. Clone the repository.

3. Create and activate a virtual environment: python3 -m venv venv and source venv/bin/activate.

4. Install dependencies: pip install -r requirements.txt.

5. Create .env file: Create a file named .env and add your OpenAI API key: OPENAI_API_KEY='your_key_here'.

6. Make the Reset Script Executable: chmod +x reset_env.sh.
## How to Run the Application

7. The application now runs as three separate services in three separate terminals. All commands should be run from the project's root directory.

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

### **Terminal 3: Start the Celery Worker**
This terminal runs the background worker that processes the tagging jobs.

```bash
# Activate the virtual environment
source venv/bin/activate

# Run the Celery worker
celery -A app:celery worker --loglevel=info
```
Once all three services are running, you can open the index.html file in a web browser to use the application.

### **Development: Resetting the Database**
To completely reset the database for a clean test run, use this single command:

```bash
flask drop-tables && flask init-db
```

## Development Process & Key Decisions

This section outlines the major phases of the MVP's development.including challenges faced and the solutions implemented.

### Project Genesis: The DJ's Tagging Dilemma

Project Genesis: The DJ's Tagging Dilemma 
The genesis of Tag Genius was a desire to solve a universal problem for DJs: the tedious, inconsistent, and time-consuming manual labor of organizing a digital music library. In an era of endless digital music, DJs find their collections plagued by a host of metadata challenges that stifle creativity and make finding the right track at the right moment incredibly difficult.

This core problem manifests in several "pain points" that were the direct inspiration for the project's features:

Genre Chaos & Inconsistency: The most common frustration is the lack of a standardized genre system. Tracks are often mislabeled by online stores, tagged with hyper-specific or conflicting genres, or lack a genre tag altogether. This creates a disorganized library where similar-sounding tracks are impossible to group together reliably.

Lack of Descriptive Richness: A single genre tag is rarely enough to capture a track's essence. DJs need deeper, more functional metadata to understand its texture, mood, and ideal use case. Information about musical elements (like a piano or vocal), the overall vibe (e.g., 'dark' vs. 'uplifting'), and the best time to play it (e.g., 'warmup' vs. 'peak hour') is often missing entirely.

The Manual Labor Bottleneck: The only traditional solution to these problems is for the DJ to manually listen to every track and painstakingly enter their own tags. This is a monumental time sink that scales poorly with a growing library and takes valuable hours away from practicing the actual craft of mixing.

Tag Genius was conceived as a holistic, AI-powered solution to this entire ecosystem of problems. By leveraging a large language model, it attacks each pain point directly: it standardizes genres using its "Guided Discovery" model, enriches each track with a full suite of descriptive tags for mood and components, and automates the entire process to eliminate the manual labor bottleneck. The inclusion of an objective energy_level is a key part of this, providing another layer of powerful, sortable data. The ultimate goal is to transform a chaotic library into a consistently and intelligently organized collection, empowering DJs to focus on their creativity.

### Phase 1: Project Genesis & The "Flash Model" Crisis

The project began with a clear and practical goal: to build an AI-powered tool to solve the "common pain point of disorganized and inconsistent track metadata" for DJs. The initial vision was to create a system that could parse a Rekordbox XML file and use AI to generate simplified, organized tags based on user preference.

However, a complete **"Project Reset"** was required after early development was severely hampered by the limitations of the initial AI model, which resulted in significant data loss. This crisis was a critical turning point that led to upgrading to a more capable Pro model and establishing a safer, Git-based workflow.

### Phase 2: Rebuilding with a Professional Workflow

The project rebuild began with a user-first approach, focusing on defining a clear data schema before writing code. An initial timing issue with the database (`no such table: tracks`) was resolved by adopting a more robust practice: moving the database initialization to a separate Flask CLI command (`flask init-db`).

This phase also involved a significant learning process around the Lexicon API. The initial assumption was that it was a web-based enrichment tool. Through research and analyzing the API documentation, it was correctly identified as a local API for accessing the user's personal Lexicon library data. This understanding led to a more efficient implementation, using the dedicated `/search/tracks` endpoint instead of pulling and searching through a large list of tracks manually.

### Phase 3: Overcoming API Rate Limits

With the database and Lexicon API calls functioning correctly, the most significant technical hurdle emerged: OpenAI's API rate limits. The script was upgraded to implement **"exponential backoff"**—an industry-standard error-handling technique that gracefully handles `429 Too Many Requests` errors by automatically retrying with increasing delays.

### Phase 4: From Technical Success to a User-Focused Product

With the core engine functional, the project focus shifted to refining the user experience (UX). The raw AI output was not just data; it needed to be useful within Rekordbox. The application's output was completely redesigned to populate Rekordbox's native, filterable `My Tag` feature using a clean, industry-standard hashtag format (e.g., `#peak_time #synth`).

### Phase 5: Implementing the "Genre Grouping" Model

After the initial MVP, the project underwent a significant refactoring to improve the quality of the AI's output. The original flat vocabulary system was replaced with a sophisticated **"Genre Grouping"** model, using a two-tiered system (`primary_genre` and `sub_genre`) to support a more nuanced and logical approach to music categorization.

### Phase 6: Application Scaling and UI Feedback

With the core tagging logic refined, the project's final major architectural hurdle was scalability. The synchronous design meant the app would time out on large libraries. The solution was to re-architect the application to be asynchronous using a **Celery task queue with Redis** as the message broker. A JavaScript polling mechanism was also added to the frontend to provide the user with real-time feedback on the job's status.

### Phase 7: User-Driven Refinement Sprint

Following the successful implementation of the asynchronous architecture, a full end-to-end test was conducted. Based on a critical review of the AI's output, a series of user-driven refinements were implemented. This included overhauling the genre model to a **"Guided Discovery"** system, linking color-coding directly to an objective energy score, refining the star-rating scale for better distribution, and improving the formatting of the final comment tags.

### Phase 8: Fulfilling the "Conversation History" MVP Requirement

To meet the "Conversation History" MVP requirement, a user-centric **"Job Archiving"** feature was designed. This feature provides a tangible "before and after" snapshot of each processing job, saving unique, timestamped copies of both the input and output XML files. A new API endpoint was created to allow the user to download these paired files as a `.zip` package.

### Phase 9: The Data-Driven Calibration Sprint

With the core features in place, the project entered its most crucial stage: **AI calibration**. A systematic, data-driven approach was required to refine the AI's performance. A three-step iterative process was established: creating a "Ground Truth" dataset, using a custom Python script (`comparison_ratings.py`) for quantitative analysis, and performing iterative prompt engineering. This process was a clear success, dramatically improving the model's performance. **Exact matches increased from an initial 33% to over 52%**, and the average difference fell to just 0.81 stars.

### Phase 10: Implementing a Flexible "Clear Tags" Feature

With the core model calibrated, the **"Clear Tags"** feature was implemented. A deeper UX discussion revealed the need for two distinct user workflows: "clear and re-tag" and "clear only." Instead of building a separate UI for each, an elegant, consolidated solution was designed. A new **"None"** option was added to the "Tagging Detail Level" slider, allowing the feature to work in two powerful modes using just a single checkbox.

### Phase 11: Integration Debugging & Color Correction

A final end-to-end test in Rekordbox revealed a frustrating visual bug where some AI-assigned colors were not displaying correctly. This triggered an intense "last mile" debugging sprint. The problem was isolated to Rekordbox interpreting standard hex color codes incorrectly. To solve this, a definitive diagnostic test was devised: tracks were manually colored inside Rekordbox and the library was exported to create a **"Rosetta Stone,"** revealing the exact, proprietary hex codes the software expected (e.g., `0xFF007F` for Pink). The color logic was updated with these definitive hex codes, and a final test confirmed the solution.

### Phase 12: Architecting the "Intelligent Splitter"
With the core tagging engine calibrated, focus shifted to the "Library Splitter" feature. The development involved a significant architectural design process, moving from a "fast-but-dumb" initial version to a more robust model. After identifying a "Two Brains Problem" that created logical inconsistencies, the project pivoted to a definitive "One Brain, Two Modes" architecture. This refactored the main AI function to operate in 'full' or 'genre_only' mode, ensuring a single source of truth for all genre classification.

### hase 13: Hardening the MVP - A Debugging & Refactoring Sprint
End-to-end testing with a large, messy library revealed critical architectural issues. A focused debugging sprint was initiated to harden the application. This involved solving API grouping failures by implementing batch processing for the AI grouper, improving API resilience by making retry logic more "patient", fixing a critical polling loop bug by tracking a unique Job ID, and streamlining the development workflow with a new reset_env.sh script.

### Phase 14: Final Architectural Upgrade - Asynchronous Splitter
The final architectural flaw was identified during a full-scale test: the synchronous nature of the splitter caused the entire process to timeout and crash on large libraries. To solve this, a major upgrade was performed. The splitter's logic was moved into a dedicated background Celery task (split_library_task), the database schema was enhanced to handle multiple job types, and a new frontend polling function was implemented. This final upgrade aligns all major features under a consistent, asynchronous, and scalable architecture, marking the successful completion of the core MVP.