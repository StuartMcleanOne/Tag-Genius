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

### Project Genesis: The DJ's Tagging Dilemma (draft)

The genesis of Tag Genius was a desire to solve a universal problem for DJs: the tedious, inconsistent, and time-consuming manual labor of tagging a digital music library. While this includes everything from genre to musical components, one of the most notoriously difficult and subjective aspects is quantifying a track's "energy level."

A popular thread on the /r/DJs subreddit, titled "Identifying energy level," serves as a perfect case study for this specific challenge, highlighting the broader pain points that Tag Genius aims to solve across all metadata fields:

The Limits of Intuition: The original poster and many commenters expressed frustration with relying solely on subjective "intuition" to build a coherent set. They were actively seeking a more systematic, data-driven approach, a problem that applies to both genre and energy.

Oversimplified Metrics: Experienced DJs in the thread correctly pointed out that a simple metric like BPM is a poor indicator of true energy. This mirrors the broader problem of using simplistic tags (e.g., just "House") when more nuance is required.

Time-Consuming Manual Systems: To solve these issues, DJs are forced to invent their own laborious, manual tagging systems for all metadata. Commenters described using star ratings, color-coding, and detailed comments to track everything—a process that takes hours to apply and maintain.

These real-world challenges affirmed the core mission of Tag Genius: to provide a holistic, AI-driven solution. By generating a comprehensive set of tags—including foundational genres, specific sub-genres, musical components, and an objective energy_level—the project automates the entire manual process. The AI's ability to tackle the difficult "energy" problem is a key feature, but it's part of a larger goal: to deliver a consistently and intelligently tagged library with minimal user effort.

---

### Project Genesis: The DJ's Tagging Dilemma (draft)

The genesis of Tag Genius was a desire to solve a universal problem for DJs: the tedious, inconsistent, and time-consuming manual labor of organizing a digital music library. In an era of endless digital music, DJs find their collections plagued by a host of metadata challenges that stifle creativity and make finding the right track at the right moment incredibly difficult.

This core problem manifests in several "pain points" that were the direct inspiration for the project's features:

Genre Chaos & Inconsistency: The most common frustration is the lack of a standardized genre system. Tracks are often mislabeled by online stores, tagged with hyper-specific or conflicting genres, or lack a genre tag altogether. This creates a disorganized library where similar-sounding tracks are impossible to group together reliably.

Lack of Descriptive Richness: A single genre tag is rarely enough to capture a track's essence. DJs need deeper, more functional metadata to understand its texture, mood, and ideal use case. Information about musical elements (like a piano or vocal), the overall vibe (e.g., 'dark' vs. 'uplifting'), and the best time to play it (e.g., 'warmup' vs. 'peak hour') is often missing entirely.

The Manual Labor Bottleneck: The only traditional solution to these problems is for the DJ to manually listen to every track and painstakingly enter their own tags. This is a monumental time sink that scales poorly with a growing library and takes valuable hours away from practicing the actual craft of mixing.

Tag Genius was conceived as a holistic, AI-powered solution to this entire ecosystem of problems. By leveraging a large language model, it attacks each pain point directly: it standardizes genres using its "Guided Discovery" model, enriches each track with a full suite of descriptive tags for mood and components, and automates the entire process to eliminate the manual labor bottleneck. The inclusion of an objective energy_level is a key part of this, providing another layer of powerful, sortable data. The ultimate goal is to transform a chaotic library into a consistently and intelligently organized collection, empowering DJs to focus on their creativity.

---

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

### Phase 9: The Data-Driven Calibration Sprint

With the core features in place, the project entered its final and most crucial stage before the MVP could be considered complete: **AI calibration**. While the initial energy scores were functional, they lacked the precision needed for a professional tool. A systematic, data-driven approach was required to refine the AI's performance and ensure the results were genuinely useful for a DJ.

To achieve this, a three-step iterative process was established:

1.  **Creating a "Ground Truth":** A small, diverse playlist of electronic music was manually rated by the user to create a "ground truth" dataset. This served as an expert's "answer key" against which the AI's performance could be quantitatively measured.

2.  **Quantitative Analysis:** A custom Python script (`comparison_ratings.py`) was developed to compare the AI's ratings against the ground truth. This tool provided clear, immediate feedback on the model's accuracy, including metrics like **"Exact Match %"** and **"Average Difference"** in stars.

3.  **Iterative Prompt Engineering:** The initial test revealed a clear "compression" bias—the AI was hesitant to use the low (1-2) and high (9-10) ends of the scale. Based on this data, the AI prompt was refined over two major cycles, with each change targeting a specific, observed weakness in the model's output.

This process was a clear success. After the final prompt adjustment, the model's performance improved dramatically. **Exact matches increased from an initial 33% to over 52%, and the average difference fell to just 0.81 stars.** This marked the successful conclusion of the calibration sprint, resulting in a significantly more accurate and reliable model ready for the MVP.

---
### Phase 10: Enhancing the Development Workflow

During the intensive testing and calibration phase, a repetitive and error-prone task was identified: the need to constantly reset the database to ensure clean test runs. To solve this and improve the developer experience, a new tool was added directly into the application's command-line interface.

