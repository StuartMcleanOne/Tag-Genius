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

## Development Process 

This section outlines the major phases of the MVP's development.including challenges faced and the solutions implemented.

## Project Genesis: 
## The DJ's Tagging Dilemma 

### **Project Genesis:** The DJ's Tagging Dilemma

The genesis of Tag Genius was a desire to solve a universal problem for DJs: the tedious, inconsistent, and time-consuming manual labor of organizing a digital music library. In an era of endless digital music, DJs find their collections plagued by a host of metadata challenges that stifle creativity and make finding the right track at the right moment incredibly difficult.

This core problem manifests in several "pain points" that were the direct inspiration for the project's features:

### **Genre Chaos & Inconsistency:** 

The most common frustration is the lack of a standardized genre system. Tracks are often mislabeled by online stores, tagged with hyper-specific or conflicting genres, or lack a genre tag altogether. This creates a disorganized library where similar-sounding tracks are impossible to group together reliably.

### **Lack of Descriptive Richness:** 

A single genre tag is rarely enough to capture a track's essence. DJs need deeper, more functional metadata to understand its texture, mood, and ideal use case. Information about musical elements, the overall vibe, and the best time to play it is often missing entirely.

### **The Manual Labor Bottleneck:** 

The only traditional solution to these problems is for the DJ to manually listen to every track and painstakingly enter their own tags. This is a monumental time sink, a frustration validated in community discussions like the popular "/r/DJs" subreddit thread on identifying track energy, where users described creating their own laborious, manual systems. This process takes valuable hours away from practicing the actual craft of mixing.

Tag Genius was conceived as a holistic, AI-powered solution to this entire ecosystem of problems. By leveraging a large language model, it attacks each pain point directly: it standardizes genres using its "Guided Discovery" model, enriches each track with a full suite of descriptive tags, and automates the entire process to eliminate the manual labor bottleneck. The inclusion of an objective energy_level is a key part of this, providing another layer of powerful, sortable data. The ultimate goal is to transform a chaotic library into a consistently and intelligently organized collection, empowering DJs to focus on their creativity.

---

## Phase 1: 
## Building with a Professional Workflow

The project build began with a user-first approach, focusing on defining a clear data schema before writing code to ensure all future features could be supported. The initial database setup encountered a timing issue where the server would start before the database table was created, causing a "no such table: tracks" error. 

This was resolved by adopting a more robust, standard practice: moving the database initialization to a separate Flask CLI command (`flask init-db`), which guarantees the database is ready before the application runs.

This phase also involved a significant learning process around the Lexicon API. The initial assumption was that it was a web-based enrichment tool. Through research and analyzing the API documentation, it was correctly identified as a local API for accessing the user's personal Lexicon library data. This understanding led to a more efficient implementation, using the dedicated `/search/tracks` endpoint instead of pulling and searching through a large list of tracks manually.

---

## Phase 2: 
## Overcoming API Rate Limits

With the database and Lexicon API calls functioning correctly, the most significant technical hurdle emerged: OpenAI's API rate limits. Initial tests showed that after processing a small "burst" of 6-7 tracks, the application would be flooded with `429 Too Many Requests` errors.

An initial, simple solution of adding a fixed one-second delay between API calls proved insufficient. This necessitated a more professional solution. The script was upgraded to implement "exponential backoff"—an industry-standard error-handling technique. With this new logic, the application could now intelligently react to the `429` error by catching it, waiting for a progressively longer period (2, 4, 8, 16 seconds), and then retrying the request. This change was a major breakthrough, transforming the script from a brittle process into a resilient one that could gracefully handle API limitations.

--- 

## Phase 3: 
## From Technical Success to a User-Focused Product

With the core engine fully functional, the project entered its final and most important phase: refining the user experience (UX). The user noted that the raw output in the Comments field was a "wall of text" that gave them a "headache" to read. The true goal was not just to store data, but to populate Rekordbox's native, filterable "My Tag" feature.

This user-focused feedback, combined with crucial insights from the Lexicon documentation about Rekordbox's limitations (a 4-category limit for MyTags and the use of hashtags for data transfer), led to the final, elegant solution. The application's output was completely redesigned. The AI's six tag categories were strategically mapped to Rekordbox's native Genre field plus its four available "My Tag" slots. The Comments field was repurposed to carry this data using a clean, industry-standard hashtag format (e.g., `#peak_time #synth`). This final pivot ensured the tool was not just technically functional but truly useful, transforming a "headache" into a clean, organized, and professionally tagged music library.

