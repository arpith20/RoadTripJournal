import os
import math
from datetime import datetime
from collections import defaultdict
import gpxpy
import folium
import branca.colormap as cm
from PIL import Image, ImageOps

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

def extract_image_metadata(image_path):
    """Extracts geographic coordinates and capture time from image EXIF headers."""
    try:
        with Image.open(image_path) as img:
            exif = img._getexif()
            if not exif:
                return None
            
            lat_ref = exif.get(1)
            lat_data = exif.get(2)
            lon_ref = exif.get(3)
            lon_data = exif.get(4)
            dt_data = exif.get(36867) or exif.get(306)

            if not (lat_ref and lat_data and lon_ref and lon_data):
                gps_dict = exif.get(34853)
                if isinstance(gps_dict, dict):
                    lat_ref = gps_dict.get(1)
                    lat_data = gps_dict.get(2)
                    lon_ref = gps_dict.get(3)
                    lon_data = gps_dict.get(4)
                else:
                    return None

            if not (lat_ref and lat_data and lon_ref and lon_data):
                return None

            def convert_to_degrees(value):
                d = float(value[0])
                m = float(value[1])
                s = float(value[2])
                return d + (m / 60.0) + (s / 3600.0)

            lat = convert_to_degrees(lat_data)
            if lat_ref in ['S', b'S']: lat = -lat
            lon = convert_to_degrees(lon_data)
            if lon_ref in ['W', b'W']: lon = -lon

            dt_obj = None
            if dt_data:
                if isinstance(dt_data, bytes):
                    dt_data = dt_data.decode('utf-8')
                try:
                    dt_obj = datetime.strptime(dt_data.strip(), '%Y:%m:%d %H:%M:%S')
                except ValueError:
                    pass
            
            if not dt_obj:
                dt_obj = datetime.fromtimestamp(os.path.getmtime(image_path))

            return {"lat": lat, "lon": lon, "datetime": dt_obj}
    except Exception:
        return None

def process_images_folder(image_folder, thumb_folder):
    """Scans image folder, completely clears the thumbnail directory, and rebuilds all active thumbnails."""
    valid_photos = []
    if not os.path.exists(image_folder):
        return []
    
    os.makedirs(thumb_folder, exist_ok=True)
    
    print("🧹 Step 1.2: Wiping thumbnail directory completely for a fresh rebuild...")
    for filename in os.listdir(thumb_folder):
        file_path = os.path.join(thumb_folder, filename)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"  Warning: Could not remove cached file {filename}: {e}")

    active_source_images = {f for f in os.listdir(image_folder) if f.lower().endswith(('.jpg', '.jpeg', '.png'))}

    print("📷 Step 1.5: Analyzing telemetry data and rebuilding map thumbnails from scratch...")
    for file_name in active_source_images:
        file_path = os.path.join(image_folder, file_name)
        thumb_path = os.path.join(thumb_folder, file_name)
        
        meta = extract_image_metadata(file_path)
        if meta:
            try:
                with Image.open(file_path) as img:
                    img = ImageOps.exif_transpose(img)
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    img.thumbnail((120, 120))
                    img.save(thumb_path, "JPEG", quality=85)
            except Exception as e:
                print(f"  Skipping thumbnail generation for {file_name}: {e}")
                continue

            valid_photos.append({
                "filename": file_name,
                "thumb_url": f"thumbnails/{file_name}",
                "full_url": f"images/{file_name}",
                "lat": meta["lat"],
                "lon": meta["lon"],
                "datetime": meta["datetime"],
                "formatted_time": meta["datetime"].strftime('%b %d, %Y • %I:%M %p')
            })
            
    valid_photos.sort(key=lambda x: x["datetime"])
    return valid_photos

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
                
                has_time = track_points[0].time is not None and track_points[-1].time is not None
                if has_time:
                    segment_date = track_points[0].time.date()
                else:
                    segment_date = datetime.fromtimestamp(os.path.getmtime(file_path)).date()
                
                day_bucket = daily_data[segment_date]
                
                if not has_time:
                    chunk_coords = [(p.latitude, p.longitude) for p in track_points]
                    day_bucket['full_coords'].extend(chunk_coords)
                    for i in range(len(track_points) - 1):
                        day_bucket['distance_m'] += track_points[i].distance_2d(track_points[i+1])
                    day_bucket['chunks'].append((chunk_coords, -1.0))
                    continue
                
                day_bucket['total_seconds'] += (track_points[-1].time - track_points[0].time).total_seconds()
                current_chunk_coords = []
                current_speed_bucket = None
                speeds_in_chunk = []
                
                for i in range(len(track_points) - 1):
                    p1 = track_points[i]
                    p2 = track_points[i+1]
                    coord1 = (p1.latitude, p1.longitude)
                    coord2 = (p2.latitude, p2.longitude)
                    
                    if i == 0: day_bucket['full_coords'].append(coord1)
                    day_bucket['full_coords'].append(coord2)
                    
                    dist = p1.distance_2d(p2)
                    day_bucket['distance_m'] += dist
                    
                    speed = calculate_speed(p1, p2)
                    if speed >= 160: speed = day_bucket['max_speed']
                    if speed > day_bucket['max_speed']: day_bucket['max_speed'] = speed
                        
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

