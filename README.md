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