---

## Phase 4 
## Implementing the "Genre Grouping" Model

After the initial MVP, the project underwent a significant refactoring to improve the quality of the AI's output. The original flat vocabulary system was replaced with a sophisticated "Genre Grouping" model. This involved redesigning the controlled vocabulary into a two-tiered system (`primary_genre` and `sub_genre` descriptors) and rewriting the AI prompt to support this more nuanced and logical approach to music categorization. During this phase, the database connection logic was also refactored to use a context manager for improved safety and code cleanliness.

---
## Phase 5: 
## Application Scaling and UI Feedback

With the core tagging logic refined, the project's final major architectural hurdle was scalability. The synchronous design meant the app would time out on large libraries. The solution was to re-architect the application to be asynchronous using a Celery task queue with Redis as the message broker. This involved creating a background worker to handle all slow API calls, freeing up the web server to respond instantly.

This change introduced a new UX problem: the user had no feedback on the job's status. To solve this, a JavaScript polling mechanism was added to the frontend. The UI now periodically calls the /history API to check the job's status and automatically updates to inform the user when the process is complete, creating a robust and user-friendly experience.

---

## Phase 6: User-Driven Refinement Sprint

Following the successful implementation of the asynchronous architecture, a full end-to-end test was conducted. Based on a critical review of the AI's output, a series of user-driven refinements were implemented to elevate the application from "functional" to "genuinely useful." This included overhauling the genre model to a "Guided Discovery" system, linking color-coding directly to an objective energy score, refining the star-rating scale for better distribution, and improving the formatting of the final comment tags for readability. This phase was a crucial example of using real-world testing to inform product design.

---

## Phase 7: 
## Fulfilling the "Conversation History" MVP Requirement
To meet the final MVP requirement, a user-centric "Job Archiving" feature was designed and implemented. This feature interprets "Conversation History" as a tangible "before and after" snapshot of each processing job. The backend was updated to save unique, timestamped copies of both the input and output XML files, and the `processing_log` database table was modified to store the paths to this archive. A new API endpoint was created to allow the user to download these paired files as a `.zip` package, providing a robust rollback and comparison capability.

---

## Phase 8: 
## The Data-Driven Calibration Sprint

With the core features in place, the project entered its final and most crucial stage before the MVP could be considered complete: **AI calibration**. While the initial energy scores were functional, they lacked the precision needed for a professional tool. A systematic, data-driven approach was required to refine the AI's performance and ensure the results were genuinely useful for a DJ.

To achieve this, a three-step iterative process was established:

### 1.  **Creating a "Ground Truth":** 

A small, diverse playlist of electronic music was manually rated by the user to create a "ground truth" dataset. This served as an expert's "answer key" against which the AI's performance could be quantitatively measured.

### 2.  **Quantitative Analysis:** 

A custom Python script (`comparison_ratings.py`) was developed to compare the AI's ratings against the ground truth. This tool provided clear, immediate feedback on the model's accuracy, including metrics like **"Exact Match %"** and **"Average Difference"** in stars.

### 3.  **Iterative Prompt Engineering:** 

The initial test revealed a clear "compression" bias—the AI was hesitant to use the low (1-2) and high (9-10) ends of the scale. Based on this data, the AI prompt was refined over two major cycles, with each change targeting a specific, observed weakness in the model's output.

This process was a clear success. After the final prompt adjustment, the model's performance improved dramatically. **Exact matches increased from an initial 33% to over 52%, and the average difference fell to just 0.81 stars.** This marked the successful conclusion of the calibration sprint, resulting in a significantly more accurate and reliable model ready for the MVP.

---
## Phase 9: 
## Enhancing the Development Workflow

During the intensive testing and calibration phase, a repetitive and error-prone task was identified: the need to constantly reset the database to ensure clean test runs. To solve this and improve the developer experience, a new tool was added directly into the application's command-line interface.

A new Flask CLI command, **`flask drop-tables`**, was created to programmatically delete all tables from the database. This was then combined with the existing `flask init-db` command into a single, one-line terminal command (`flask drop-tables && flask init-db`) to provide a complete, one-step reset of the development environment. This automated a crucial part of the testing workflow, increasing speed and reducing the potential for user error during a critical development phase.

---

## Phase 10: 
## Implementing a Flexible "Clear Tags" Feature

