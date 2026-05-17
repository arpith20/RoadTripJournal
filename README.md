🚗 Trip Journal
Trip Journal is a high-performance Python utility that transforms raw GPS tracking files (.gpx) into a beautiful, interactive, and completely self-contained analytics webpage (index.html).

Designed with a sleek, modern glassmorphic interface, it consolidates your entire journey's metrics, daily timelines, and velocity profiles into a single unified workspace.

✨ Core Features
⚡ Speed-Profile Heatmaps: Dynamically parses track logs and chunks lines into color-coded velocity vectors (Green = Cruise, Yellow = Alert, Red = High Speed).

🧩 Unified Analytics Control Center: A custom bottom-left sidebar containing a global Journey Dashboard (Total Distance, Cumulative Time, Day Counters) stacked cleanly above an expandable Trip Timeline.

🎨 Click-to-Expand Theme Drawer: An isolated, non-jarring floating button in the bottom-right corner allowing users to cycle between Light Theme, Dark Theme, Satellite View, and Standard Streets.

📉 Smart Path Simplification: Leverages the Ramer-Douglas-Peucker algorithm with a customizable cross-track error threshold to compress files by up to 90% without visible fidelity loss, keeping rendering performance fluid.

⚙️ Dual-Pipeline Input Parsing: * Recorded Data: Generates time, average speed, maximum speed, and vector calculations.

Planned/Timeless Routes: Gracefully handles GPX exports without active timestamps (e.g., manually drafted routes), calculating raw distance metrics and drawing them as sublte slate-gray reference lines.

📅 Automatic Multi-File Merging: Intelligently combines multiple .gpx files from the same calendar day into a single interactive card timeline entry while ignoring stationary down-time gaps.

🛠️ Desktop UI Conveniences: Global master toggles (Select All / Deselect All), minimizable timeline drawers, non-underline button styles, and viewport boundary auto-framing.

🚀 Getting Started
Prerequisites
Ensure you have Python 3.10+ installed along with the required parsing and visualization libraries:

Bash
pip install gpxpy folium branca
File Architecture
Place your target tracking logs inside a designated directory. The script handles corrupt or un-timed files without crashing execution pipelines.

Plaintext
YourProject/
│
├── generate_heatmap.py       # Main production script
├── README.md                 # Project Documentation
└── GPSLogs/                  # Directory containing input files
    ├── day1_morning.gpx
    ├── day1_afternoon.gpx
    ├── route_plan_manual.gpx
    └── day2_highway.gpx
Execution
Open generate_heatmap.py.

Scroll to the bottom execution block and update your absolute file paths:

Python
if __name__ == "__main__":
    TARGET_GPX_FOLDER = r"C:\Your\Path\To\GPSLogs"
    data_matrix = process_gpx_to_chunked_days(TARGET_GPX_FOLDER)
    build_production_site(data_matrix, output_html="index.html")
Run the script from your terminal:

Bash
python generate_heatmap.py
Double-click the newly compiled index.html file to view your journey in any web browser.

🛠️ How It Works (Behind the Scenes)
Vector Chunking & Smoothing
Instead of rendering one massive, performance-heavy path line, the parser partitions tracking data into geographic velocity zones based on sudden accelerations or decelerations. Straight lines and long highway runs are automatically stripped of duplicate tracking points via:

Python
segment.simplify(max_distance=4.0)
This ensures a 300 km track loads as quickly as a 5 km track.

CSS Injection Core
The interface is entirely decoupled from default Leaflet interface parameters. Custom responsive viewports are injected dynamically using strict CSS variables, native hardware acceleration rules, and browser feature queries (:has()). This design completely avoids legacy layer conflicts or vertical misalignments.

📄 License
This project is open-source and available under the MIT License. Feel free to customize the design layouts, layout anchors, and telemetry formatting vectors to suit your adventures!