def build_production_site(daily_data, photo_data, output_html="index.html"):
    """Generates an optimized web map featuring interactive card containers and split-performance photos grouped by day."""
    # --- UPDATE: COMPILATION OF UNIQUE DATE LIST ACROSS BOTH TRACKS AND IMAGES ---
    gpx_dates = set(daily_data.keys())
    photo_dates = {p["datetime"].date() for p in photo_data}
    master_sorted_dates = sorted(list(gpx_dates.union(photo_dates)))

    all_coords = []
    global_max_speed = 0.0
    grand_total_distance_km = 0.0
    grand_total_seconds = 0.0
    
    for date in daily_data.keys():
        day = daily_data[date]
        all_coords.extend(day['full_coords'])
        grand_total_distance_km += (day['distance_m'] / 1000.0)
        grand_total_seconds += day['total_seconds']
        if day['max_speed'] > global_max_speed:
            global_max_speed = day['max_speed']

    for photo in photo_data:
        all_coords.append((photo["lat"], photo["lon"]))

    max_display_speed = max(int(math.ceil(global_max_speed / 10.0) * 10), 20)
    mymap = folium.Map(tiles=None, prefer_canvas=True)
    
    folium.TileLayer("Cartodb Positron", name="☀️ Light Theme", control=True, show=True).add_to(mymap)
    folium.TileLayer("Cartodb dark_matter", name="🌙 Dark Theme", control=True, show=False).add_to(mymap)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="🛰️ Satellite View", control=True, show=False
    ).add_to(mymap)
    folium.TileLayer("OpenStreetMap", name="🗺️ Street View", control=True, show=False).add_to(mymap)

    colormap = cm.LinearColormap(
        colors=['#2ecc71', '#f1c40f', '#e74c3c'], vmin=0, vmax=max_display_speed,
        caption="Driving Velocity Profile (km/h)"
    )
    colormap.add_to(mymap)

    print("🎨 Step 2: Generating vector overlays and injector stylesheets...")
    # Loop over the master calendar grid timeline 
    for day_idx, date in enumerate(master_sorted_dates, 1):
        formatted_date = date.strftime('%b %d, %Y')
        
        # Grab tracking properties if they exist for this calendar date
        day = daily_data.get(date, {
            'chunks': [], 'full_coords': [], 'max_speed': 0.0, 'distance_m': 0.0, 'total_seconds': 0.0
        })
        
        day_dist_km = day['distance_m'] / 1000.0
        
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
        
        # Everything rendered inside this day_feature_group will show/hide together
        day_feature_group = folium.FeatureGroup(name=layer_title, overlay=True, control=True)

        # Plot matching vehicle movement paths
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

        # --- UPDATE: BOUND MATCHING PHOTOS DIRECTLY TO THIS CHRONOLOGICAL DAY GROUP ---
        for global_idx, photo in enumerate(photo_data):
            if photo["datetime"].date() == date:
                icon_html = f"""
                    <img src='{photo["thumb_url"]}' class='map-photo-marker' onclick='launchLightboxGallery({global_idx})' loading='lazy' />
                """
                custom_icon = folium.DivIcon(html=icon_html, icon_size=(44, 44), icon_anchor=(22, 22))
                
                tooltip_html = f"""
                    <div style="font-family: 'Segoe UI', sans-serif; font-size: 12px; padding: 2px; color: #1e293b; white-space: nowrap;">
                        <span style="font-weight: 500; color: #1e293b;">{photo["formatted_time"]}</span>
                    </div>
                """
                folium.Marker(
                    location=[photo["lat"], photo["lon"]], icon=custom_icon,
                    tooltip=folium.Tooltip(tooltip_html, sticky=True)
                ).add_to(day_feature_group)

        day_feature_group.add_to(mymap)

    folium.LayerControl(collapsed=False).add_to(mymap)

    # UI Comprehensive Layout Stylesheet Override
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

        .map-photo-marker {
            width: 44px; height: 44px;
            border: 3px solid #ffffff; border-radius: 10px;
            box-shadow: 0 4px 14px rgba(0,0,0,0.18);
            object-fit: cover; cursor: pointer;
            transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1), border-color 0.2s;
        }
        .map-photo-marker:hover {
            transform: scale(1.25); border-color: #3b82f6; z-index: 999999 !important;
        }

        .leaflet-marker-icon, 
        .leaflet-marker-icon:focus,
        .leaflet-interactive:focus,
        .map-photo-marker,
        .map-photo-marker:focus {
            outline: none !important;
            box-shadow: none !important;
            -webkit-tap-highlight-color: transparent;
        }

        #global-photo-lightbox {
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
            background-color: rgba(15, 23, 42, 0.95); 
            z-index: 9999999; display: none; align-items: center; justify-content: center;
            font-family: 'Segoe UI', system-ui, sans-serif;
        }
        #lightbox-image-frame {
            max-width: 85%; max-height: 80%;
            border-radius: 8px; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
            object-fit: contain; user-select: none; -webkit-user-drag: none;
        }
        .lightbox-control-btn {
            position: absolute; color: #f8fafc; font-size: 28px; font-weight: 300;
            width: 56px; height: 56px; line-height: 52px; background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.1); border-radius: 50%; text-align: center;
            cursor: pointer; user-select: none; transition: background 0.15s, transform 0.1s;
        }
        .lightbox-control-btn:hover { background: rgba(255,255,255,0.15); }
        .lightbox-control-btn:active { transform: scale(0.95); }
        #lightbox-left-arrow { left: 40px; }
        #lightbox-right-arrow { right: 40px; }
        #lightbox-close-btn { top: 30px; right: 40px; font-size: 22px; }
        
        #lightbox-meta-tag {
            position: absolute; bottom: 40px; color: #e2e8f0; font-size: 14px;
            background: rgba(0,0,0,0.4); padding: 8px 20px; border-radius: 20px;
            backdrop-filter: blur(4px); pointer-events: none; text-align: center;
        }
    </style>
    """
    mymap.get_root().header.add_child(folium.Element(ui_css_override))
    mymap.get_root().header.add_child(folium.Element("<title>Road Trip Journal</title>"))

    # JavaScript controller injection block
    ui_javascript_injector = f"""
    <div id="global-photo-lightbox">
        <span class="lightbox-control-btn" id="lightbox-close-btn" onclick="closeLightboxGallery()">✕</span>
        <span class="lightbox-control-btn" id="lightbox-left-arrow" onclick="navigateLightbox(-1)">‹</span>
        <span class="lightbox-control-btn" id="lightbox-right-arrow" onclick="navigateLightbox(1)">›</span>
        <img id="lightbox-image-frame" src="" />
        <div id="lightbox-meta-tag"></div>
    </div>

    <script>
    const dynamicPhotoArray = {str([{k: v for k, v in p.items() if k != 'datetime'} for p in photo_data])};
    let currentLightboxIndex = 0;

    function launchLightboxGallery(index) {{
        currentLightboxIndex = index;
        updateLightboxDisplay();
        document.getElementById('global-photo-lightbox').style.display = 'flex';
    }}

    function closeLightboxGallery() {{
        document.getElementById('global-photo-lightbox').style.display = 'none';
    }}

    function navigateLightbox(direction) {{
        currentLightboxIndex += direction;
        if (currentLightboxIndex >= dynamicPhotoArray.length) currentLightboxIndex = 0;
        if (currentLightboxIndex < 0) currentLightboxIndex = dynamicPhotoArray.length - 1;
        updateLightboxDisplay();
    }}

    function updateLightboxDisplay() {{
        if(dynamicPhotoArray.length === 0) return;
        const currentTarget = dynamicPhotoArray[currentLightboxIndex];
        document.getElementById('lightbox-image-frame').src = currentTarget.full_url;
        document.getElementById('lightbox-meta-tag').innerHTML = `<b>${{currentTarget.filename}}</b><br>${{currentTarget.formatted_time}}`;
    }}

    document.addEventListener('keydown', function(event) {{
        const lightboxView = document.getElementById('global-photo-lightbox');
        if (lightboxView.style.display === 'flex') {{
            if (event.key === 'ArrowRight') navigateLightbox(1);
            if (event.key === 'ArrowLeft') navigateLightbox(-1);
            if (event.key === 'Escape') closeLightboxGallery();
        }}
    }});

    let touchStartAxisX = 0;
    let touchEndAxisX = 0;
    const lightboxFrame = document.getElementById('global-photo-lightbox');
    
    lightboxFrame.addEventListener('touchstart', e => {{
        touchStartAxisX = e.changedTouches[0].screenX;
    }}, {{passive: true}});

    lightboxFrame.addEventListener('touchend', e => {{
        touchEndAxisX = e.changedTouches[0].screenX;
        handleSwipeGesture();
    }}, {{passive: true}});

    function handleSwipeGesture() {{
        const deltaThreshold = 50;
        if (touchStartAxisX - touchEndAxisX > deltaThreshold) {{
            navigateLightbox(1);
        }}
        if (touchEndAxisX - touchStartAxisX > deltaThreshold) {{
            navigateLightbox(-1);
        }}
    }}

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
                    <tr><td style="color:#64748b;"><b>Total Timeline:</b></td><td style="text-align:right; font-weight:bold; color:#1e293b;">{len(master_sorted_dates)} Days</td></tr>
                    <tr><td style="color:#64748b;"><b>Total Driving:</b></td><td style="text-align:right; font-weight:bold; color:#1e293b;">{format_duration(grand_total_seconds)}</td></tr>
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

    title_html = """
    <div style="position: fixed; 
                top: 25px; left: 50%; transform: translateX(-50%); width: auto; max-width: 85%;
                z-index:9999; font-family: 'Segoe UI', sans-serif;
                background-color: rgba(255, 255, 255, 0.95); padding: 12px 28px;
                border-radius: 30px; box-shadow: 0 10px 25px rgba(0,0,0,0.06);
                border: 1px solid #e2e8f0; backdrop-filter: blur(8px);
                text-align: center; white-space: nowrap;">
        <h1 style="margin: 0; color: #1e293b; font-size: 18px; font-weight: 700; letter-spacing: -0.5px;">
            🚗 Our Road Trip Adventure
        </h1>
    </div>
    """
    mymap.get_root().html.add_child(folium.Element(title_html))

    if all_coords:
        min_lat, max_lat = min(c[0] for c in all_coords), max(c[0] for c in all_coords)
        min_lon, max_lon = min(c[1] for c in all_coords), max(c[1] for c in all_coords)
        mymap.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])

    mymap.save(output_html)
    print(f"🎉 Success! Synchronized timeline interface written to: '{output_html}'")

if __name__ == "__main__":
    SCRIPT_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
    TARGET_GPX_FOLDER = os.path.join(SCRIPT_DIRECTORY, "GPXLogs")
    TARGET_IMAGE_FOLDER = os.path.join(SCRIPT_DIRECTORY, "images")
    TARGET_THUMB_FOLDER = os.path.join(SCRIPT_DIRECTORY, "thumbnails")
    
    data_matrix = process_gpx_to_chunked_days(TARGET_GPX_FOLDER)
    photo_matrix = process_images_folder(TARGET_IMAGE_FOLDER, TARGET_THUMB_FOLDER)
    
    build_production_site(data_matrix, photo_matrix, output_html="index.html")