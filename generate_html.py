import os
import math
from datetime import datetime
from collections import defaultdict
import gpxpy
import folium
import branca.colormap as cm

def calculate_speed(p1, p2):
    """Calculates speed between two sequential points in km/h."""
    if not p1.time or not p2.time:
        return 0.0
    time_delta = (p2.time - p1.time).total_seconds()
    if time_delta <= 0:
        return 0.0
    return (p1.distance_2d(p2) / time_delta) * 3.6

def format_duration(seconds):
    """Converts a raw count of seconds into a human-readable Xh Ym string."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours}h {minutes}m"

def process_gpx_to_chunked_days(folder_path):
    """Parses GPX files, handles timeless files gracefully, and chunks speed profiles."""
    daily_data = defaultdict(lambda: {
        'chunks': [],        
        'full_coords': [],   
        'max_speed': 0.0,
        'distance_m': 0.0,
        'total_seconds': 0.0
    })
    
    if not os.path.exists(folder_path):
        print(f"Error: Directory '{folder_path}' not found.")
        return {}

    print(f"🚀 Step 1: Parsing GPX logs from target directory: {folder_path}...")
    for file_name in os.listdir(folder_path):
        if not file_name.lower().endswith('.gpx'):
            continue
            
        file_path = os.path.join(folder_path, file_name)
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                gpx = gpxpy.parse(f)
            except Exception as e:
                print(f"Skipping corrupt file {file_name}: {e}")
                continue
                
        for track in gpx.tracks:
            for segment in track.segments:
                segment.simplify(max_distance=4.0) 
                track_points = segment.points
                if len(track_points) < 2:
                    continue
                
                # Check if this specific file possesses timestamp streams
                has_time = track_points[0].time is not None and track_points[-1].time is not None
                
                if has_time:
                    segment_date = track_points[0].time.date()
                else:
                    # Fallback: Use file modified calendar date if GPS timestamps are empty
                    segment_date = datetime.fromtimestamp(os.path.getmtime(file_path)).date()
                
                day_bucket = daily_data[segment_date]
                
                # PIPELINE A: Handle Timeless/Planned Routes
                if not has_time:
                    chunk_coords = [(p.latitude, p.longitude) for p in track_points]
                    day_bucket['full_coords'].extend(chunk_coords)
                    
                    # Accumulate path travel distance exclusively
                    for i in range(len(track_points) - 1):
                        day_bucket['distance_m'] += track_points[i].distance_2d(track_points[i+1])
                    
                    # Store as a single chunk using -1.0 as a flag for timeless data
                    day_bucket['chunks'].append((chunk_coords, -1.0))
                    continue
                
                # PIPELINE B: Handle Standard Recorded GPS Logs
                day_bucket['total_seconds'] += (track_points[-1].time - track_points[0].time).total_seconds()
                
                current_chunk_coords = []
                current_speed_bucket = None
                speeds_in_chunk = []
                
                for i in range(len(track_points) - 1):
                    p1 = track_points[i]
                    p2 = track_points[i+1]
                    
                    coord1 = (p1.latitude, p1.longitude)
                    coord2 = (p2.latitude, p2.longitude)
                    
                    if i == 0:
                        day_bucket['full_coords'].append(coord1)
                    day_bucket['full_coords'].append(coord2)
                    
                    dist = p1.distance_2d(p2)
                    day_bucket['distance_m'] += dist
                    
                    speed = calculate_speed(p1, p2)
                    if speed >= 160: 
                        speed = day_bucket['max_speed']
                    
                    if speed > day_bucket['max_speed']:
                        day_bucket['max_speed'] = speed
                        
                    speed_bucket = round(speed / 12.0) * 12
                    
                    if current_speed_bucket is None:
                        current_speed_bucket = speed_bucket
                        current_chunk_coords = [coord1, coord2]
                        speeds_in_chunk = [speed]
                    elif speed_bucket == current_speed_bucket:
                        current_chunk_coords.append(coord2)
                        speeds_in_chunk.append(speed)
                    else:
                        avg_chunk_speed = sum(speeds_in_chunk) / len(speeds_in_chunk)
                        day_bucket['chunks'].append((current_chunk_coords, avg_chunk_speed))
                        
                        current_speed_bucket = speed_bucket
                        current_chunk_coords = [coord1, coord2]
                        speeds_in_chunk = [speed]
                        
                if current_chunk_coords:
                    avg_chunk_speed = sum(speeds_in_chunk) / len(speeds_in_chunk) if speeds_in_chunk else 0
                    day_bucket['chunks'].append((current_chunk_coords, avg_chunk_speed))
                
    return daily_data

def build_production_site(daily_data, output_html="index.html"):
    """Generates an optimized web map with support for rendering timeless tracks."""
    if not daily_data:
        print("No valid tracking records extracted. Aborting.")
        return

    sorted_dates = sorted(daily_data.keys())
    all_coords = []
    global_max_speed = 0.0
    grand_total_distance_km = 0.0
    grand_total_seconds = 0.0
    
    for date in sorted_dates:
        day = daily_data[date]
        all_coords.extend(day['full_coords'])
        grand_total_distance_km += (day['distance_m'] / 1000.0)
        grand_total_seconds += day['total_seconds']
        if day['max_speed'] > global_max_speed:
            global_max_speed = day['max_speed']

    max_display_speed = max(int(math.ceil(global_max_speed / 10.0) * 10), 20)

    mymap = folium.Map(tiles=None, prefer_canvas=True)
    
    # Base Map configurations
    folium.TileLayer("Cartodb Positron", name="☀️ Light Theme", control=True, show=True).add_to(mymap)
    folium.TileLayer("Cartodb dark_matter", name="🌙 Dark Theme", control=True, show=False).add_to(mymap)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="🛰️ Satellite View", control=True, show=False
    ).add_to(mymap)
    folium.TileLayer("OpenStreetMap", name="🗺️ Street View", control=True, show=False).add_to(mymap)

    colormap = cm.LinearColormap(
        colors=['#2ecc71', '#f1c40f', '#e74c3c'],
        vmin=0, vmax=max_display_speed,
        caption="Speed Profile (km/h)"
    )
    colormap.add_to(mymap)

    print("🎨 Step 2: Generating vector overlays and injector stylesheets...")
    for day_idx, date in enumerate(sorted_dates, 1):
        day = daily_data[date]
        formatted_date = date.strftime('%b %d, %Y')
        day_dist_km = day['distance_m'] / 1000.0
        
        # Safe metric parsing string definitions block
        if day['total_seconds'] > 0:
            day_avg_speed = (day_dist_km / (day['total_seconds'] / 3600.0))
            avg_speed_str = f"{day_avg_speed:.1f} km/h"
            max_speed_str = f"{day['max_speed']:.1f} km/h" 
            duration_str = format_duration(day['total_seconds'])
        else:
            avg_speed_str = "N/A"
            max_speed_str = "N/A"
            duration_str = "N/A"

        layer_title = (
            f"<span class='timeline-day-title'>Day {day_idx:02d} • {formatted_date}</span>"
            f"<span class='timeline-day-metrics'>"
            f"  {day_dist_km:.1f} km • Time: {duration_str} • Avg: {avg_speed_str} • Max: {max_speed_str}"
            f"</span>"
        )
        
        day_feature_group = folium.FeatureGroup(name=layer_title, overlay=True, control=True)

        for points, avg_chunk_speed in day['chunks']:
            if avg_chunk_speed < 0:
                color_hex = "#94a3b8"  
                section_speed_text = "N/A"
            else:
                color_hex = colormap(min(avg_chunk_speed, max_display_speed))
                section_speed_text = f"{avg_chunk_speed:.1f} km/h"
            
            tooltip_html = f"""
            <div style="font-family: 'Segoe UI', sans-serif; width: 250px; font-size: 13px; color: #333;">
                <h4 style="margin: 0 0 6px 0; color: #2c3e50; border-bottom: 2px solid #34495e; padding-bottom: 4px;">🚗 <b>Day {day_idx} Overview</b></h4>
                <table style="width: 100%; border-collapse: collapse; line-height: 1.5;">
                    <tr><td style="color: #7f8c8d;"><b>Date:</b></td><td style="text-align: right;">{formatted_date}</td></tr>
                    <tr><td style="color: #7f8c8d;"><b>Day's Distance:</b></td><td style="text-align: right; font-weight: bold;">{day_dist_km:.1f} km</td></tr>
                    <tr><td style="color: #7f8c8d;"><b>Day's Duration:</b></td><td style="text-align: right; font-weight: bold;">{duration_str}</td></tr>
                    <tr><td style="color: #27ae60;"><b>Day's Avg Speed:</b></td><td style="text-align: right;">{avg_speed_str}</td></tr>
                    <tr><td style="color: #c0392b;"><b>Day's Max Speed:</b></td><td style="text-align: right; font-weight: bold;">{max_speed_str}</td></tr>
                    <tr style="border-top: 2px solid #3b82f6; background-color: #f8fafc;">
                        <td style="color: #3b82f6; padding: 4px;"><b>⚡ Section Cruise Speed:</b></td>
                        <td style="text-align: right; color: #3b82f6; font-weight: bold; padding: 4px;">{section_speed_text}</td>
                    </tr>
                </table>
            </div>
            """
            folium.PolyLine(locations=points, color=color_hex, weight=5, opacity=0.85, tooltip=folium.Tooltip(tooltip_html, sticky=True)).add_to(day_feature_group)

        day_feature_group.add_to(mymap)

    folium.LayerControl(collapsed=False).add_to(mymap)

    # UI Glassmorphism Layout Stylesheet
    ui_css_override = """
    <style>
        .leaflet-control-layers {
            position: fixed !important; bottom: 30px !important; left: 30px !important; top: auto !important; right: auto !important;
            background: rgba(255, 255, 255, 0.95) !important; backdrop-filter: blur(12px) webkit-backdrop-filter(12px);
            border: 1px solid rgba(226, 232, 240, 0.8) !important; border-radius: 16px !important; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08) !important;
            padding: 16px !important; font-family: 'Segoe UI', system-ui, -apple-system, sans-serif !important;
            width: 380px !important; max-height: 520px !important; display: flex !important; flex-direction: column !important; z-index: 10000 !important; box-sizing: border-box !important; transition: max-height 0.25s ease;
        }
        .leaflet-control-layers-separator { display: none !important; }
        .leaflet-control-layers-overlays {
            max-height: 280px !important; overflow-y: auto !important; padding-right: 4px; margin-top: 4px; opacity: 1;
            transition: max-height 0.22s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.15s ease, margin 0.22s ease !important;
        }
        .timeline-collapsed .leaflet-control-layers-overlays,
        .timeline-collapsed .timeline-toggle-row {
            max-height: 0 !important; opacity: 0 !important; margin-top: 0 !important; margin-bottom: 0 !important;
            padding-top: 0 !important; padding-bottom: 0 !important; overflow: hidden !important; pointer-events: none !important; border: none !important;
        }
        .timeline-collapsed #timeline-chevron { transform: rotate(-90deg) !important; }
        .leaflet-control-layers-overlays label {
            margin-bottom: 8px !important; padding: 12px 14px !important; background: #ffffff !important; border: 2px solid #e2e8f0 !important; border-radius: 12px !important; 
            display: block !important; cursor: pointer !important; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important; box-sizing: border-box !important; width: 100% !important;
        }
        .leaflet-control-layers-overlays label > span {
            display: flex !important; flex-direction: column !important; align-items: flex-start !important; justify-content: center !important; float: none !important; margin: 0 !important; padding: 0 !important; width: 100% !important;
        }
        .leaflet-control-layers-overlays label:has(input:checked) {
            background-color: #eff6ff !important; border-color: #3b82f6 !important; box-shadow: 0 4px 12px rgba(59, 130, 246, 0.06) !important; opacity: 1 !important;
        }
        .leaflet-control-layers-overlays label:has(input:checked) .timeline-day-title { color: #2563eb !important; }
        .leaflet-control-layers-overlays label:not(:has(input:checked)) { background-color: #ffffff !important; border-color: #f1f5f9 !important; opacity: 0.55 !important; }
        .leaflet-control-layers-overlays label:hover { border-color: #cbd5e1 !important; opacity: 1 !important; transform: translateY(-1px); }
        .timeline-day-title { font-weight: 700 !important; font-size: 13px !important; color: #1e293b !important; line-height: 1.2 !important; display: block !important; white-space: nowrap !important; }
        .timeline-day-metrics { font-size: 11px !important; color: #64748b !important; margin-top: 4px !important; font-weight: 500 !important; line-height: 1.2 !important; display: block !important; white-space: nowrap !important; }
        .leaflet-control-layers-overlays input.leaflet-control-layers-selector[type="checkbox"] { display: none !important; }
        
        .leaflet-control-layers-base {
            position: fixed !important; bottom: 30px !important; right: 30px !important; z-index: 9999 !important;
            background: rgba(255, 255, 255, 0.96) !important; backdrop-filter: blur(12px) webkit-backdrop-filter(12px); border: 1px solid rgba(226, 232, 240, 0.8) !important;
            border-radius: 12px !important; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08) !important; padding: 0 !important; width: 44px !important; height: 44px !important;
            overflow: hidden !important; transition: box-shadow 0.2s ease !important; cursor: pointer !important; display: flex !important; flex-direction: column !important; align-items: center !important; justify-content: center !important;
        }
        .leaflet-control-layers-base:hover { box-shadow: 0 8px 20px rgba(0, 0, 0, 0.12) !important; }
        .leaflet-control-layers-base::before { content: "🎨" !important; font-size: 18px !important; display: block !important; line-height: 44px !important; text-align: center !important; width: 44px !important; height: 44px !important; flex-shrink: 0 !important; }
        .leaflet-control-layers-base label { display: none !important; }
        .leaflet-control-layers-base.active-click { width: 220px !important; height: auto !important; padding: 16px !important; align-items: stretch !important; justify-content: flex-start !important; cursor: default !important; }
        .leaflet-control-layers-base.active-click::before { content: "🎨 Map Style" !important; font-weight: 700 !important; color: #1e293b !important; font-size: 13px !important; line-height: normal !important; text-align: left !important; width: auto !important; height: auto !important; margin-bottom: 12px !important; }
        .leaflet-control-layers-base.active-click label { display: flex !important; width: auto !important; height: auto !important; margin-bottom: 6px !important; padding: 8px 12px !important; background: #f8fafc; border: 1px solid #e2e8f0 !important; animation: menuFadeIn 0.2s ease-out forwards !important; }
        .leaflet-control-zoom { position: fixed !important; bottom: 90px !important; right: 30px !important; top: auto !important; left: auto !important; margin: 0 !important; z-index: 9999 !important; background: rgba(255, 255, 255, 0.96) !important; backdrop-filter: blur(12px) webkit-backdrop-filter(12px); border: 1px solid rgba(226, 232, 240, 0.8) !important; border-radius: 12px !important; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08) !important; overflow: hidden !important; display: flex !important; flex-direction: column !important; }
        .leaflet-control-zoom a { background: rgba(255, 255, 255, 0.96) !important; color: #475569 !important; border: none !important; border-bottom: 1px solid #edf2f7 !important; font-weight: 600 !important; transition: background 0.15s, color 0.15s !important; text-decoration: none !important; }
        .leaflet-control-zoom a:last-child { border-bottom: none !important; }
        .leaflet-control-zoom a:hover { background: #f8fafc !important; color: #1e293b !important; text-decoration: none !important; }
        .leaflet-control-layers-base label:hover { background: #ffffff; border-color: #cbd5e1; color: #1e293b !important; transform: translateY(-1px); box-shadow: 0 4px 6px -1px rgba(0,0,0,0.03); }
        .leaflet-control-layers-selector[type="radio"] { appearance: none; -webkit-appearance: none; width: 18px; height: 18px; border: 2px solid #cbd5e1; border-radius: 50%; margin-right: 12px !important; position: relative; background: #ffffff; flex-shrink: 0; cursor: pointer; transition: all 0.2s ease; }
        .leaflet-control-layers-selector[type="radio"]:checked { border-color: #3b82f6; }
        .leaflet-control-layers-selector[type="radio"]:checked::after { content: ''; position: absolute; width: 8px; height: 8px; background-color: #3b82f6; border-radius: 50%; top: 3px; left: 3px; }
    </style>
    """
    mymap.get_root().header.add_child(folium.Element(ui_css_override))
    mymap.get_root().header.add_child(folium.Element("<title>Trip Journal</title>"))

    # JavaScript integration controller 
    ui_javascript_injector = f"""
    <script>
    function compileUnifiedLeftDashboard() {{
        var masterPanel = document.querySelector('.leaflet-control-layers');
        var stylePanel = document.querySelector('.leaflet-control-layers-base');
        
        if (masterPanel && stylePanel) {{
            var headerBlock = document.createElement('div');
            headerBlock.style.width = '100%';
            headerBlock.style.boxSizing = 'border-box';
            headerBlock.innerHTML = `
                <h4 style="margin:0 0 10px 0; color:#1e293b; font-size:15px; border-bottom: 2px solid #3b82f6; padding-bottom: 6px;">
                    🚀 <b>Journey Dashboard</b>
                </h4>
                <table style="width:100%; border-collapse:collapse; line-height:1.7; font-size:13px; margin-bottom: 12px;">
                    <tr><td style="color:#64748b;"><b>Total Timeline:</b></td><td style="text-align:right; font-weight:bold; color:#1e293b;">{len(sorted_dates)} Days</td></tr>
                    <tr><td style="color:#64748b;"><b>Total Time:</b></td><td style="text-align:right; font-weight:bold; color:#1e293b;">{format_duration(grand_total_seconds)}</td></tr>
                    <tr style="font-size: 14px; border-top: 1px solid #edf2f7;"><td style="color:#64748b; padding-top:6px;"><b>Grand Total:</b></td><td style="text-align:right; font-weight:bold; color:#3b82f6; padding-top:6px;">{grand_total_distance_km:.1f} km</td></tr>
                </table>
            `;
            masterPanel.insertBefore(headerBlock, masterPanel.firstChild);

            var formList = masterPanel.querySelector('.leaflet-control-layers-list');
            var overlaysContainer = masterPanel.querySelector('.leaflet-control-layers-overlays');
            
            if (formList && overlaysContainer) {{
                var timelineHeader = document.createElement('div');
                timelineHeader.id = 'timeline-toggle-header';
                timelineHeader.style.display = 'flex';
                timelineHeader.style.justifyContent = 'space-between';
                timelineHeader.style.alignItems = 'center';
                timelineHeader.style.marginTop = '4px';
                timelineHeader.style.paddingTop = '12px';
                timelineHeader.style.borderTop = '1px solid #e2e8f0';
                timelineHeader.style.cursor = 'pointer';
                timelineHeader.style.userSelect = 'none';
                timelineHeader.innerHTML = `
                    <span style="font-weight: 700; color: #1e293b; font-size: 13px;">🗺️ Trip Timeline</span>
                    <span id="timeline-chevron" style="font-size: 11px; color: #64748b; transition: transform 0.2s ease; display: inline-block;">▼</span>
                `;
                formList.insertBefore(timelineHeader, overlaysContainer);

                var toggleRow = document.createElement('div');
                toggleRow.className = 'timeline-toggle-row';
                toggleRow.style.display = 'flex';
                toggleRow.style.gap = '14px';
                toggleRow.style.marginTop = '8px';
                toggleRow.style.marginBottom = '12px';
                toggleRow.style.paddingLeft = '2px';
                toggleRow.style.transition = 'max-height 0.22s ease, opacity 0.15s ease, margin 0.22s ease';
                toggleRow.innerHTML = `
                    <span id="map-select-all" style="font-size: 11px; color: #3b82f6; cursor: pointer; font-weight: 600; user-select: none;">✓ Select All</span>
                    <span id="map-deselect-all" style="font-size: 11px; color: #64748b; cursor: pointer; font-weight: 600; user-select: none;">✕ Deselect All</span>
                `;
                formList.insertBefore(toggleRow, overlaysContainer);

                timelineHeader.addEventListener('click', function() {{
                    masterPanel.classList.toggle('timeline-collapsed');
                }});
                
                document.getElementById('map-select-all').addEventListener('click', function(ev) {{
                    ev.stopPropagation();
                    var checkboxes = overlaysContainer.querySelectorAll('input[type="checkbox"]');
                    checkboxes.forEach(function(cb) {{
                        if (!cb.checked) {{
                            cb.click();
                        }}
                    }});
                }});
                
                document.getElementById('map-deselect-all').addEventListener('click', function(ev) {{
                    ev.stopPropagation();
                    var checkboxes = overlaysContainer.querySelectorAll('input[type="checkbox"]');
                    checkboxes.forEach(function(cb) {{
                        if (cb.checked) {{
                            cb.click();
                        }}
                    }});
                }});
            }}

            stylePanel.addEventListener('click', function(event) {{
                if (event.target.tagName === 'INPUT' || event.target.closest('label')) {{
                    return;
                }}
                this.classList.toggle('active-click');
                event.stopPropagation();
            }});
            
            document.addEventListener('click', function(event) {{
                if (!stylePanel.contains(event.target)) {{
                    stylePanel.classList.remove('active-click');
                }}
            }});
        }} else {{
            setTimeout(compileUnifiedLeftDashboard, 100);
        }}
    }}
    compileUnifiedLeftDashboard();
    </script>
    """
    mymap.get_root().html.add_child(folium.Element(ui_javascript_injector))

    # Top Center Header Title Banner
    title_html = """
    <div style="position: fixed; 
                top: 25px; left: 50%; transform: translateX(-50%); width: auto; max-width: 85%;
                z-index:9999; font-family: 'Segoe UI', sans-serif;
                background-color: rgba(255, 255, 255, 0.95); padding: 12px 28px;
                border-radius: 30px; box-shadow: 0 10px 25px rgba(0,0,0,0.06);
                border: 1px solid #e2e8f0; backdrop-filter: blur(8px);
                text-align: center; white-space: nowrap;">
        <h1 style="margin: 0; color: #1e293b; font-size: 18px; font-weight: 700; letter-spacing: -0.5px;">
            🚗 Our Adventure
        </h1>
    </div>
    """
    mymap.get_root().html.add_child(folium.Element(title_html))

    min_lat, max_lat = min(c[0] for c in all_coords), max(c[0] for c in all_coords)
    min_lon, max_lon = min(c[1] for c in all_coords), max(c[1] for c in all_coords)
    mymap.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])

    mymap.save(output_html)
    print(f"🎉 Success! Interactive map exported successfully to: '{output_html}'")

if __name__ == "__main__":
    # --- FIXED: ABSOLUTE RELATIVE SCRIPT ANCHORING ---
    # Finds the folder containing this python file, then targets "GPXLogs" right next to it.
    SCRIPT_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
    TARGET_GPX_FOLDER = os.path.join(SCRIPT_DIRECTORY, "GPXLogs")
    
    data_matrix = process_gpx_to_chunked_days(TARGET_GPX_FOLDER)
    build_production_site(data_matrix, output_html="index.html")