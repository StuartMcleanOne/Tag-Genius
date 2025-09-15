# Tag Genius

## Overview

Tag Genius is an AI-powered music library management tool designed for DJs. It processes a Rekordbox XML library file, calls external APIs (Lexicon and OpenAI) to get rich metadata, and uses an AI model to generate a structured, consistent set of tags based on user-defined detail levels. The goal is to automate the tedious process of library organization and improve track searchability.

## Features

* **XML Processing**: Parses Rekordbox XML library files.
* **AI Tagging**: Uses a Large Language Model (LLM) to generate tags across six categories: `primary_genre`, `sub_genre`, `energy_vibe`, `situation_environment`, `components`, and `time_period`.
* **Adjustable Detail**: A "simplicity dial" on the front-end allows the user to choose between three levels of tagging detail: Essential, Recommended, and Detailed.
* **API Integration**: Connects to the local Lexicon DJ app for metadata enrichment.
* **Web Interface**: A simple front-end for uploading files and initiating the tagging process.

## Setup and Installation

1.  **Clone the repository:**
    `git clone <your-repo-url>`
2.  **Create a virtual environment:**
    `python3 -m venv venv`
    `source venv/bin/activate`
3.  **Install dependencies:**
    `pip install -r requirements.txt`
4.  **Create `.env` file:** Create a file named `.env` in the root directory and add your OpenAI API key:
    `OPENAI_API_KEY='your_key_here'`
5.  **Initialize the database:**
    `flask init-db`

## How to Run the Application

1.  Ensure the **Lexicon DJ application** is running on your computer.
2.  Start the Flask backend server:
    `python app.py`
3.  Open the `index.html` file in a web browser.
4.  Use the interface to upload your XML file and start the tagging process.

## Development Process & Key Decisions
This section outlines the major phases of the MVP's development, including challenges faced and the solutions implemented.

### Phase 1: Project Reset & Foundation
Goal: To recover from a critical failure with a previous AI model and establish a solid, reliable foundation for the project.

Challenge: The previous model had corrupted the project's logic. We needed to abandon the corrupted work and safely revert to a known-good state in Git.

Solution: We used git checkout <hash> to travel back to a stable commit. We then immediately created a new branch (git switch -c feature/tagging-rewrite) to isolate our new development effort, leaving the old, corrupted main branch untouched.

### Phase 2: Core Logic & Debugging
Goal: To build the core backend functionality: parsing the XML, calling external APIs, and saving the results.

Challenge: Initial testing revealed several critical bugs: "Connection refused" errors from the Lexicon API, no such column errors from the database, and 429 Too Many Requests errors from the OpenAI API.

Solution: We debugged each issue systematically. We ensured the local Lexicon app was running, re-initialized the database with the correct schema, and implemented a robust "exponential backoff" retry mechanism to handle the API rate limits gracefully.

### Phase 3: Implementing the Final Output
Goal: To write the AI-generated tags back into a new, Rekordbox-compatible XML file and allow the user to download it.

Challenge: We needed to modify the XML file without corrupting its structure or losing any of the original metadata that Rekordbox requires.

Solution: We adopted a "surgical" approach using Python's xml.etree.ElementTree library. The script loads the original XML into memory, modifies only the Genre and Comments attributes directly on the XML elements, and then saves the entire, intact structure to a new file.

### Phase 4: UX Refinements & Final Strategy
Goal: To implement a professional tagging strategy by mapping AI-generated tags to Rekordbox's native Genre field and 4 "My Tag" categories.

Challenge: The initial output was a dense "wall of text" and the AI's tags were unpredictable. Research into the Lexicon DJ software revealed that Rekordbox has a 4-category limit for its native "My Tags" and that a hashtag system is a standard method for transferring this data.

Solution: We adopted a hashtag system. The Genre attribute is populated with genre tags. All other tags (vibe, situation, etc.) are formatted as hashtags (e.g., #peak_time #synth) and written to the Comments attribute. This industry-standard approach provides a clean data transfer method intended to populate Rekordbox's native tag system upon import. We also added full documentation to the codebase.