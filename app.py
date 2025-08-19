import streamlit as st
import random
import time
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from collections import deque

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ----------------------------
# CONFIG
# ----------------------------
HERE = Path(__file__).parent
ASSETS = HERE / "assets"

ROOMS = ["Room 1", "Room 2", "Room 3", "Room 12", "Production 1", "Production 2"]

# Live data storage
if "data" not in st.session_state:
    st.session_state.data = {room: deque(maxlen=50) for room in ROOMS}
    st.session_state.timestamps = deque(maxlen=50)
    st.session_state.t0 = time.time()

# Simulation state
if "smoke" not in st.session_state:
    st.session_state.smoke = {room: 0.0 for room in ROOMS}
if "view" not in st.session_state:
    st.session_state.view = "facility"
if "room" not in st.session_state:
    st.session_state.room = None

# ----------------------------
# LIVE DATA UPDATER
# ----------------------------
def update_data():
    now = time.time() - st.session_state.t0
    st.session_state.timestamps.append(now)
    for room in ROOMS:
        # Random walk data
        if random.random() < 0.05:  # occasional spike
            val = random.uniform(50, 100)
            st.session_state.smoke[room] = min(1.0, st.session_state.smoke[room] + 0.2)
        else:
            val = random.uniform(5, 20)
            st.session_state.smoke[room] = max(0.0, st.session_state.smoke[room] - 0.02)
        st.session_state.data[room].append(val)

# ----------------------------
# FACILITY RENDER
# ----------------------------
def draw_facility():
    """Draws a simple 2.5D facility cutaway with Pillow."""
    w, h = 1200, 700
    img = Image.new("RGB", (w, h), (25, 25, 25))
    draw = ImageDraw.Draw(img)

    # Layout grid
    layout = {
        "Room 1": (50, 50, 300, 250),
        "Room 2": (350, 50, 600, 250),
        "Room 3": (650, 50, 900, 250),
        "Room 12": (950, 50, 1150, 250),
        "Production 1": (200, 350, 550, 600),
        "Production 2": (650, 350, 1000, 600),
    }

    for room, (x1, y1, x2, y2) in layout.items():
        # Base room rectangle
        draw.rectangle([x1, y1, x2, y2], outline=(0, 200, 255), width=3)

        # Room label
        draw.text((x1 + 10, y1 + 10), room, fill=(0, 200, 255))

        # Gas cloud overlay
        intensity = st.session_state.smoke.get(room, 0.0)
        if intensity > 0:
            overlay = Image.new("RGBA", (x2 - x1, y2 - y1), (255, 0, 0, int(120 * intensity)))
            img.paste(overlay, (x1, y1), overlay)

    return img

def render_facility():
    st.subheader("Facility Overview (2.5D Blueprint)")
    img = draw_facility()
    st.image(img, use_column_width=True)

    st.markdown("### Rooms")
    cols = st.columns(len(ROOMS))
    for idx, rn in enumerate(ROOMS):
        with cols[idx % len(cols)]:
            if st.button(rn, key=f"enter_{rn}"):
                st.session_state.view = "room"
                st.session_state.room = rn
                st.rerun()

# ----------------------------
# ROOM VIEW
# ----------------------------
def render_room(room):
    st.subheader(f"{room} — Detail View")

    # Chart
    fig, ax = plt.subplots()
    ax.plot(st.session_state.timestamps, list(st.session_state.data[room]), label="Gas Level", color="red")
    ax.set_ylabel("ppm")
    ax.set_xlabel("time (s)")
    ax.legend()
    st.pyplot(fig)

    # Back button
    if st.button("⬅ Back to Facility"):
        st.session_state.view = "facility"
        st.session_state.room = None
        st.rerun()

# ----------------------------
# APP MAIN
# ----------------------------
st.title("Pharma Safety HMI — AI First (Demo)")

update_data()

if st.session_state.view == "facility":
    render_facility()
elif st.session_state.view == "room":
    render_room(st.session_state.room)

