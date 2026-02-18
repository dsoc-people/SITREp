import streamlit as st
import os
import requests
import zipfile
import threading
import time
from datetime import datetime
import shapefile
import folium
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh

# ---------------- CONFIG ----------------

BASE_DIR = "GIS"
SPC_DIR = os.path.join(BASE_DIR, "SPC")
UPDATE_INTERVAL = 900

WARREN_LAT = 36.99
WARREN_LON = -86.44

# Warren County Bounding Box
WARREN_BOUNDS = {
    "lat_min": 36.80,
    "lat_max": 37.10,
    "lon_min": -86.65,
    "lon_max": -86.20
}

SPC_URLS = {
    "Day1": "https://www.spc.noaa.gov/products/outlook/day1otlk-shp.zip",
    "Day2": "https://www.spc.noaa.gov/products/outlook/day2otlk-shp.zip",
    "Day3": "https://www.spc.noaa.gov/products/outlook/day3otlk-shp.zip",
}

RISK_COLORS = {
    "TSTM": "#C6E2FF",
    "MRGL": "#66C266",
    "SLGT": "#FFD700",
    "ENH": "#FF8C00",
    "MDT": "#FF0000",
    "HIGH": "#CC00CC",
}

# WeatherSTEM Warren URLs
WEATHERSTEM_URLS = {
    "WKU": "https://cdn.weatherstem.com/dashboard/data/dynamic/model/warren/wku/latest.json",
    "WKU Chaos": "https://cdn.weatherstem.com/dashboard/data/dynamic/model/warren/wkuchaos/latest.json",
    "WKU IM Fields": "https://cdn.weatherstem.com/dashboard/data/dynamic/model/warren/wkuimfields/latest.json",
}

# ---------------- SETUP ----------------

os.makedirs(SPC_DIR, exist_ok=True)

# 30-second refresh for WeatherSTEM box
st_autorefresh(interval=30000, key="wswx_refresh")

# ---------------- SPC DOWNLOAD ----------------

def download_and_extract(url):
    filename = os.path.join(SPC_DIR, url.split("/")[-1])
    r = requests.get(url, timeout=60)
    with open(filename, "wb") as f:
        f.write(r.content)

    with zipfile.ZipFile(filename, "r") as zip_ref:
        zip_ref.extractall(SPC_DIR)

    os.remove(filename)

def update_spc():
    for url in SPC_URLS.values():
        download_and_extract(url)

def scheduler():
    while True:
        try:
            update_spc()
        except:
            pass
        time.sleep(UPDATE_INTERVAL)

if "scheduler_started" not in st.session_state:
    thread = threading.Thread(target=scheduler, daemon=True)
    thread.start()
    st.session_state.scheduler_started = True

# ---------------- WEATHERSTEM FUNCTIONS ----------------

def fetch_weatherstem_station(name, url):
    try:
        r = requests.get(url, timeout=10).json()
        records = r.get("records", [])

        station_data = {
            "Station": name,
            "Observation Time": r.get("time", "N/A")
        }

        for rec in records:
            sensor = rec.get("sensor_name", "Unknown")
            value = rec.get("value")
            station_data[sensor] = value

        return station_data

    except:
        return None

# ---------------- NWS ALERT COUNTS ----------------

def get_warren_alert_counts():
    url = "https://api.weather.gov/alerts/active?area=KY"
    r = requests.get(url, timeout=30)
    data = r.json()

    warnings = watches = advisories = 0

    for feature in data["features"]:
        area_desc = feature["properties"].get("areaDesc", "")
        if "Warren" in area_desc:
            event = feature["properties"].get("event", "")
            if "Warning" in event:
                warnings += 1
            elif "Watch" in event:
                watches += 1
            elif "Advisory" in event:
                advisories += 1

    return warnings, watches, advisories

# ---------------- MAP ----------------

def load_day(day):
    shp_files = [
        os.path.join(SPC_DIR, f)
        for f in os.listdir(SPC_DIR)
        if day.lower() in f.lower() and f.endswith(".shp")
    ]
    if not shp_files:
        return None, None

    latest = max(shp_files, key=os.path.getmtime)
    sf = shapefile.Reader(latest)
    return sf, latest

def render_map(sf):
    m = folium.Map(location=[WARREN_LAT, WARREN_LON], zoom_start=7)

    folium.TileLayer(
        tiles="https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0r/{z}/{x}/{y}.png",
        attr="NEXRAD",
        name="Radar",
        overlay=True,
    ).add_to(m)

    folium.TileLayer(
        tiles="https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Satellite",
        overlay=False,
    ).add_to(m)

    fields = [field[0] for field in sf.fields[1:]]

    for sr in sf.shapeRecords():
        geom = sr.shape.__geo_interface__
        record = dict(zip(fields, sr.record))
        risk = record.get("DN", "")
        color = RISK_COLORS.get(risk, "#999999")

        folium.GeoJson(
            geom,
            style_function=lambda x, c=color: {
                "fillColor": c,
                "color": "black",
                "weight": 2,
                "fillOpacity": 0.55,
            },
        ).add_to(m)

    folium.CircleMarker(
        location=[WARREN_LAT, WARREN_LON],
        radius=8,
        color="blue",
        fill=True,
        fill_color="blue",
    ).add_to(m)

    folium.LayerControl().add_to(m)
    return m

# ---------------- STREAMLIT UI ----------------

st.set_page_config(layout="wide")
st.title("DSOC Severe Weather Situation Dashboard")

# --- Alert Metrics ---
warnings, watches, advisories = get_warren_alert_counts()

col1, col2, col3 = st.columns(3)
col1.metric("Warnings (Warren Co.)", warnings)
col2.metric("Watches (Warren Co.)", watches)
col3.metric("Advisories (Warren Co.)", advisories)

st.divider()

# ---------------- WEATHERSTEM BOX ----------------

st.subheader("Warren County WeatherSTEM Stations (Live 30s)")

for name, url in WEATHERSTEM_URLS.items():
    station_data = fetch_weatherstem_station(name, url)

    if station_data:
        with st.expander(f"{name}", expanded=True):
            for key, value in station_data.items():
                st.write(f"**{key}:** {value}")
    else:
        st.warning(f"{name} unavailable.")

st.divider()

# ---------------- SPC MAP ----------------

day_choice = st.radio("SPC Outlook", ["Day1", "Day2", "Day3"], horizontal=True)

sf, filepath = load_day(day_choice)

if sf is None:
    st.warning("Waiting for SPC data...")
else:
    mod_time = datetime.utcfromtimestamp(os.path.getmtime(filepath))
    age_minutes = int((datetime.utcnow() - mod_time).total_seconds() / 60)
    st.caption(f"SPC Data Age: {age_minutes} minutes")

    m = render_map(sf)
    st_folium(m, width=1200, height=700)
