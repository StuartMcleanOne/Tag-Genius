# Tag Genius

## The AI-Powered DJ's Assistant That Eliminates Decision Fatigue

Tag Genius is an intelligent music library management tool that solves a problem every DJ faces: **the overwhelming burden of tagging thousands of tracks with meaningful, consistent metadata.**

It's not just about genres. It's about generating a **complete descriptive profile** for every track - energy levels, vibes, situations, and musical components - the exact tags DJs need to find the perfect track at the perfect moment, but never have time to create manually.

**The result?** A perfectly organized library where every track is instantly searchable by the characteristics that actually matter during a set.

---

## The Problem: Decision Fatigue at Scale

Modern DJs don't lack music - they drown in it. A typical library contains thousands of tracks, each requiring dozens of subjective decisions:

* **Genre Anxiety:** Is this "Deep House" or "Tech House"? What about "Melodic Techno"? The paradox of hyper-specific sub-genres creates constant uncertainty.
* **The Missing Context:** Genre alone isn't enough. *When* should you play this track? What's the vibe? Is it a peak-hour banger or a sunset closer?
* **The Manual Labor Bottleneck:** Creating these tags manually means listening to every track and making dozens of decisions per song. For a 2,000-track library, that's **over 65 hours** of tedious work.
* **Inconsistent Data:** Relying on online stores or memory leads to chaos. Similar tracks become impossible to find because the tagging is subjective and inconsistent.

This isn't a workflow problem. It's a **decision fatigue crisis** that stifles creativity and makes the joy of DJing feel like data entry.

---

## The Solution: AI as Your Definitive Tagging Authority

Tag Genius eliminates the burden of choice by establishing the AI as a **single source of truth** for music classification.

Upload your Rekordbox XML library, and the AI generates:

* **Intelligent Genre Classification:** Primary genre + specific sub-genres (e.g., "House → French House, Disco House")
* **Objective Energy Levels:** A calibrated 1-10 scale that maps to star ratings and color-coded dots (Pink = Peak Hour, Aqua = Chill)
* **Contextual Situation Tags:** When to play it ("Peak Hour", "Sunset", "Warmup", "Closer")
* **Emotional Vibe Tags:** How it feels ("Uplifting", "Dark", "Funky", "Hypnotic")
* **Musical Component Tags:** What makes it unique ("Piano", "Strings", "Vocal", "Saxophone")

All of this is written directly into your XML file in a clean, machine-readable format that integrates seamlessly with Rekordbox's search and filtering system.

---

## The Value Proposition: Time & Cost

The ROI is undeniable:

| Metric              | Manual Tagging             | Tag Genius        | Advantage         |
| :------------------ | :------------------------- | :---------------- | :---------------- |
| **Time (250 Tracks)** | ~8.3 Hours (at 2 min/track) | ~40 Minutes       | **12x Faster** |
| **Cost (250 Tracks)** | ~$166 (at $20/hr wage)     | **~$0.04** | **99.9% Cheaper** |

For a 2,000-track library, Tag Genius replaces **65+ hours of manual labor** with a background task that costs less than **$0.35**.

More importantly: it's **consistent**. French House is French House, every time. No more second-guessing your own past decisions.

---

## Key Features

### 🎯 The Master Blueprint System
Tag Genius creates a "Master Blueprint" for every track on first encounter - a complete profile stored locally in the database. Future tagging jobs simply retrieve and render this cached data at whatever detail level you choose (Essential, Recommended, Detailed). Result: **instant re-tagging** without additional AI costs.

### ⚡ Asynchronous Processing
Built on Flask + Celery + Redis, large library jobs run in the background without freezing your browser. Real-time status updates via JavaScript polling keep you informed.

### 🎨 Visual Energy Coding
Tracks are automatically color-coded (Pink → Orange → Yellow → Green → Aqua) based on their energy level, providing at-a-glance filtering in Rekordbox. Star ratings (1-5) map to the same energy scale.

### 🗂️ Intelligent Library Splitting
Split massive libraries into manageable genre-specific files (e.g., `Electronic.xml`, `Hip_Hop.xml`) using AI-powered genre grouping. Perfect for targeted tagging with genre-specific calibration.

### 🔄 Flexible Tagging Modes
- **Tag Mode:** Add AI tags at Essential/Recommended/Detailed levels
- **Split Mode:** Organize by genre before tagging
- **Clear Mode:** Remove all AI tags to start fresh

### 🛡️ User Override Protection
Respects your manual workflow. Tracks you've manually colored "Red" (e.g., to mark for deletion) are automatically skipped during tagging.

### 📜 Job History & Rollback
Every job is logged with timestamps. Download archived "before" and "after" XML files as `.zip` packages for easy rollback.

---

## Tech Stack

