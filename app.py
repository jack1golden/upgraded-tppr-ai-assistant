import os
from pathlib import Path
import streamlit as st
from PIL import Image

# ---------- CONFIG ----------
st.set_page_config(page_title="Pharma Safety HMI — AI First", layout="wide")

HERE = Path(__file__).parent
ASSETS = HERE / "assets"

ROOMS = ["Room 1", "Room 2", "Room 3", "Room 12", "Production 1", "Production 2"]

# ---------- STATE ----------
if "view" not in st.session_state:
    st.session_state.view = "facility"
if "room" not in st.session_state:
    st.session_state.room = None

def set_view(view: str, room: str | None = None):
    st.session_state.view = view
    st.session_state.room = room

# ---------- HELPERS ----------
def safe_image(path: Path, caption: str | None = None, **kwargs):
    if path.exists() and path.is_file():
        st.image(str(path), caption=caption, **kwargs)
    else:
        st.error(f"Image not found: {path}")
        st.stop()

# ---------- SIDEBAR (AI panel placeholder) ----------
with st.sidebar:
    st.header("AI Safety Assistant")
    st.write("Chat bubble stream will appear here in the next upgrade.")
    st.caption("This build verifies image loading + navigation paths.")

# ---------- FACILITY ----------
if st.session_state.view == "facility":
    st.title("Pharma Safety HMI — AI First")
    st.subheader("Facility Overview (2.5D Blueprint)")

    safe_image(ASSETS / "facility.png", caption="Facility Cutaway", use_container_width=True)

    st.markdown("### Rooms")
    cols = st.columns(3)
    for i, rn in enumerate(ROOMS):
        with cols[i % 3]:
            if st.button(rn, use_container_width=True):
                set_view("room", rn)
                st.experimental_rerun()

# ---------- ROOM ----------
if st.session_state.view == "room" and st.session_state.room:
    rn = st.session_state.room
    st.subheader(f"{rn} — Interior View")
    img_path = ASSETS / f"{rn.replace(' ', '_').lower()}.png"
    safe_image(img_path, caption=f"{rn} (Blueprint Interior)", use_container_width=True)

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("← Back to Facility", use_container_width=True):
            set_view("facility")
            st.experimental_rerun()
    with col2:
        st.caption("Detectors, charts, smoke & shutters will be added here in the next step.")
