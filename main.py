import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
from datetime import datetime

# -----------------------------
# CONFIG
# -----------------------------
st.set_page_config(
    page_title="Weather Dashboard",
    layout="wide"
)

API_KEY = "YOUR_OPENWEATHER_API_KEY"

# -----------------------------
# FUNCTIONS
# -----------------------------
def get_weather(city):
    url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?q={city}&units=metric&appid={API_KEY}"
    )
    response = requests.get(url)
    return response.json()


def build_map(lat, lon):
    df = pd.DataFrame({
        "lat": [lat],
        "lon": [lon]
    })

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position="[lon, lat]",
        get_radius=50000,
        pickable=True,
    )

    view_state = pdk.ViewState(
        latitude=lat,
        longitude=lon,
        zoom=6
    )

    return pdk.Deck(
        layers=[layer],
        initial_view_state=view_state
    )


# -----------------------------
# SIDEBAR
# -----------------------------
st.sidebar.title("Locations")

cities = [
    "New York",
    "Los Angeles",
    "Chicago",
    "Houston",
    "Miami"
]

selected_city = st.sidebar.selectbox(
    "Select a city",
    cities
)

refresh = st.sidebar.button("Refresh Weather")

# -----------------------------
# MAIN DASHBOARD
# -----------------------------
st.title("Weather Dashboard")

if refresh or "weather_data" not in st.session_state:
    st.session_state.weather_data = get_weather(selected_city)

weather = st.session_state.weather_data

if weather.get("cod") != 200:
    st.error("Error retrieving weather data")
else:
    col1, col2 = st.columns([2, 1])

    # Map Column
    with col1:
        lat = weather["coord"]["lat"]
        lon = weather["coord"]["lon"]
        st.pydeck_chart(build_map(lat, lon))

    # Widgets Column
    with col2:
        st.subheader("Current Conditions")
        st.metric("Temperature (°C)", weather["main"]["temp"])
        st.metric("Humidity (%)", weather["main"]["humidity"])
        st.metric("Wind Speed (m/s)", weather["wind"]["speed"])

        st.subheader("Alerts")
        description = weather["weather"][0]["description"]
        st.info(description.title())

        st.subheader("Local Time")
        timezone_offset = weather["timezone"]
        local_time = datetime.utcfromtimestamp(
            weather["dt"] + timezone_offset
        )
        st.write(local_time.strftime("%Y-%m-%d %H:%M:%S"))