With the core model calibrated, the next roadmap item was the "Clear Tags" feature. The initial plan was a simple pre-processing checkbox. However, a deeper UX discussion revealed the need for two distinct user workflows: a one-click "clear and re-tag" option for experimentation, and a "clear only" utility to simply clean a file without running the AI.

Instead of building a separate UI for each, an elegant, consolidated solution was designed and implemented. A new "None" option was added to the "Tagging Detail Level" slider. This allowed the feature to work in two powerful modes using just a single checkbox:

### 1.  **Clear and Re-tag:** 

A user checks the "Clear Tags" box and selects a detail level (e.g., "Recommended"). The backend first calls the `clear_ai_tags` function and then proceeds with the AI analysis, all in one seamless operation.

### 2.  **Clear Only:**

A user checks the "Clear Tags" box and selects the new "None" level. The backend clears the tags but then intelligently skips the time-consuming and costly AI call, immediately producing a cleaned XML file.

This approach successfully implemented two features' worth of functionality with minimal changes to the UI and backend logic, showcasing an efficient and user-focused design.

---

## Phase 11: 
## Energy Levels, Colour Coding & Star Ratings 

After successfully implementing the "Clear Tags" feature, a final end-to-end test in Rekordbox revealed a frustrating and elusive visual bug. While the star ratings were being applied correctly, the corresponding colors—specifically the highest 'Pink' and lowest 'Aqua'—were not displaying in the software.

This triggered an intense "last mile" debugging sprint. The investigation confirmed that the application's logic was sound and that the correct `Colour` attributes were being written to the output XML file. The problem was therefore isolated to how the target software, Rekordbox, was interpreting the standard hex color codes.

It was hypothesized that Rekordbox used a specific, non-standard color palette. To solve this, a definitive diagnostic test was devised:


1.  Several tracks were manually colored inside Rekordbox, one for each color in the palette.


2.  The library was exported to an XML file, creating a "Rosetta Stone."


3.  This file was inspected to reveal the exact, proprietary hex codes that this version of Rekordbox expected (e.g., `0xFF007F` for Pink, not the standard `0xFF00FF`).


The color logic in `app.py` was updated with these definitive hex codes. A final test confirmed the solution: all colors now display perfectly in Rekordbox, synchronizing flawlessly with the AI-generated star ratings. This phase served as a critical lesson in the challenges of integrating with proprietary, closed-source software and the importance of data-driven debugging to solve the final 1% of a problem.

---

## Phase 12: 
## Architecting and Implementing the "Intelligent Splitter"

With the core tagging engine calibrated, the focus shifted to a new cornerstone feature: the "Library Splitter." This feature was conceived to address a major user pain point (managing monolithic library files) and to creatively fulfill the MVP's "conversational history" requirement by creating an interactive workspace.

The development involved a significant architectural design process:

### 1.  **Initial "Fast-but-Dumb" Implementation:** 

A basic splitter was built that sorted tracks based only on existing `Genre` tags. While fast, testing revealed a critical UX flaw: it failed on messy libraries, placing all untagged tracks into a useless `Miscellaneous` bucket.


### 2.  **First Refinement ("Intelligent Fallback"):** 

To handle untagged tracks, a new, lightweight AI function (`get_genre_from_ai`) was added as a fallback within the `get_primary_genre` helper. This made the splitter robust but introduced an architectural conflict.


### 3.  **The "Two Brains" Problem:** 

I identified that having a separate AI function for splitting created two inconsistent "brains" for genre identification, violating the DRY principle and the project's core vision.


### 4.  **The Definitive "One Brain, Two Modes" Architecture:** 

The flawed "Two Brains" model was rejected. Instead, the main AI function (`call_llm_for_tags`) was refactored to operate in two modes (`'full'` and `'genre_only'`). The splitter was upgraded to use this single, consistent brain in its fast `'genre_only'` mode.

### 5.  **AI-Powered Grouping:** 

Finally, the splitter logic was enhanced to perform dynamic grouping. After determining the specific genre for each track (using the `'genre_only'` AI mode when necessary), it makes a single, fast AI call (`get_genre_map_from_ai`) to intelligently map these specific genres to the main `MAIN_GENRE_BUCKETS`. This replaced a flawed, static `GENRE_MAP` approach.

