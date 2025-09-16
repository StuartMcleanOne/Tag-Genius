# Tag Genius

## Overview


***

Tag Genius is an AI-powered music library management tool designed to automate the tedious process of tagging and organizing a DJ's music library. 

The application uses a Flask backend to parse an uploaded XML file, calls external APIs (Lexicon and OpenAI) for metadata enrichment, and uses a powerful language model to generate consistent, structured tags. 

With user-controlled detail levels, the final output is a new, enhanced XML file ready for import, built to improve library searchability and streamline a DJ's workflow.

***
## Key Features

* **Rekordbox XML Processing**: Parses and writes Rekordbox-compatible XML files.


* **AI-Powered Tagging**: Uses the OpenAI API to generate tags across six distinct categories.


* **Configurable Detail Levels**: A simple UI allows the user to choose between "Essential," "Recommended," and "Detailed" tagging levels, controlling the depth of the AI's output.


* **Controlled Vocabulary**: Employs prompt engineering to constrain the AI, ensuring tags are consistent and predictable.


* **Hashtag Formatting**: Outputs tags in a clean, industry-standard `#hashtag` format in the comments field, designed for compatibility with Rekordbox's "My Tag" system.


* **Robust Error Handling**: Includes an exponential backoff mechanism to gracefully handle API rate limits without crashing.


* **Normalized Database**: Uses a multi-table SQLite database to professionally store and manage track and tag data.


* **Job History**: Logs every processing job to a database and provides an API endpoint to view the history.


* **Local API Integration**: Connects to the local Lexicon DJ application API for metadata enrichment.

## Tech Stack

* **Backend**: Python, Flask
* **Database**: SQLite
* **Frontend**: HTML, CSS, JavaScript (via Tailwind CSS)
* **Core APIs**: OpenAI API, Lexicon Local API

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    ```
2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Create `.env` file:** Create a file named `.env` in the root directory and add your OpenAI API key:
    ```
    OPENAI_API_KEY='your_key_here'
    ```
5.  **Initialize the database:**
    ```bash
    flask init-db
    ```

## How to Run the Application

1.  Ensure the **Lexicon DJ application** is running on your computer.
2.  Start the Flask backend server from the project directory:
    ```bash
    python app.py
    ```
3.  Open the `index.html` file in a web browser.
4.  Use the interface to upload your XML file and start the tagging process.

## API Endpoints

* `POST /upload_library`: The main endpoint for uploading an XML file and a configuration object to start the tagging process.


* `GET /export_xml`: Allows the user to download the most recently generated tagged XML file.


* `GET /history`: Retrieves a JSON list of all past processing jobs.


* `GET /tracks`, `GET /tracks/<id>`: Standard CRUD endpoints for viewing track data from the local database.

---

## Development Process & Key Decisions

This section outlines the major phases of the MVP's development, including challenges faced and the solutions implemented.

### Phase 1: Project Genesis & The "Flash Model" Crisis

The project began with a clear and practical goal: to build an AI-powered tool to solve the "common pain point of disorganized and inconsistent track metadata" for DJs. The initial vision was to create a system that could parse a Rekordbox XML file and use AI to generate simplified, organized tags based on user preference.

However, early development was severely hampered by the limitations of the initial AI model. The user noted that the "flash model just lost the plot," forgot objectives, and deleted core functions, resulting in the loss of nearly 20 hours of work. 

This crisis was a critical turning point. The experience highlighted a stark contrast between the capabilities of free and professional AI tools, leading to the reflection that access to more powerful models provides a significant advantage. 

The solution was a complete "Project Reset". This involved abandoning the corrupted work, upgrading to a more capable Pro model, and establishing a new, safer workflow built on a solid foundation: using Git to revert to a known-good state and creating a new, clean development branch to move forward with confidence.

---

### Phase 2: Rebuilding with a Professional Workflow

The project rebuild began with a user-first approach, focusing on defining a clear data schema before writing code to ensure all future features could be supported. The initial database setup encountered a timing issue where the server would start before the database table was created, causing a "no such table: tracks" error. 

This was resolved by adopting a more robust, standard practice: moving the database initialization to a separate Flask CLI command (flask init-db), which guarantees the database is ready before the application runs.

This phase also involved a significant learning process around the Lexicon API. The initial assumption was that it was a web-based enrichment tool. Through research and analyzing the API documentation, it was correctly identified as a local API for accessing the user's personal Lexicon library data. 

This understanding led to a more efficient implementation, using the dedicated /search/tracks endpoint instead of pulling and searching through a large list of tracks manually.

---

### Phase 3: Overcoming API Rate Limits

With the database and Lexicon API calls functioning correctly, the most significant technical hurdle emerged: OpenAI's API rate limits. Initial tests showed that after processing a small "burst" of 6-7 tracks, the application would be flooded with 429 Too Many Requests errors.

An initial, simple solution of adding a fixed one-second delay between API calls proved insufficient. This necessitated a more professional solution. The script was upgraded to implement "exponential backoff"—an industry-standard error-handling technique. With this new logic, the application could now intelligently react to the 429 error by catching it, waiting for a progressively longer period (2, 4, 8, 16 seconds), and then retrying the request. 

This change was a major breakthrough, transforming the script from a brittle process into a resilient one that could gracefully handle API limitations.

---

### Phase 4: From Technical Success to a User-Focused Product

With the core engine fully functional, the project entered its final and most important phase: refining the user experience (UX). The user noted that the raw output in the Comments field was a "wall of text" that gave them a "headache" to read. The true goal was not just to store data, but to populate Rekordbox's native, filterable "My Tag" feature.

This user-focused feedback, combined with crucial insights from the Lexicon documentation about Rekordbox's limitations (a 4-category limit for MyTags and the use of hashtags for data transfer), led to the final, elegant solution. 

The application's output was completely redesigned. The AI's six tag categories were strategically mapped to Rekordbox's native Genre field plus its four available "My Tag" slots. The Comments field was repurposed to carry this data using a clean, industry-standard hashtag format (e.g., #peak_time #synth). 

This final pivot ensured the tool was not just technically functional but truly useful, transforming a "headache" into a clean, organized, and professionally tagged music library.

## Future Improvements (Roadmap)

* **True "My Tag" Integration**: Investigate writing to the `Grouping` and `Colour` XML attributes to create native, colored category pills in Rekordbox automatically.

* **Scalability**: For very large libraries, implement a background task queue (e.g., Celery with Redis) to offload the slow API processing from the main web request.

* **UI/UX Refinements**: Develop a more polished front-end with a dedicated JavaScript file, providing richer feedback to the user (e.g., progress bars, detailed error messages).

* **New Features**: Implement the "Clear Tags" button functionality and allow users to customize the controlled vocabulary.
