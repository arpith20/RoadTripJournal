# 🚗 TripJournal

TripJournal is a high-performance Python utility that transforms raw GPS tracking files (`.gpx`) into beautiful, interactive, and completely self-contained analytics web journals (`index.html`). 

Engineered with a sleek, modern glassmorphic sidebar dashboard, it consolidates your entire journey's metrics, daily timelines, and velocity profiles into a clean, unified map interface.

---

## ✨ Core Features

* **⚡ Speed-Profile Heatmaps:** Dynamically parses track logs and chunks paths into color-coded velocity vectors (Green = Cruise, Yellow = Alert, Red = High Speed).
* **🧩 Unified Dashboard & Timeline Sidebar:** A custom bottom-left panel containing a global **Journey Dashboard** (Total Distance, Cumulative Time, Day Counters) stacked cleanly above an expandable **Trip Timeline**.
* **🎨 Click-to-Expand Theme Drawer:** An isolated, non-jarring floating button in the bottom-right corner allowing users to switch dynamically between Light Theme, Dark Theme, Satellite View, and Standard Street View without any page reloads.
* **📉 Smart Path Simplification:** Leverages the Ramer-Douglas-Peucker algorithm with a customizable cross-track error threshold to compress files by up to 90% without visible detail loss, keeping browser canvas rendering fluid and fast.
* **⚙️ Dual-Pipeline Input Parsing:** * *Recorded GPS Logs:* Generates elapsed time, average speed, maximum speed, and color-chunked velocity profiles.
  * *Planned/Timeless Routes:* Gracefully recovers GPX exports without active timestamps (e.g., manually drafted route maps), calculating raw distance metrics and drawing them as elegant slate-gray reference lines (`#94a3b8`).
* **📅 Automatic Multi-File Consolidation:** Intelligently merges multiple `.gpx` files recorded on the same calendar day into a single interactive card timeline entry while automatically discounting engine-off resting gaps.
* **🛠️ Modern Desktop UI Enhancements:** Global master toggles (**✓ Select All / ✕ Deselect All**), minimizable timeline drawers with rotating chevrons, explicit checkbox styling overrides, and viewport boundary auto-framing.

---

## 🚀 Getting Started

### Prerequisites

Ensure you have Python 3.10+ installed along with the required parsing and visualization libraries:

```bash
pip install gpxpy folium branca
```

### File Architecture

Place your target tracking logs inside a designated directory. The script handles corrupt, empty, or un-timed files without breaking execution pipelines.

```text
TripJournal/
│
├── generate_html.py       # Main production script
├── README.md                 # Project Documentation
└── GPXLogs/                  # Directory containing input GPX logs
    ├── day1_morning.gpx
    ├── day1_afternoon.gpx
    ├── route_plan_manual.gpx
    └── day2_highway.gpx
```

### Execution

1. Open `generate_html.py`.
2. Scroll to the bottom execution block. The script is pre-configured to look for a folder named `GPXLogs` sitting in the exact same directory where the script is located, meaning you can execute it from anywhere.
3. Run the script from your terminal:
   ```bash
   python generate_html.py
   ```
4. Double-click the newly compiled `index.html` file to view your journey in any web browser.

---

## 🛠️ How It Works (Behind the Scenes)

### Vector Chunking & Smoothing
Instead of forcing the browser to render one massive, performance-heavy path line, the parser partitions tracking data into geographic velocity zones based on sudden accelerations or decelerations. Straight lines and long highway runs are automatically stripped of duplicate tracking points via a 4-meter cross-track threshold constraint. This ensures a 300 km track loads as instantly as a 5 km track.

### CSS Injection Core
The user interface is entirely decoupled from default Leaflet interface parameters. Custom responsive viewports are injected dynamically using strict CSS variables, native hardware acceleration rules, and modern CSS layout engines (Flexbox row-column controls and explicit grid spacing configurations). This design eliminates legacy layout rendering conflicts or misalignments completely.

---

## 📄 License

This project is open-source and available under the **MIT License**. Feel free to customize the design layouts, color tokens, and telemetry formatting options to map out your own adventures!