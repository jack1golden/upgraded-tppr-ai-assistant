import os
from pathlib import Path
import streamlit as st
from PIL import Image, UnidentifiedImageError
import io

# ---------- CONFIG ----------
st.set_page_config(page_title="Pharma Safety HMI — AI First", layout="wide")

HERE = Path(__file__).parent.resolve()
ASSETS = (HERE / "assets").resolve()
ROOMS = ["Room 1", "Room 2", "Room 3", "Room 12", "Production 1", "Production 2"]

# ---------- IMAGE LOADER (robust) ----------
def show_image(path: Path, caption: str | None = None, **kwargs):
    """
    Robustly load an image for Streamlit:
    - Verifies existence
    - Tries Pillow open/convert
    - Falls back to raw bytes
    - Clear error if anything fails
    """
    if not path.exists() or not path.is_file():
        st.error(f"Missing image: {path}")
        st.stop()

    # Try Pillow first (best for formats/conversion)
    try:
        with Image.open(path) as im:
            # Convert to a common mode to avoid downstream issues
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGB")
            st.image(im, caption=caption, **kwargs)
            return
    except UnidentifiedImageError:
        # Fall back to raw bytes if PIL cannot identify (e.g., truncated but viewable)
        pass
    except Exception as e:
        st.warning(f"PIL load warning for {path.name}: {e}")

    # Fallback: bytes
    try:
        with open(path, "rb") as f:
            data = f.read()
        st.image(data, caption=caption, **kwargs)
    except Exception as e:
        st.error(f"Unable to display image {path.name}: {e}")
        st.stop()

# ---------- STATE ----------
if "view" not in st.session_state:
    st.session_state.view = "facility"
if "room" not in st.session_state:
    st.session_state.room = None

def set_view(view: str, room: str | None = None):
    st.session_state.view = view
    st.session_state.room = room

# ---------- DEBUG (collapse if you like) ----------
with st.expander("Debug (paths)", expanded=False):
    st.write({"cwd": os.getcwd(), "HERE": str(HERE), "ASSETS": str(ASSETS)})
    st.write("Assets present:", sorted([p.name for p in ASSETS.glob("*")]))

# ---------- SIDEBAR (AI panel placeholder) ----------
with st.sidebar:
    st.header("AI Safety Assistant")
    st.write("Chat bubble stream will appear here in the next upgrade.")
    st.caption("This build verifies image loading + navigation paths.")

# ---------- FACILITY ----------
if st.session_state.view == "facility":
    st.title("Pharma Safety HMI — AI First")
    st.subheader("Facility Overview (2.5D Blueprint)")

    show_image(ASSETS / "facility.png", caption="Facility Cutaway", use_container_width=True)

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
    show_image(img_path, caption=f"{rn} (Blueprint Interior)", use_container_width=True)

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("← Back to Facility", use_container_width=True):
            set_view("facility")
            st.experimental_rerun()
    with col2:
        st.caption("Detectors, charts, smoke & shutters will be added here in the next step.")

