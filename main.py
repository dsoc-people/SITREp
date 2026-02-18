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

# ---------------- CONFIG ----------------

BASE_DIR = "GIS"
SPC_DIR = os.path.join(BASE_DIR, "SPC")
UPDATE_INTERVAL = 900

SPC_URLS = {
    "Day1": "https://www.spc.noaa.gov/products/outlook/day1otlk-shp.zip",
    "Day2": "https://www.spc.noaa.gov/products/outlook/day2otlk-shp.zip",
    "Day3": "https://www.spc.noaa.gov/products/outlook/day3otlk-shp.zip",
}

RISK_COLORS = {
    "TSTM": "#66ccff",
    "MRGL": "#00ff00",
    "SLGT": "#ffff00",
    "ENH": "#ff9900",
    "MDT": "#ff0000",
    "HIGH": "#cc00cc",
}

# ---------------- SETUP ----------------

def ensure_dir():
    os.makedirs(SPC_DIR, exist_ok=True)

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

# ---------------- BACKGROUND THREAD ----------------

def scheduler():
    while True:
        update_spc()
        time.sleep(UPDATE_INTERVAL)

if "scheduler_started" not in st.session_state:
    ensure_dir()
    thread = threading.Thread(target=scheduler, daemon=True)
    thread.start()
    st.session_state.scheduler_started = True

# ---------------- LOAD SHAPEFILE ----------------

def load_day(day):
    files = [
        os.path.join(SPC_DIR, f)
        for f in os.listdir(SPC_DIR)
        if day.lower() in f.lower() and f.endswith(".shp")
    ]
    if not files:
        return None, None

    latest = max(files, key=os.path.getmtime)
    sf = shapefile.Reader(latest)
    return sf, latest

# ---------------- MAP ----------------

def render_map(sf):
    bbox = sf.bbox  # [xmin, ymin, xmax, ymax]
    center_lat = (bbox[1] + bbox[3]) / 2
    center_lon = (bbox[0] + bbox[2]) / 2

    m = folium.Map(location=[center_lat, center_lon], zoom_start=5)
    m.fit_bounds([[bbox[1], bbox[0]], [bbox[3], bbox[2]]])

    # Radar
    folium.TileLayer(
        tiles="https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0r/{z}/{x}/{y}.png",
        attr="NEXRAD",
        name="Radar",
        overlay=True,
    ).add_to(m)

    # Satellite
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
                "weight": 1,
                "fillOpacity": 0.5,
            },
        ).add_to(m)

    folium.LayerControl().add_to(m)
    return m

# ---------------- STREAMLIT ----------------

st.set_page_config(layout="wide")
st.title("Operational Severe Weather Dashboard")

day_choice = st.radio("Select Outlook Day", ["Day1", "Day2", "Day3"], horizontal=True)

sf, filepath = load_day(day_choice)

if sf is None:
    st.warning("Waiting for background data download...")
else:
    mod_time = datetime.utcfromtimestamp(os.path.getmtime(filepath))
    age_minutes = int((datetime.utcnow() - mod_time).total_seconds() / 60)

    col1, col2 = st.columns(2)
    col1.metric("Last Updated (UTC)", mod_time.strftime("%Y-%m-%d %H:%M"))
    col2.metric("Dataset Age (minutes)", age_minutes)

    st.divider()

    m = render_map(sf)
    st_folium(m, width=1200, height=700)

    st.markdown("### Risk Legend")
    for k, v in RISK_COLORS.items():
        st.markdown(f"<span style='color:{v};font-weight:bold'>■ {k}</span>", unsafe_allow_html=True)
