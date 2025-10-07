# Key Design Choices & Rationale

This document tracks the key user-experience (UX) and product decisions made during the development of Tag Genius, highlighting the blend of design thinking, AI implementation, and coding.

---
### **1. Genre Tagging: The "Guided Discovery" Model**

* **Problem**: Early models for genre tagging were too restrictive, forcing the AI to use a predefined list that killed nuance and accuracy (e.g., labeling "French House" as just "House").
* **Insight**: The goal of the AI should be to act as an "expert curator," not a simple tag-picker. It needs the freedom to identify specific, recognized sub-genres while still being guided to prevent tag chaos.
* **Solution**: A two-tiered "Genre Grouping" model was implemented. The AI is instructed to first choose one high-level **Primary Genre** from a curated list, and then use its own knowledge to discover and apply specific **Sub-Genre** "descriptors." This provides both structure and intelligent freedom.

---
### **2. Color Coding: From Subjective Vibes to Objective Energy**

* **Problem**: Linking track colors to subjective "vibe" tags (e.g., "uplifting," "groovy") proved inconsistent. A track with multiple vibes could be assigned a different color depending on which tag the algorithm saw first.
* **Insight**: For a DJ making quick decisions, a track's color should represent a consistent, objective metric. The AI already generates a numerical energy score (1-10).
* **Solution**: The color-coding system was completely redesigned to map directly to the track's **energy level**. A "hot-to-cold" color scale (Pink → Aqua) now provides an at-a-glance, reliable indicator of a track's intensity.

---
### **3. Metadata Priority: Respecting User's Manual Input**

* **Problem**: An automated system risks being too aggressive, overwriting a user's deliberate, manual organization.
* **Insight**: A good tool should assist, not dictate. If a user manually colors a track "Red" to mark it for deletion, the application must respect that decision. This is a core principle of user-centric design.
* **Solution**: A "guard clause" was added to the color-coding logic. Before applying any automatic color, the code first checks if the track is already colored red (`0xFF0000`). If it is, the automated process is skipped for that track, preserving the user's intent.

---
### **4. AI Calibration: Specialized (Niche) vs. Universal (Generic) Energy Scale**

* **Problem**: The AI's 1-10 energy rating was universal, meaning genres like Death Metal would occupy the top end of the scale. This made the ratings less useful for the core user—an electronic music DJ—as their high-energy tracks would rarely receive a 9 or 10.
* **Insight**: "Energy" is a relative, context-dependent metric. A tool designed for a specific user persona should have its AI calibrated to that user's specific context.
* **The Strategic Choice**: We identified a key product decision:
    * **Path A (Niche)**: Contextualize the AI prompt (e.g., "rate this for an electronic DJ"). This makes the tool excellent for the target audience but less useful for edge-case users.
    * **Path B (Generic)**: Keep the prompt universal. The tool works "okay" for everyone but is not perfectly calibrated for anyone.
* **Decision**: We have decided to **defer this choice** until more data can be gathered from a larger "baseline test" to see how the AI currently behaves.

### **5. Genre Formatting: Prioritizing Functionality Over Visual Consistency**

* **Problem**: How should the `primary_genre` and `sub_genres` be formatted in the final XML's `Genre` attribute? Applying the same prefix-based formatting used in the `Comments` field (e.g., `P-Genre: House / S-Genre: French House`) would create visual consistency across the generated tags.
* **Insight**: Through analysis of the Rekordbox software, it was determined that the `Genre` field is not a simple text field; it is **structured data** used for the software's core filtering and searching features. Rekordbox's parser expects a simple, comma-separated list to populate its filterable tags. Any other format would break this essential functionality.
* **Solution**: The decision was made to **prioritize functionality within the target software over aesthetic consistency**. The `Genre` attribute is formatted as a clean, comma-separated string (e.g., `"House, French House, Disco House"`), preserving Rekordbox's native filtering capabilities. This is a key example of a technical constraint dictating the final data output.

### **6. Product Vision: 'Profile-Based' (Multi-Modal) UI**

