import streamlit as st
import os
import requests
import zipfile
import threading
import time
from datetime import datetime, timezone
import shapefile
import folium
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh

# ---------------- PAGE CONFIG ----------------
st.set_page_config(layout="wide")

# 30-second WeatherSTEM refresh
st_autorefresh(interval=30000, key="wswx_refresh")

# ---------------- CONFIG ----------------

BASE_DIR = "GIS"
SPC_DIR = os.path.join(BASE_DIR, "SPC")
UPDATE_INTERVAL = 900

WARREN_LAT = 36.99
WARREN_LON = -86.44

SPC_URLS = {
    "Day1": "https://www.spc.noaa.gov/products/outlook/day1otlk-shp.zip",
    "Day2": "https://www.spc.noaa.gov/products/outlook/day2otlk-shp.zip",
    "Day3": "https://www.spc.noaa.gov/products/outlook/day3otlk-shp.zip",
}

MD_URL = "https://www.spc.noaa.gov/products/md/md_latest.geojson"

RISK_COLORS = {
    "TSTM": "#C6E2FF",
    "MRGL": "#66C266",
    "SLGT": "#FFD700",
    "ENH": "#FF8C00",
    "MDT": "#FF0000",
    "HIGH": "#CC00CC",
}

WEATHERSTEM_URLS = {
    "WKU": "https://cdn.weatherstem.com/dashboard/data/dynamic/model/warren/wku/latest.json",
    "WKU Chaos": "https://cdn.weatherstem.com/dashboard/data/dynamic/model/warren/wkuchaos/latest.json",
    "WKU IM Fields": "https://cdn.weatherstem.com/dashboard/data/dynamic/model/warren/wkuimfields/latest.json",
}

# ---------------- SETUP ----------------

os.makedirs(SPC_DIR, exist_ok=True)

# ---------------- SPC DOWNLOAD ----------------

def download_and_extract(url):
    try:
        filename = os.path.join(SPC_DIR, url.split("/")[-1])
        r = requests.get(url, timeout=60)
        if r.status_code == 200:
            with open(filename, "wb") as f:
                f.write(r.content)
            with zipfile.ZipFile(filename, "r") as zip_ref:
                zip_ref.extractall(SPC_DIR)
            os.remove(filename)
    except:
        pass

def update_spc():
    for url in SPC_URLS.values():
        download_and_extract(url)

def scheduler():
    while True:
        update_spc()
        time.sleep(UPDATE_INTERVAL)

if "scheduler_started" not in st.session_state:
    thread = threading.Thread(target=scheduler, daemon=True)
    thread.start()
    st.session_state.scheduler_started = True

# ---------------- WEATHERSTEM ----------------

def fetch_weatherstem_station(name, url):
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200 or not r.text.strip():
            return None

        j = r.json()
        records = j.get("records", [])

        data = {
            "Station": name,
            "Observation Time": j.get("time", "N/A")
        }

        for rec in records:
            sensor = rec.get("sensor_name", "Unknown")
            value = rec.get("value")
            data[sensor] = value

        return data
    except:
        return None

# ---------------- ALERT COUNTS ----------------

def get_warren_alert_counts():
    try:
        url = "https://api.weather.gov/alerts/active?area=KY"
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            return 0, 0, 0

        data = r.json()
        warnings = watches = advisories = 0

        for feature in data.get("features", []):
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
    except:
        return 0, 0, 0

# ---------------- SPC LOAD ----------------

def load_day(day):
    shp_files = [
        os.path.join(SPC_DIR, f)
        for f in os.listdir(SPC_DIR)
        if day.lower() in f.lower() and f.endswith(".shp")
    ]
    if not shp_files:
        return None, None

    latest = max(shp_files, key=os.path.getmtime)
    return shapefile.Reader(latest), latest

# ---------------- MAP ----------------

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

    # SAFE MD LOAD
    try:
        md_response = requests.get(MD_URL, timeout=30)
        if md_response.status_code == 200 and md_response.text.strip():
            md_data = md_response.json()
            for feature in md_data.get("features", []):
                folium.GeoJson(
                    feature["geometry"],
                    tooltip=f"MD #{feature['properties'].get('md_number', '')}",
                    popup=feature["properties"].get("headline", "No headline"),
                    style_function=lambda x: {"color": "purple", "weight": 3},
                ).add_to(m)
    except:
        pass

    folium.CircleMarker(
        location=[WARREN_LAT, WARREN_LON],
        radius=8,
        color="blue",
        fill=True,
        fill_color="blue",
    ).add_to(m)

    folium.LayerControl().add_to(m)
    return m

# ---------------- UI ----------------

st.title("DSOC Severe Weather Situation Dashboard")

warnings, watches, advisories = get_warren_alert_counts()

col1, col2, col3 = st.columns(3)
col1.metric("Warnings (Warren Co.)", warnings)
col2.metric("Watches (Warren Co.)", watches)
col3.metric("Advisories (Warren Co.)", advisories)

st.divider()

# WEATHERSTEM BOX
st.subheader("Warren County WeatherSTEM Stations (Live 30s)")

for name, url in WEATHERSTEM_URLS.items():
    station = fetch_weatherstem_station(name, url)
    if station:
        with st.expander(name, expanded=True):
            for k, v in station.items():
                st.write(f"**{k}:** {v}")
    else:
        st.warning(f"{name} unavailable.")

st.divider()

# SPC MAP
day_choice = st.radio("SPC Outlook", ["Day1", "Day2", "Day3"], horizontal=True)

sf, filepath = load_day(day_choice)

if sf:
    mod_time = datetime.fromtimestamp(os.path.getmtime(filepath), timezone.utc)
    age_minutes = int((datetime.now(timezone.utc) - mod_time).total_seconds() / 60)
    st.caption(f"SPC Data Age: {age_minutes} minutes")

    m = render_map(sf)
    st_folium(m, width=1200, height=700)
else:
    st.warning("Waiting for SPC data...")