* **Backend:** Python, Flask
* **Database:** SQLite (local file storage)
* **Task Queue:** Celery
* **Message Broker:** Redis (Docker)
* **AI Engine:** OpenAI GPT-4o-mini
* **Frontend:** Vanilla JavaScript, Tailwind CSS

---

## Setup & Installation

### Prerequisites
- Python 3.12+
- Docker Desktop (for Redis)
- OpenAI API key

### Installation Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/StuartMcleanOne/Tag-Genius
   cd Tag-Genius
   ```

2. **Create and activate virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   
   Create a `.env` file in the root directory:
   ```env
   OPENAI_API_KEY=your_openai_api_key
   CELERY_BROKER_URL=redis://localhost:6379/0
   CELERY_RESULT_BACKEND=redis://localhost:6379/0
   ```

5. **Initialize the database**
   ```bash
   flask init-db
   ```

---

## How to Run

Tag Genius runs as **three separate services**. Open three terminal windows:

### Terminal 1: Redis (Message Broker)
```bash
docker run -d --name tag-genius-redis -p 6379:6379 redis:latest
```

### Terminal 2: Flask Web Server
```bash
source venv/bin/activate
python3 app.py
```
Server runs at `http://127.0.0.1:5001`

### Terminal 3: Celery Worker (Background Processing)
```bash
source venv/bin/activate
celery -A app:celery worker --loglevel=info
```

### Access the App
Open your browser and navigate to:
```
http://127.0.0.1:5001/app
```

---

## Usage Workflow

1. **Export your Rekordbox library** as XML (File → Export Collection in XML format)
2. **Upload to Tag Genius** via the web interface
3. **Choose your mode:**
   - **Split Library:** Organize by genre first (recommended for large libraries)
   - **Tag Library:** Apply AI tags at your chosen detail level
   - **Clear Tags:** Remove existing AI tags
4. **Monitor progress** in real-time via the status display
5. **Download your tagged library** and import back into Rekordbox

---

## The "Guided Discovery" Model

Tag Genius doesn't force tracks into rigid categories. Instead, it uses a **two-tier genre system**:

1. **Primary Genre:** One authoritative high-level classification (e.g., "House", "Techno", "Hip Hop")
2. **Sub-Genre Descriptors:** AI-identified specific styles (e.g., "French House", "Acid Techno")

This provides structure without sacrificing nuance. The AI has the freedom to identify niche sub-genres while maintaining a consistent top-level taxonomy.

---

## API Endpoints (for developers)

* `POST /upload_library` - Upload XML + config, returns job_id
* `GET /history` - Retrieve all past jobs (used for status polling)
* `GET /export_xml` - Download most recent tagged XML
* `GET /download_job/<job_id>` - Download archived before/after files as .zip
* `POST /tag_split_file` - Tag a specific split file from workspace
* `GET /download_split_file?path=<path>` - Download a single split file

---

## Future Roadmap

### V2.0: The Community Cache
Evolve from a single-user tool to a **global knowledge base**. When you tag a track, the result is anonymously contributed to a community database. Future users get **instant results** for popular tracks without API calls.

**Network effects:** The more users, the larger the cache, the faster everyone's experience.

**Technical Requirements:**
- Migration from SQLite to cloud database (PostgreSQL/Supabase)
- De-duplication system for track matching
- Privacy-preserving anonymous contribution system

### Genre-Specific Calibration Profiles
Let users choose specialized AI profiles (e.g., "Techno Genius", "Deep House Specialist") that calibrate energy ratings and tag vocabulary for specific genres.

### Tag Genius Radio
Turn waiting time into discovery time. While jobs process, the app streams 30-second previews of random tracks from your library via Spotify/Apple Music APIs, helping you rediscover forgotten gems.

---

## Why Tag Genius Exists

This project was born from frustration. As a DJ, I was spending more time organizing my library than actually mixing. Every session began with the same ritual: scrolling through thousands of tracks, trying to remember what each one sounded like, what energy it had, when I should play it.

The existing tools either gave me **too many choices** (creating decision paralysis) or **no intelligence** (forcing manual data entry). I wanted something that would just... *know*. That would tag my library the way an expert musicologist would, consistently and objectively.

Tag Genius is that tool. It's not perfect - AI isn't magic - but it's **12 times faster than doing it manually** and costs practically nothing. More importantly, it frees you to focus on what actually matters: the music.

---

## License

MIT License - see LICENSE file for details

---

## Contributing

This is an MVP built for a university project. If you're interested in contributing to V2.0 or have feature suggestions, feel free to open an issue or submit a pull request.

---

## Acknowledgments

Built with frustration, coffee, and the belief that DJs deserve better tools.

Special thanks to the `/r/DJs` community for validating that this problem is universal.

*"French House is French House, regardless of who is listening to it."*

---

**Stuart McLean**  
Berlin, 2025
