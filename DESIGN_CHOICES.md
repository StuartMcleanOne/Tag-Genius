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