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
* **Solution**: The color-coding system was completely redesigned to map directly to the track's **energy level**. A "hot-to-cold" color scale (Pink → Orange → Yellow → Green → Aqua) now provides an at-a-glance, reliable indicator of a track's intensity, perfectly complementing the 1-5 star rating.

---
### **3. Metadata Priority: Respecting User's Manual Input**

* **Problem**: An automated system risks being too aggressive, overwriting a user's deliberate, manual organization.
* **Insight**: A good tool should assist, not dictate. If a user manually colors a track "Red" to mark it for deletion, the application must respect that decision. This is a core principle of user-centric design.
* **Solution**: A "guard clause" was added to the color-coding logic. Before applying any automatic color, the code first checks if the track is already colored red (`0xFF0000`). If it is, the automated process is skipped for that track, preserving the user's intent.