import streamlit as st
import os
import requests
import zipfile
import threading
import time
from datetime import datetime
import geopandas as gpd
import folium
from streamlit_folium import st_folium

# ------------------ CONFIG ------------------

BASE_DIR = "GIS"
SPC_CONVECTIVE_DIR = os.path.join(BASE_DIR, "Outlooks", "SPC", "Convective")

UPDATE_INTERVAL = 900  # 15 minutes background update

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

# ------------------ SETUP ------------------

def ensure_directories():
    os.makedirs(SPC_CONVECTIVE_DIR, exist_ok=True)

def download_and_extract(url):
    filename = os.path.join(SPC_CONVECTIVE_DIR, url.split("/")[-1])

    r = requests.get(url, timeout=60)
    with open(filename, "wb") as f:
        f.write(r.content)

    with zipfile.ZipFile(filename, "r") as zip_ref:
        zip_ref.extractall(SPC_CONVECTIVE_DIR)

    os.remove(filename)

def update_spc():
    for url in SPC_URLS.values():
        download_and_extract(url)

# ------------------ BACKGROUND THREAD ------------------

def scheduler():
    while True:
        update_spc()
        time.sleep(UPDATE_INTERVAL)

if "scheduler_started" not in st.session_state:
    ensure_directories()
    thread = threading.Thread(target=scheduler, daemon=True)
    thread.start()
    st.session_state.scheduler_started = True

# ------------------ LOAD SHAPEFILE ------------------

def load_day(day):
    files = [
        os.path.join(SPC_CONVECTIVE_DIR, f)
        for f in os.listdir(SPC_CONVECTIVE_DIR)
        if day.lower() in f.lower() and f.endswith(".shp")
    ]
    if not files:
        return None
    latest = max(files, key=os.path.getmtime)
    return gpd.read_file(latest), latest

# ------------------ MAP ------------------

def style_function(feature):
    risk = feature["properties"].get("DN", "")
    color = RISK_COLORS.get(risk, "#999999")
    return {
        "fillColor": color,
        "color": "black",
        "weight": 1,
        "fillOpacity": 0.5,
    }

def render_map(gdf):
    gdf = gdf.to_crs(epsg=4326)
    bounds = gdf.total_bounds  # xmin, ymin, xmax, ymax

    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2

    m = folium.Map(location=[center_lat, center_lon], zoom_start=5)

    # Auto zoom to bounds
    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])

    # Radar layer
    folium.TileLayer(
        tiles="https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0r/{z}/{x}/{y}.png",
        attr="NEXRAD",
        name="Radar",
        overlay=True,
        control=True,
    ).add_to(m)

    # Satellite layer
    folium.TileLayer(
        tiles="https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Satellite",
        overlay=False,
        control=True,
    ).add_to(m)

    folium.GeoJson(
        gdf,
        style_function=style_function,
        name="SPC Outlook",
    ).add_to(m)

    folium.LayerControl().add_to(m)

    return m

# ------------------ STREAMLIT UI ------------------

st.set_page_config(layout="wide")
st.title("Operational Severe Weather Dashboard")

# Layer Toggle
day_choice = st.radio("Select Outlook Day", ["Day1", "Day2", "Day3"], horizontal=True)

result = load_day(day_choice)

if result is None:
    st.warning("No shapefile found yet. Waiting for background update.")
else:
    gdf, filepath = result

    # Dataset Age Panel
    mod_time = datetime.utcfromtimestamp(os.path.getmtime(filepath))
    age_minutes = int((datetime.utcnow() - mod_time).total_seconds() / 60)

    col1, col2 = st.columns(2)
    col1.metric("Last Updated (UTC)", mod_time.strftime("%Y-%m-%d %H:%M"))
    col2.metric("Dataset Age (minutes)", age_minutes)

    st.divider()

    m = render_map(gdf)
    st_folium(m, width=1200, height=700)

    st.markdown("### Risk Legend")
    for k, v in RISK_COLORS.items():
        st.markdown(f"<span style='color:{v};font-weight:bold'>■ {k}</span>", unsafe_allow_html=True)
