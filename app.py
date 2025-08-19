import streamlit as st

st.set_page_config(page_title="Pharma Safety HMI — AI First", layout="wide")

st.title("Pharma Safety HMI — AI First (Demo)")
st.info("This is a packaged demo app. Facility blueprint, rooms, detectors, smoke animations, shutters, and AI chat will be drawn here.")

st.image("assets/facility.png", caption="2.5D Facility Demo (Blueprint Style)")

st.sidebar.header("AI Safety Assistant")
st.sidebar.write("Chat bubble stream with timestamps and events will appear here.")

st.success("Demo repo structure created successfully. Replace this with full app logic.")