The final "Intelligent Splitter" successfully balances speed and intelligence, provides a clean, curated output (e.g., `Electronic.xml`, `Hip_Hop.xml`), and aligns perfectly with the project's long-term vision. The entire process served as a valuable case study in iterative design, architectural refinement, and prioritizing a consistent, user-focused experience.

---

## Phase 13: 
## Architecting the "Intelligent Splitter".

With the core tagging engine calibrated, the focus shifted to a new cornerstone feature: the "Library Splitter." The development involved a significant architectural design process, culminating in a "One Brain, Two Modes" architecture and an AI-powered grouping mechanism to provide a clean, curated output. This process served as a valuable case study in iterative design and prioritizing a consistent user experience.

---

## Phase 14: 
## Hardening the MVP - A Debugging & Refactoring Sprint.

Following the initial implementation of the "Intelligent Splitter," end-to-end testing with a large, messy library revealed critical architectural issues: the splitter would time out, and API rate limits caused poor-quality results. A focused debugging sprint was initiated to harden the application.

### **Diagnosing the Splitter Timeout:** 

The root cause was identified as the synchronous nature of the /split_library endpoint. Long-running operations on the main web server thread caused the browser connection to time out, killing the process. This identified the immediate next architectural step: re-architecting the splitter to be asynchronous.

### **Solving API Grouping Failures:** 

The AI "grouper" was failing on large lists of unique genres due to API request size limits. This was solved by re-architecting the get_genre_map_from_ai function to use batch processing, breaking the large list into smaller, more manageable chunks.

### **Improving API Resilience:** 

To combat API rate-limiting errors, the retry logic for the AI grouper was made more "patient" by increasing the number of retries and the initial delay, significantly improving the quality of the final split.

### **Fixing the Polling Loop:** 

A subtle but critical bug was found where the frontend polling mechanism would never stop. This was fixed by re-architecting the process to track a unique Job ID returned by the server, rather than relying on a non-unique filename.

### **Improving the Developer Workflow:** 

To speed up testing, the manual three-terminal startup process was replaced. A new reset_env.sh script now automates the entire environment reset, while leaving the Flask and Celery servers to be run manually for full, real-time log visibility.

 This sprint successfully transformed the application from a functional but brittle tool into a resilient and robust MVP, ready for final validation.

---

## Future Roadmap
### Architectural Upgrades (Immediate Priority)

**Make the Library Splitter Asynchronous:** 

The most critical next step is to move the splitter's logic into a background Celery task. This will solve the timeout issue, provide a non-blocking user experience, and allow for the implementation of a real-time progress indicator for split jobs. This involves creating a split_library_task, updating the database schema to store split job results, and adding a new polling mechanism to the frontend.

### Core Functionality (Next Steps)

**Implement "Tag this File" Button:** Connect the UI to the backend to allow a user to send a newly created split file directly to the asynchronous tagging engine.

**Customizable Vocabulary:** Build a feature that allows users to edit the controlled vocabulary through a simple UI, tailoring the AI's output to their specific needs.

## Long-Term Vision (V2.0)

These are major architectural upgrades that would transform Tag Genius into a more powerful and interactive application.

* **Stateful "Interactive Mode":** A significant evolution from a stateless utility to a stateful web app. This would introduce the "Load/Eject" workflow, allowing a user to upload a file once and perform multiple actions on it (tag, clear, re-tag with different settings) without needing to re-upload. This would require implementing server-side state management and a suite of new API endpoints.

* **Advanced Calibration Profiles:** To further address the subjectivity of tagging, this feature would allow users to select a "Calibration Profile" (e.g., "Hard Techno & Industrial," "Deep & Melodic House," "Classic Funk/Soul"). This profile would apply a specially tuned AI prompt to the entire library run, calibrating the AI's output to the specific nuances of the user's taste without requiring them to split their library.

---

---
## User Interface & Experience (UI/UX)

These items focus on making the application more intuitive, informative, and powerful from the user's perspective.

* **Configurable Tag Settings:** Enhance the frontend to allow users to configure key parameters for each run from the UI, such as the desired number of sub-genres or components to be generated.

* **Informative Tooltips:** Add context-aware help icons (❔) to UI elements, starting with the "Clear Tags" checkbox. This will clearly explain each feature's function, what it does, and what it doesn't do (e.g., clarifying that Genres are always overwritten).

* **Polished Dashboard UI:** Evolve the simple HTML page into a modern, card-based dashboard inspired by professional analytics tools. This would provide a more engaging and visually appealing experience for tracking job progress and viewing results.

---




