import streamlit as st
from PIL import Image

st.set_page_config(page_title="Pharma Safety HMI — AI First", layout="wide")

st.title("Pharma Safety HMI — AI First")

# Sidebar AI Assistant
with st.sidebar:
    st.header("AI Safety Assistant")
    st.write("Chat bubble stream will appear here.")

if "view" not in st.session_state:
    st.session_state.view = "facility"
if "room" not in st.session_state:
    st.session_state.room = None

def set_view(view, room=None):
    st.session_state.view = view
    st.session_state.room = room

# Facility view
if st.session_state.view == "facility":
    st.subheader("Facility Overview (2.5D Blueprint)")
    st.image("assets/facility.png", use_container_width=True)
    st.write("Click below to enter a room:")
    for rn in ["Room 1", "Room 2", "Room 3", "Room 12", "Production 1", "Production 2"]:
        if st.button(rn):
            set_view("room", rn)
            st.experimental_rerun()

# Room view
if st.session_state.view == "room" and st.session_state.room:
    rn = st.session_state.room
    st.subheader(f"{rn} - Interior View")
    st.image(f"assets/{rn.replace(' ', '_').lower()}.png", use_container_width=True)
    st.write("Equipment and detector shown in blueprint style.")
    if st.button("Back to Facility"):
        set_view("facility")
        st.experimental_rerun()
