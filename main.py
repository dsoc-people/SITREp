import streamlit as st
import os
import requests
import zipfile
import time
from datetime import datetime
import shapefile
import folium
from streamlit_folium import st_folium

# ---------------- CONFIG ----------------

BASE_DIR = "GIS"
SPC_DIR = os.path.join(BASE_DIR, "SPC")
os.makedirs(SPC_DIR, exist_ok=True)

WARREN_LAT = 36.99
WARREN_LON = -86.44

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

MD_URL = "https://www.spc.noaa.gov/products/md/md_latest.geojson"

# ---------------- DOWNLOAD ----------------

def download_and_extract(url):
    filename = os.path.join(SPC_DIR, url.split("/")[-1])

    r = requests.get(url, timeout=60)
    if r.status_code != 200:
        raise Exception(f"Failed to download {url}")

    with open(filename, "wb") as f:
        f.write(r.content)

    with zipfile.ZipFile(filename, "r") as zip_ref:
        zip_ref.extractall(SPC_DIR)

    os.remove(filename)

@st.cache_data(ttl=900)
def ensure_spc_downloaded():
    if not any(f.endswith(".shp") for f in os.listdir(SPC_DIR)):
        for url in SPC_URLS.values():
            download_and_extract(url)
        return "Downloaded"
    return "Exists"

# ---------------- LOAD ----------------

def load_spc(day):
    files = [
        os.path.join(SPC_DIR, f)
        for f in os.listdir(SPC_DIR)
        if day.lower() in f.lower() and f.endswith(".shp")
    ]
    if not files:
        return None
    latest = max(files, key=os.path.getmtime)
    return shapefile.Reader(latest), latest

# ---------------- MAP ----------------

def render_map(sf):
    m = folium.Map(location=[WARREN_LAT, WARREN_LON], zoom_start=7)

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

    fields = [f[0] for f in sf.fields[1:]]

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
                "fillOpacity": 0.6,
            },
        ).add_to(m)

    # Mesoscale Discussions
    md_data = requests.get(MD_URL, timeout=30).json()

    for feature in md_data["features"]:
        folium.GeoJson(
            feature["geometry"],
            tooltip=f"MD #{feature['properties']['md_number']}",
            popup=feature["properties"]["headline"],
            style_function=lambda x: {"color": "purple", "weight": 3},
        ).add_to(m)

    folium.LayerControl().add_to(m)
    return m

# ---------------- STREAMLIT ----------------

st.set_page_config(layout="wide")
st.title("DSOC Operational Weather Dashboard")

status = ensure_spc_downloaded()

if status == "Downloaded":
    st.success("SPC outlook data downloaded.")
else:
    st.info("SPC data ready.")

day_choice = st.radio("SPC Outlook", ["Day1", "Day2", "Day3"], horizontal=True)

sf_data = load_spc(day_choice)

if sf_data:
    sf, filepath = sf_data
    mod_time = datetime.utcfromtimestamp(os.path.getmtime(filepath))
    age_minutes = int((datetime.utcnow() - mod_time).total_seconds() / 60)
    st.caption(f"SPC Data Age: {age_minutes} minutes")

    m = render_map(sf)
    st_folium(m, width=1200, height=700)
else:
    st.error("SPC shapefile not found after download attempt.")
