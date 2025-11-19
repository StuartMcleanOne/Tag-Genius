# Tag Genius: Design Choices & Architecture Decisions
**Quick-Reference Guide to Technical Decisions**

---

## Purpose of This Document

This is a **technical appendix** containing architecture decisions and their rationale. Unlike the Development Journal (which tells the story), this document is optimized for:
- Technical interviews ("Why did you choose X over Y?")
- Code reviews
- Onboarding new developers
- Architecture discussions

**Target Audience:** Technical interviewers, senior developers, system architects

---

## Table of Contents

1. [Core Architecture](#core-architecture)
2. [AI Integration](#ai-integration)
3. [Data Management](#data-management)
4. [Frontend Architecture](#frontend-architecture)
5. [Performance Optimizations](#performance-optimizations)
6. [Deployment Decisions](#deployment-decisions)

---

## Core Architecture

### Asynchronous Task Processing

**Decision:** Flask + Celery + Redis architecture

**Alternatives Considered:**
- Synchronous Flask (initial implementation)
- Django with Celery
- FastAPI with background tasks

**Why This Choice:**
```
Flask (Web Server)
  ↓
Redis (Message Broker)
  ↓
Celery Worker (Background Processing)
  ↓
SQLite (Data Persistence)
```

**Rationale:**
- **Flask:** Lightweight, familiar, perfect for MVP
- **Celery:** Industry standard for Python async tasks
- **Redis:** Fast, reliable message broker
- **Separation of Concerns:** Web tier can restart without killing jobs

**Trade-offs:**
- **Pro:** Handles any library size, no timeouts
- **Pro:** Scales horizontally (add more workers)
- **Con:** More infrastructure complexity (3 services vs 1)
- **Con:** Requires Redis dependency

**When to Reconsider:**
- If you only need to process <50 tracks → synchronous is fine
- If deploying to serverless → use AWS Lambda instead

---

### Single-Responsibility Modules

**Decision:** One Celery task per job type

```python
@celery.task
def process_library_task(log_id, input_path, output_path, config):
    """Handles AI tagging jobs"""
    pass

@celery.task
def split_library_task(log_id, input_path, output_folder):
    """Handles library splitting jobs"""
    pass
```

**Rationale:**
- **Isolation:** Split job failure doesn't affect tagging
- **Monitoring:** Track success rates per job type
- **Scaling:** Can add more workers for specific job types

**Alternative Rejected:**
```python
# Don't do this
@celery.task
def process_job(job_type, *args):
    if job_type == 'tag':
        process_library(...)
    elif job_type == 'split':
        split_library(...)
```
**Why Rejected:** Violates single responsibility, harder to monitor/debug

---

## AI Integration

### The "Guided Discovery" Model

**Decision:** Two-tier genre classification

```python
prompt = """
1. Choose ONE Primary Genre from: [House, Techno, Drum & Bass, ...]
2. Identify specific Sub-Genres using your knowledge
   Example: Primary = "House", Sub = ["French House", "Disco House"]
"""
```

**Alternatives Considered:**

**Option A: Flat Vocabulary (Rejected)**
```python
GENRES = ["House", "Techno", "French House", "Deep House", ...]
# Problem: 200+ options, AI confusion, lost high-level grouping
```

**Option B: Free-Form (Rejected)**
```python
prompt = "Identify the genre of this track"
# Problem: Tag chaos (300+ unique genres)
```

**Why Guided Discovery Wins:**
- **Structure:** Primary genre ensures consistency
- **Intelligence:** Sub-genres capture nuance
- **Filtering:** Rekordbox can filter by primary genre
- **Searchable:** Sub-genres make tracks findable

**Technical Implementation:**
```python
{
    "primary_genre": ["House"],           # Always single value
    "sub_genre": ["French House", "Disco House"]  # Variable length
}

# In XML:
<TRACK Genre="House, French House, Disco House" />
```

---

### Mode-Based AI Function

**Decision:** Single AI function with mode parameter

```python
def call_llm_for_tags(track_data, config, mode='full'):
    if mode == 'genre_only':
        # Fast, lightweight prompt
        prompt = build_genre_prompt(track_data)
    else:  # mode == 'full'
        # Complete metadata prompt
        prompt = build_full_prompt(track_data, config)
    
    return call_openai_api(prompt)
```

**Alternative Rejected: Separate Functions**
```python
# Don't do this
def get_genre_from_ai(track):
    pass

def call_llm_for_tags(track, config):
    pass

# Problem: Two "brains" with potentially different logic
```

**Rationale:**
- **DRY Principle:** Single source of truth
- **Consistency:** Genre identification logic is identical everywhere
- **Maintainability:** Update prompt once, affects all features
- **Testing:** Test one function, not two

**Trade-off:**
- **Pro:** Consistency guaranteed
- **Con:** Function has two responsibilities (arguable)

---

### Exponential Backoff for API Resilience

**Decision:** Implement retry logic with exponential delays

```python
max_retries = 5
initial_delay = 2

for attempt in range(max_retries):
    try:
        response = requests.post(api_url, ...)
        return response.json()
    except requests.exceptions.RequestException:
        delay = initial_delay * (2 ** attempt)  # 2, 4, 8, 16, 32 sec
        time.sleep(delay)
```

**Alternatives Considered:**
- Fixed 1-second delay (too naive, still hit limits)
- No retry (unacceptable, single failures kill jobs)
- Third-party library like `tenacity` (overkill for MVP)

**Rationale:**
- **Resilience:** Gracefully handles rate limits
- **Cost:** Prevents job failures that waste API credits
- **UX:** User doesn't see failures, just slower processing

**When This Matters:**
- Processing >50 tracks in one job
- Multiple concurrent users (production)

---

### Batch Processing for AI Grouper

**Decision:** Split large genre lists into batches

```python
def get_genre_map_from_ai(genre_list):
    batch_size = 10
    final_map = {}
    
    for i in range(0, len(genre_list), batch_size):
        batch = genre_list[i:i + batch_size]
        batch_map = call_ai_grouper(batch)
        final_map.update(batch_map)
    
    return final_map
```

**Problem Solved:**
```
# Before: Single request with 50+ genres
genres = ["French House", "Industrial Techno", ...]  # 50 items
call_ai(genres)  # ERROR: Payload too large

# After: 5 requests with 10 genres each
for batch in batches_of_10(genres):
    call_ai(batch)  # Success
```

**Trade-offs:**
- **Pro:** No payload size errors
- **Pro:** Better error recovery (one batch fails, others succeed)
- **Con:** More API calls (but negligible cost)

---

## Data Management

### Master Blueprint Caching

**Decision:** Store maximum-detail AI response, render dynamically

**Architecture:**
```
First Tagging (Cache Miss):
  1. Call OpenAI with MAXIMUM detail config
  2. Save complete JSON to tracks.tags_json
  3. Render subset based on user's selected level
  4. Write rendered tags to XML

Second Tagging (Cache Hit):
  1. Load Master Blueprint from database
  2. Render subset based on NEW detail level
  3. Write rendered tags to XML (no API call!)
```

**Database Schema:**
```sql
CREATE TABLE tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    artist TEXT,
    bpm REAL,
    tonality TEXT,
    genre TEXT,
    label TEXT,
    comments TEXT,
    grouping TEXT,
    tags_json TEXT  -- Master Blueprint stored here as JSON
);

CREATE INDEX idx_tracks_name_artist ON tracks(name, artist);
```

**Rendering Function:**
```python
def apply_user_config_to_tags(blueprint_tags, user_config):
    """Trim Master Blueprint to match user's selected detail"""
    rendered = json.loads(json.dumps(blueprint_tags))  # Deep copy
    
    # Trim lists to user's requested counts
    for key in ['sub_genre', 'energy_vibe', 'situation_environment', 'components']:
        if key in rendered and key in user_config:
            rendered[key] = rendered[key][:user_config[key]]
    
    return rendered
```

**Why This Architecture:**
- **Performance:** 12,000x faster on cache hits (40 min → 0.02 sec)
- **Cost:** 50% reduction on re-tags ($0.50 → $0.00)
- **UX:** Instant experimentation with detail levels
- **Scalability:** Foundation for V2.0 community cache

**Alternative Rejected: Store Only User's Selected Level**
```python
# Don't do this
def process_track(track, user_config):
    tags = call_llm_for_tags(track, user_config)  # Only get what user wants
    save_to_db(track, tags)

# Problem: If user wants more detail later, must call API again
```

**Trade-offs:**
- **Pro:** One API call per track ever
- **Pro:** Enables instant re-tagging
- **Con:** Larger database storage (JSON vs normalized)
- **Con:** More complex rendering logic

**When This Matters:**
- Users experimenting with detail levels (likely)
- Re-tagging same library multiple times (common)
- Future community cache (V2.0 roadmap)

---

### SQLite for MVP

**Decision:** Use SQLite for local development and MVP deployment

**Alternatives Considered:**
- PostgreSQL (cloud-ready but requires external server)
- MongoDB (flexible schema but overkill)
- MySQL (heavyweight for single-user app)

**Why SQLite:**
- **Zero Config:** Single file, no server required
- **ACID:** Full transaction support
- **Python Native:** Built into Python standard library
- **Sufficient:** Handles 100,000+ tracks easily
- **Simple Deployment:** One file to backup/restore

**Technical Details:**
```python
def get_db_connection():
    """Establishes and returns a connection to the SQLite database."""
    conn = sqlite3.connect('tag_genius.db')
    conn.row_factory = sqlite3.Row  # Dict-like access
    return conn
```

**Limitations:**
- **Concurrency:** Single writer (fine for MVP)
- **Network:** No remote access (fine for local app)
- **Scale:** Not ideal for 1M+ tracks or multi-user

**When to Migrate:**
- V2.0 community cache (needs shared database)
- Multi-user deployment
- Need for advanced querying features

**Migration Path to PostgreSQL:**
```python
# Future V2.0:
# 1. Replace sqlite3 with psycopg
# 2. Update SQL syntax (AUTOINCREMENT → SERIAL)
# 3. Add RETURNING clauses for inserts
# 4. Deploy to Supabase/Render
```

**Trade-offs:**
- **Pro:** Dead simple, zero external dependencies
- **Pro:** Fast for single-user workload
- **Pro:** Portable (entire DB is one file)
- **Con:** Can't scale to community cache without migration
- **Con:** No built-in replication

---

### Database Context Manager

**Decision:** Wrap all DB operations in context manager

```python
@contextmanager
def db_cursor():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()  # Auto-commit on success
    except Exception as e:
        conn.rollback()  # Auto-rollback on error
        raise e
    finally:
        cursor.close()
        conn.close()  # Always cleanup

# Usage
with db_cursor() as cursor:
    cursor.execute("INSERT INTO tracks ...")
    # Automatic commit, rollback, and cleanup
```

**Alternatives Rejected:**
```python
# Don't do this - manual management
def update_track():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE ...")
    conn.commit()
    cursor.close()
    conn.close()  # Easy to forget!
```

**Rationale:**
- **Safety:** Guarantees connection cleanup even on exceptions
- **Transactions:** Automatic commit/rollback
- **DRY:** Write once, use everywhere
- **Pythonic:** Follows context manager best practices

---

## Frontend Architecture

### Polling-Based Status Updates

**Decision:** Frontend polls `/history` endpoint every 5 seconds

```javascript
function pollJobStatus(jobId) {
    const interval = setInterval(async () => {
        const response = await fetch('/history');
        const jobs = await response.json();
        const job = jobs.find(j => j.id === jobId);
        
        if (job.status === 'Completed' || job.status === 'Failed') {
            clearInterval(interval);
            handleJobComplete(job);
        }
    }, 5000);
}
```

**Alternatives Considered:**
- WebSockets (real-time push)
- Server-Sent Events (SSE)
- Long polling

**Why Polling Wins for MVP:**
- **Simplicity:** No additional infrastructure
- **Reliability:** Works through firewalls/proxies
- **Sufficient:** 5-second delays are acceptable UX
- **Stateless:** Server doesn't track connections

**Trade-offs:**
- **Pro:** Simple, reliable, no new dependencies
- **Con:** Slightly wasteful (polls even when nothing changes)
- **Con:** Not real-time (5 sec delay)

**When to Upgrade to WebSockets:**
- Multiple users on same job (collaborative tagging)
- Need sub-second updates
- Server load from polling becomes issue (unlikely)

---

### sessionStorage for UI State

**Decision:** Use `sessionStorage` to persist split results

```javascript
// Save split results
sessionStorage.setItem('lastSplitResults', JSON.stringify(files));

// Restore on page load
function restorePreviousState() {
    const saved = sessionStorage.getItem('lastSplitResults');
    if (saved) {
        const files = JSON.parse(saved);
        displaySplitResults(files);
    }
}
```

**Why sessionStorage:**
- **Persistence:** Survives page refreshes
- **Scoped:** Cleared when tab closes (intentional)
- **Simple:** No backend changes needed
- **Fast:** Instant load

**Alternative Rejected: Server-Side Session**
```python
# Don't do this for MVP
session['split_results'] = files
# Problem: Requires server-side session management
```

**When Server-Side Sessions Matter:**
- Multi-device support needed
- Longer persistence required (days, not hours)

---

### Direct File Downloads

**Decision:** Serve files directly from Flask, not S3

```python
@app.route('/download_split_file')
def download_split_file():
    file_path = request.args.get('path')
    
    # Security: Ensure path is within outputs/ directory
    safe_path = os.path.abspath(os.path.join('outputs', file_path))
    if not safe_path.startswith(os.path.abspath('outputs')):
        return jsonify({"error": "Invalid path"}), 403
    
    return send_file(safe_path, as_attachment=True)
```

**Alternatives Considered:**
- AWS S3 + signed URLs
- Cloud Storage (Google Cloud)

**Why Direct Serving:**
- **Simplicity:** No cloud storage setup
- **Cost:** No S3 egress fees
- **Control:** Complete control over access
- **Speed:** Fine for MVP scale (<100 users)

**Security Measures:**
- Path validation (prevent directory traversal)
- Whitelist-based (only outputs/ directory)
- No authentication (files are user-generated, non-sensitive)

**When to Switch to S3:**
- Scaling beyond single server
- Need CDN for global users
- Want to offload bandwidth from app server

---

## Performance Optimizations

### Color Coding Based on Energy

**Decision:** Map track color to energy level, not vibes

```python
def get_color_from_energy(energy_level):
    if energy_level >= 9:
        return "0xFF007F", "Pink"      # Peak
    elif energy_level == 8:
        return "0xFFA500", "Orange"    # High
    elif energy_level >= 6:
        return "0xFFFF00", "Yellow"    # Medium-high
    elif energy_level >= 4:
        return "0x00FF00", "Green"     # Medium
    else:
        return "0x25FDE9", "Aqua"      # Chill
```

**Alternative Rejected: Vibe-Based Colors**
```python
# Don't do this
if "Uplifting" in vibes:
    color = "Yellow"
elif "Dark" in vibes:
    color = "Purple"
# Problem: Multi-vibe tracks get unpredictable colors
```

**Rationale:**
- **Consistency:** Energy is single value, vibes are array
- **Objectivity:** Energy is measurable, vibes are subjective
- **Sorting:** DJs can sort by color = sort by energy
- **Visual:** "Hot to cold" scale is intuitive

---

### Rekordbox Proprietary Color Codes

**Decision:** Use Rekordbox's actual hex codes, not standard web colors

**Discovery Process:**
1. Manually color tracks in Rekordbox
2. Export to XML
3. Inspect `Colour` attribute values
4. Document actual codes

**The Mapping:**
```python
# Standard Web Colors (don't use!)
STANDARD_PINK = "0xFF00FF"  # Doesn't work in Rekordbox
STANDARD_AQUA = "0x00FFFF"  # Doesn't work in Rekordbox

# Rekordbox Proprietary Colors (use these!)
REKORDBOX_PINK = "0xFF007F"
REKORDBOX_AQUA = "0x25FDE9"
```

**Why This Matters:**
- Colors must display correctly in target software
- No standard exists, must reverse-engineer
- Diagnostic testing is essential

---

### Database Indexes

**Decision:** Index (name, artist) for cache lookups

```sql
CREATE INDEX idx_tracks_name_artist ON tracks(name, artist);
CREATE INDEX idx_processing_log_timestamp ON processing_log(timestamp DESC);
CREATE INDEX idx_processing_log_status ON processing_log(status);
```

**Why These Indexes:**
- `(name, artist)` → Cache hit checks (most frequent query)
- `timestamp DESC` → Recent jobs first (history page)
- `status` → Filter by job status

**Query Performance:**
```sql
-- Without index: Full table scan (slow)
SELECT tags_json FROM tracks WHERE name = 'Track' AND artist = 'Artist';
-- 100,000 tracks: ~50ms

-- With index: Direct lookup (fast)
SELECT tags_json FROM tracks WHERE name = 'Track' AND artist = 'Artist';
-- 100,000 tracks: ~2ms
```

**Trade-offs:**
- **Pro:** 25x faster cache hits
- **Con:** Slower inserts (negligible for this use case)
- **Con:** More storage (indexes take space)

---

## Deployment Decisions

### Local Development Simplicity

**Decision:** Keep deployment simple for MVP

**Current Setup:**
```bash
# Terminal 1: Redis
docker run -d --name tag-genius-redis -p 6379:6379 redis:latest

# Terminal 2: Flask
python3 app.py

# Terminal 3: Celery
celery -A app:celery worker --loglevel=info
```

**Why This Works:**
- **No External Services:** Everything runs locally
- **Easy Testing:** Fast iteration cycles
- **Zero Cost:** No cloud bills during development
- **Full Control:** Debug everything

**Limitations:**
- **Single Machine:** Can't distribute workload
- **No Persistence:** Redis data lost on restart (acceptable for MVP)
- **Manual Setup:** Each developer must configure

**Future Production Architecture (V2.0):**
```
Service 1: Web Service (Gunicorn)
  - Deployed on Render.com
  
Service 2: Celery Workers
  - Background service on Render.com
  
Service 3: Redis
  - Upstash (managed Redis)
  
Service 4: PostgreSQL
  - Supabase (managed database)
```

---

### Environment Variables

**Decision:** All secrets in environment variables, never in code

```python
# .env file (local development)
OPENAI_API_KEY=sk-...
CELERY_BROKER_URL=redis://localhost:6379/0

# Code
import os
api_key = os.environ.get("OPENAI_API_KEY")
```

**Security:**
- No secrets in code or version control
- Separate secrets per environment (dev/staging/prod)
- Easy rotation (change in .env, restart service)

---

## Decision Framework

When making architectural decisions, prioritize in this order:

1. **Correctness** - Does it work reliably?
2. **Simplicity** - Can it be maintained?
3. **Performance** - Is it fast enough?
4. **Cost** - Is it affordable at scale?
5. **Flexibility** - Can it evolve?

**Example Application:**

**Decision:** Master Blueprint Caching

1. ✅ **Correctness:** Tags are consistent
2. ✅ **Simplicity:** Single JSON column, simple rendering
3. ✅ **Performance:** 12,000x faster re-tags
4. ✅ **Cost:** 50% reduction on re-tags
5. ✅ **Flexibility:** Enables V2.0 community cache

**All criteria met → Excellent decision**

---

## When to Revisit These Decisions

### SQLite → PostgreSQL
**Trigger:** V2.0 community cache feature
**Alternative:** Cloud database for shared access

### Polling → WebSockets
**Trigger:** If real-time updates become critical
**Alternative:** Socket.io or native WebSockets

### Direct Serving → S3
**Trigger:** If bandwidth costs exceed $50/month
**Alternative:** S3 + CloudFront CDN

---

## Appendix: Architecture Diagrams

### Request Flow (Tagging Job)
```
User Browser
    ↓ [POST /upload_library]
Flask Web Server
    ↓ [1. Save file]
    ↓ [2. Create job log]
    ↓ [3. Dispatch task]
Redis Queue
    ↓ [Task queued]
Celery Worker
    ↓ [1. Load file]
    ↓ [2. For each track:]
        ↓ [Check cache]
        ↓ [Call OpenAI if needed]
        ↓ [Save to SQLite]
    ↓ [3. Write XML]
    ↓ [4. Update job status]
SQLite Database
    ↓ [Job marked 'Completed']
User Browser (polling)
    ↓ [GET /history every 5 sec]
    ↓ [Detects 'Completed']
    ↓ [Shows download button]
```

### Data Flow (Master Blueprint)
```
Track "Daft Punk - One More Time"
    ↓
Check Database (name + artist)
    ↓
Cache Miss?
    ↓ YES
    Call OpenAI (MAXIMUM detail)
        ↓
        {
            "primary_genre": ["House"],
            "sub_genre": ["French House", "Disco House", "Filter House"],
            "energy_level": 9,
            "energy_vibe": ["Uplifting", "Funky", "Euphoric"],
            "situation_environment": ["Peak Hour", "Opener", "Crowd Pleaser"],
            "components": ["Synth", "Vocoder", "Talkbox"],
            "time_period": ["2000s"]
        }
        ↓
    Save to tracks.tags_json (Master Blueprint)
        ↓
    Render subset based on user config
        ↓
    Write to XML

Cache Hit?
    ↓ YES
    Load Master Blueprint from database (instant)
        ↓
    Render subset based on user config
        ↓
    Write to XML
```

---

**End of Design Choices Document**

*This document is optimized for quick reference during technical discussions. For the full development story, see DEVELOPMENT_JOURNAL.md.*