* **Problem**: A "one-size-fits-all" AI model for music tagging is inherently flawed. The meaning of "energy" and the specific sub-genres are relative and highly dependent on the user's domain (e.g., Electronic vs. Rock vs. Hip Hop). A generic tool is never perfectly optimized for any specific user.
* **Insight**: Instead of forcing a choice between a "niche" tool and a "generic" tool, the application could offer **multiple specialized tools** on a single platform.
* **Solution (Proposed Future Feature)**: The proposed solution is a "profile-based" or "multi-modal" user interface, inspired by simple web tools like `ilovepdf.com`. The main page would present the user with several options (e.g., "Tag Genius for Electronic Music," "Tag Genius for Rock"). By selecting a profile, the user provides a clear context. On the backend, this selection would dynamically load a specifically calibrated AI prompt, ensuring the genre and energy results are perfectly tailored to the user's library. This idea has been added to the future roadmap.

---
## **7. Calibrating the AI's "Energy Level" Score**

### 1. The Problem: The Subjectivity of "Energy"

One of the most critical pieces of metadata for a DJ is a track's "energy level," yet it is also one of the most subjective and difficult to quantify. A DJ's goal is to create a "coherent story" with their playlist, which requires a consistent understanding of energy. This problem was validated by real-world discussions, such as a popular thread on the `/r/DJs` subreddit titled "Identifying energy level".

The community discussion highlighted several key "pain points" that Tag Genius aims to solve:
* DJs don't want to rely solely on subjective "intuition".
* Simple metrics like BPM are unreliable indicators of energy.
* DJs are forced to create their own time-consuming, manual systems using star ratings, colors, or comments to track energy.

The initial output from the AI, while functional, suffered from a similar problem: its "universal" understanding of energy was not specific enough for a DJ's needs.

### 2. The Hypothesis

Our hypothesis was that the AI's performance could be significantly improved through **iterative prompt engineering**. We believed that by providing the AI with a clearer, more context-specific definition of the 1-10 energy scale—calibrated specifically for an electronic music DJ—we could "stretch" its ratings to be more decisive and accurate.

### 3. The Methodology: A Data-Driven Approach

To test our hypothesis, we developed a systematic, data-driven calibration process:

1.  **Creating a "Ground Truth":** The user, acting as the domain expert, manually assigned a 1-5 star rating to a diverse playlist of 21 electronic tracks. This created an expert "answer key" to serve as a benchmark for the AI's performance.

2.  **Developing a Measurement Tool:** A custom Python script (`comparison_ratings.py`) was created to automate the analysis. The script takes the user's "ground truth" XML and the AI-generated XML as input and produces a side-by-side comparison, along with key metrics: **Exact Match %** and **Average Difference**.

3.  **Iterative Testing:** We conducted three full test cycles. After each cycle, the quantitative results were analyzed to identify the AI's specific weaknesses, and the prompt was adjusted to target those weaknesses directly.

### 4. The Results: A Measurable Improvement

The data from the three test cycles showed clear, significant improvement with each iteration.

| Test Cycle | Prompt Version | Exact Matches | Avg. Difference | Key Finding |
| :--- | :--- | :--- | :--- | :--- |
| **Test 1** | Initial Prompt | 7 / 21 (33%) | 1.05 stars | Ratings were "compressed" to the middle; AI avoided low scores. |
| **Test 2** | Added Low/High Definitions | 9 / 21 (43%) | 0.95 stars | High-end accuracy improved, but low-end was still overrated. |
| **Test 3** | Added Forceful Low-End Instruction | **11 / 21 (52%)** | **0.81 stars** | **Success!** Significant improvement in mid-range and overall accuracy. |

The iterative process successfully increased the AI's exact-match accuracy by nearly **20 percentage points** and reduced the average error rate.

### 5. Conclusion & Final Decision

The data-driven, iterative prompt engineering process was a clear success. While a minor bias against the very lowest 1-star ratings remains, the model's overall accuracy and reliability were drastically improved.

The decision was made to **accept the final prompt as the calibrated model for the MVP.** With over 52% exact matches and an average error of less than one star, the feature provides immense value and a massive time-saving improvement over manual tagging, even with its minor, known limitation. This process serves as a key case study in the importance of systematic testing and refinement when working with large language models.