A new Flask CLI command, **`flask drop-tables`**, was created to programmatically delete all tables from the database. This was then combined with the existing `flask init-db` command into a single, one-line terminal command (`flask drop-tables && flask init-db`) to provide a complete, one-step reset of the development environment. This automated a crucial part of the testing workflow, increasing speed and reducing the potential for user error during a critical development phase.

### Phase 11: Implementing a Flexible "Clear Tags" Feature

With the core model calibrated, the next roadmap item was the "Clear Tags" feature. The initial plan was a simple pre-processing checkbox. However, a deeper UX discussion revealed the need for two distinct user workflows: a one-click "clear and re-tag" option for experimentation, and a "clear only" utility to simply clean a file without running the AI.

Instead of building a separate UI for each, an elegant, consolidated solution was designed and implemented. A new "None" option was added to the "Tagging Detail Level" slider. This allowed the feature to work in two powerful modes using just a single checkbox:

1.  **Clear and Re-tag:** A user checks the "Clear Tags" box and selects a detail level (e.g., "Recommended"). The backend first calls the `clear_ai_tags` function and then proceeds with the AI analysis, all in one seamless operation.
2.  **Clear Only:** A user checks the "Clear Tags" box and selects the new "None" level. The backend clears the tags but then intelligently skips the time-consuming and costly AI call, immediately producing a cleaned XML file.

This approach successfully implemented two features' worth of functionality with minimal changes to the UI and backend logic, showcasing an efficient and user-focused design.

---
### Phase 12: Final Calibration - Debugging the "Last Mile"

After successfully implementing the "Clear Tags" feature, a final end-to-end test in Rekordbox revealed a frustrating and elusive visual bug. While the star ratings were being applied correctly, the corresponding colors—specifically the highest 'Pink' and lowest 'Aqua'—were not displaying in the software.

This triggered an intense "last mile" debugging sprint. The investigation confirmed that the application's logic was sound and that the correct `Colour` attributes were being written to the output XML file. The problem was therefore isolated to how the target software, Rekordbox, was interpreting the standard hex color codes.

It was hypothesized that Rekordbox used a specific, non-standard color palette. To solve this, a definitive diagnostic test was devised:
1.  Several tracks were manually colored inside Rekordbox, one for each color in the palette.
2.  The library was exported to an XML file, creating a "Rosetta Stone."
3.  This file was inspected to reveal the exact, proprietary hex codes that this version of Rekordbox expected (e.g., `0xFF007F` for Pink, not the standard `0xFF00FF`).

The color logic in `app.py` was updated with these definitive hex codes. A final test confirmed the solution: all colors now display perfectly in Rekordbox, synchronizing flawlessly with the AI-generated star ratings. This phase served as a critical lesson in the challenges of integrating with proprietary, closed-source software and the importance of data-driven debugging to solve the final 1% of a problem.

## Future Improvements (Roadmap)

With the core AI engine calibrated and the application architecture stable, the focus now shifts to enhancing user control, improving the user experience, and expanding the application's capabilities.

---
### Core Functionality (Immediate Next Steps)

These features build directly on the existing backend and add significant value for the user.

* **Implement "Clear Tags" Feature:** Finalize and implement the planned "stateless" version of the "Clear Tags" feature. This will allow users to re-process a previously tagged library by checking a box on upload, which will reset the AI-generated comments, colors, and star ratings before the new analysis runs.

* **Customizable Vocabulary:** Build a feature that allows users to edit the controlled vocabulary through a simple UI. This would give advanced users power over the AI's tag suggestions for `components`, `energy_vibe`, and other categories, tailoring the output to their specific needs.

---
### User Interface & Experience (UI/UX)

These items focus on making the application more intuitive, informative, and powerful from the user's perspective.

* **Configurable Tag Settings:** Enhance the frontend to allow users to configure key parameters for each run from the UI, such as the desired number of sub-genres or components to be generated.

* **Informative Tooltips:** Add context-aware help icons (❔) to UI elements, starting with the "Clear Tags" checkbox. This will clearly explain each feature's function, what it does, and what it doesn't do (e.g., clarifying that Genres are always overwritten).

* **Polished Dashboard UI:** Evolve the simple HTML page into a modern, card-based dashboard inspired by professional analytics tools. This would provide a more engaging and visually appealing experience for tracking job progress and viewing results.

---
### Long-Term Vision (V2.0)

These are major architectural upgrades that would transform Tag Genius into a more powerful and interactive application.

* **Stateful "Interactive Mode":** A significant evolution from a stateless utility to a stateful web app. This would introduce the "Load/Eject" workflow, allowing a user to upload a file once and perform multiple actions on it (tag, clear, re-tag with different settings) without needing to re-upload. This would require implementing server-side state management and a suite of new API endpoints.

* **Advanced Calibration Profiles:** To further address the subjectivity of tagging, this feature would allow users to select a "Calibration Profile" (e.g., "Hard Techno & Industrial," "Deep & Melodic House," "Classic Funk/Soul"). This profile would apply a specially tuned AI prompt to the entire library run, calibrating the AI's output to the specific nuances of the user's taste without requiring them to split their library.
