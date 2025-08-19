import os, io, time, math, json, base64
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image, UnidentifiedImageError
import streamlit.components.v1 as components

# ===================== CONFIG =====================
st.set_page_config(page_title="Pharma Safety HMI — AI First", layout="wide")

HERE = Path(__file__).parent.resolve()
ASSETS = (HERE / "assets").resolve()

ROOMS = ["Room 1", "Room 2", "Room 3", "Room 12", "Production 1", "Production 2"]
ROOM_DETECTORS = {
    "Room 1": ["Room 1: NH3"],
    "Room 2": ["Room 2: CO"],
    "Room 3": ["Room 3: O2"],
    "Room 12": ["Room 12: Ethanol"],
    "Production 1": ["Production 1: O2", "Production 1: CH4"],
    "Production 2": ["Production 2: O2", "Production 2: H2S"],
}
# Facility hotspots: left, top, width, height in %
ROOM_RECTS_PCT = {
    "Room 1":       (6.0,  8.0,  22.0, 20.0),
    "Room 2":       (30.0,  8.0,  22.0, 20.0),
    "Room 3":       (54.0,  8.0,  22.0, 20.0),
    "Room 12":      (78.0,  8.0,  18.0, 20.0),
    "Production 1": (18.0, 40.0, 30.0, 30.0),
    "Production 2": (52.0, 40.0, 30.0, 30.0),
}
# Gas colors (smoke)
GAS_COLOR = {
    "NH3":      (168, 85, 247, 0.24),   # purple
    "CO":       (239, 68, 68, 0.26),    # red
    "O2":       (30, 58, 138, 0.30),    # deep blue (low-O2 "void")
    "Ethanol":  (245, 158, 11, 0.26),   # orange
    "CH4":      (234, 179, 8, 0.26),    # yellow
    "H2S":      (34, 197, 94, 0.26),    # green
}
DEFAULT_THR = {
    "O2":      {"mode":"low",  "warn":19.5, "alarm":18.0, "units":"%vol"},
    "CO":      {"mode":"high", "warn":35.0, "alarm":50.0, "units":"ppm"},
    "H2S":     {"mode":"high", "warn":10.0, "alarm":15.0, "units":"ppm"},
    "CH4":     {"mode":"high", "warn":10.0, "alarm":20.0, "units":"%LEL"},
    "NH3":     {"mode":"high", "warn":25.0, "alarm":35.0, "units":"ppm"},
    "Ethanol": {"mode":"high", "warn":300.0, "alarm":500.0, "units":"ppm"},
}

# ===================== STATE =====================
if "view" not in st.session_state:
    st.session_state.view = "facility"
if "room" not in st.session_state:
    st.session_state.room = None
if "spike" not in st.session_state:
    # single active spike: {room, gas, start_ts, duration, shutters_at, fade_after}
    st.session_state.spike = None
if "buffers" not in st.session_state:
    st.session_state.buffers = {}
if "latest" not in st.session_state:
    st.session_state.latest = {}

def set_view(view: str, room: Optional[str] = None):
    st.session_state.view = view
    st.session_state.room = room

# ===================== HELPERS =====================
def b64_image(path: Path) -> str:
    if not path.exists():
        return ""
    with open(path, "rb") as f:
        data = f.read()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")

def gas_from_label(key: str) -> str:
    k = key.lower()
    if "o2" in k: return "O2"
    if "h2s" in k: return "H2S"
    if "ch4" in k or "lel" in k or "methane" in k: return "CH4"
    if "nh3" in k or "ammonia" in k: return "NH3"
    if "ethanol" in k: return "Ethanol"
    if "co" in k and "co2" not in k: return "CO"
    return "CO"

def status_for_value(gas: str, val: float) -> str:
    thr = DEFAULT_THR.get(gas, {"mode":"high","warn":0,"alarm":0})
    if thr["mode"] == "low":
        if val <= thr["alarm"]: return "ALARM"
        if val <= thr["warn"]:  return "WARN"
        return "HEALTHY"
    else:
        if val >= thr["alarm"]: return "ALARM"
        if val >= thr["warn"]:  return "WARN"
        return "HEALTHY"

def push_point(key: str, val: float):
    ts = time.time()
    buf = st.session_state.buffers.setdefault(key, [])
    buf.append((ts, float(val)))
    if len(buf) > 1800:  # last 30 min @ 1Hz
        del buf[:len(buf)-1800]
    st.session_state.latest[key] = (ts, float(val))

def get_series(key: str) -> pd.DataFrame:
    buf = st.session_state.buffers.get(key, [])
    if not buf:
        return pd.DataFrame(columns=["ts","value"])
    ts, vs = zip(*buf)
    return pd.DataFrame({"ts": ts, "value": vs})

# basic simulator (ticks whenever you press buttons, good enough for demo)
def simulate_live_values():
    t = time.time() % 10000
    vals = {
        "Room 1: NH3":          8 + 6*math.sin(t/18),
        "Room 2: CO":           15 + 12*math.sin(t/20),
        "Room 3: O2":           20.7 + 0.2*math.sin(t/22),
        "Room 12: Ethanol":     260 + 120*math.sin(t/24),
        "Production 1: O2":     20.8 + 0.14*math.sin(t/26),
        "Production 1: CH4":    5 + 3*math.sin(t/16),
        "Production 2: O2":     20.9 + 0.12*math.sin(t/28),
        "Production 2: H2S":    2 + 2.5*math.sin(t/14),
    }
    # If spike is active, push a bump to the affected detector(s)
    sp = st.session_state.spike
    if sp:
        for key in ROOM_DETECTORS.get(sp["room"], []):
            g = gas_from_label(key)
            if g == sp["gas"]:
                # rising shape while active
                elapsed = time.time() - sp["start_ts"]
                bump = max(0.0, (elapsed/3.5) * (10 if g != "O2" else -2))
                vals[key] = vals.get(key, 0) + bump
    for k, v in vals.items():
        push_point(k, v)

# ===================== SIDEBAR (AI chat, animated via JS) =====================
def render_sidebar_ai():
    st.sidebar.header("AI Safety Assistant")
    # derive spike info snapshot for JS
    sp = st.session_state.spike
    data = None
    if sp:
        # Prepare chat timing windows (seconds since spike start)
        # 0s: detection; 2s: warn; 5s: close shutters; 7s: isolated; 10s: ventilation; 13s: safe
        data = {
            "room": sp["room"],
            "gas": sp["gas"],
            "start_ts": sp["start_ts"],
            "events": [
                {"at": 0,  "msg": f"{sp['gas']} levels elevated in {sp['room']}. Monitoring…"},
                {"at": 2,  "msg": f"{sp['gas']} rising. Investigate source and increase ventilation."},
                {"at": 5,  "msg": f"Alarm threshold reached. Closing shutters to isolate {sp['room']}."},
                {"at": 7,  "msg": f"{sp['room']} isolated. Production areas remain safe."},
                {"at": 10, "msg": f"Ventilation engaged. {sp['gas']} dissipating."},
                {"at": 13, "msg": f"{sp['room']} returned to safe condition."},
            ]
        }
    payload = json.dumps(data) if data else "null"

    components.html(f"""
    <div id="chat" style="
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
      color:#e5e7eb; background:#0b1220; border:1px solid #1f2a44; border-radius:12px;
      padding:12px; height:520px; overflow:auto; box-shadow:0 10px 30px rgba(0,0,0,.35);
    ">
      <div id="log" style="display:flex; flex-direction:column; gap:8px;"></div>
    </div>
    <script>
      const gasEmoji={{"NH3":"🟣","CO":"🔴","O2":"🔵","Ethanol":"🟠","CH4":"🟡","H2S":"🟢"}};
      const data = {payload};
      const log = document.getElementById('log');
      function ts() {{
        const d = new Date();
        return d.toLocaleTimeString();
      }}
      function bubble(text) {{
        const b = document.createElement('div');
        b.style.background = 'rgba(30,58,138,.35)';
        b.style.border = '1px solid #334155';
        b.style.borderRadius = '12px';
        b.style.padding = '10px 12px';
        b.style.backdropFilter = 'blur(2px)';
        b.style.animation = 'slidein .25s ease-out';
        b.textContent = text;
        log.appendChild(b);
        log.scrollTop = log.scrollHeight;
      }}
      const style = document.createElement('style');
      style.innerHTML = '@keyframes slidein{{from{{opacity:.0; transform:translateX(-6px)}} to{{opacity:1; transform:translateX(0)}}}}';
      document.head.appendChild(style);

      if (!data) {{
        bubble('System idle. No active events.');
      }} else {{
        const start = data.start_ts * 1000; // sec->ms
        const gas = data.gas;
        const room = data.room;
        // Seed first message immediately
        bubble(`[${{ts()}}] 🤖 AI: ${{
          gasEmoji[gas] || ''
        }} ${data.events[0].msg}`);
        // Schedule the rest with short delays
        for (let i=1;i<data.events.length;i++) {{
          const ev = data.events[i];
          setTimeout(() => {{
            bubble(`[${{ts()}}] 🤖 AI: ${{
              gasEmoji[gas] || ''
            }} ${ev.msg}`);
          }}, ev.at*1000);
        }}
      }}
    </script>
    """, height=560, scrolling=True)

# ===================== FACILITY (image + canvas smoke/shutters) =====================
def render_facility():
    st.title("Pharma Safety HMI — AI First")
    st.subheader("Facility Overview (2.5D Blueprint)")

    facility_b64 = b64_image(ASSETS / "facility.png")

    # Pack rectangles and active spike for JS
    rects = ROOM_RECTS_PCT
    sp = st.session_state.spike
    active = None
    if sp:
        rgba = GAS_COLOR.get(sp["gas"], (239,68,68,0.25))
        active = {
            "room": sp["room"],
            "gas": sp["gas"],
            "start_ts": sp["start_ts"],
            "duration": sp["duration"],
            "shutters_at": sp["shutters_at"],
            "fade_after": sp["fade_after"],
            "color": rgba,
            "rect": rects.get(sp["room"])
        }

    payload = json.dumps({
        "image": facility_b64,
        "rects": rects,
        "active": active
    })

    # Buttons row
    st.markdown("#### Rooms")
    cols = st.columns(3)
    for i, rn in enumerate(ROOMS):
        with cols[i % 3]:
            if st.button(rn, use_column_width=True, key=f"enter_{rn}"):
                set_view("room", rn)
                st.experimental_rerun()

    # Simulate spike at facility-level (applies to first detector gas in that room)
    st.markdown("---")
    colA, colB = st.columns([1,2])
    with colA:
        room_choice = st.selectbox("Simulate spike in…", ROOMS, key="fac_spike_room")
        # choose gas from room detectors (first gas if multiple)
        first_key = ROOM_DETECTORS[room_choice][0]
        gas = gas_from_label(first_key)
        if st.button("Simulate Spike (Facility View)", use_column_width=True, key="fac_spike_btn"):
            st.session_state.spike = {
                "room": room_choice,
                "gas": gas,
                "start_ts": time.time(),
                "duration": 14,      # total animation seconds
                "shutters_at": 5,    # when shutters close
                "fade_after": 9      # when to start fade
            }
            simulate_live_values()  # push initial bump
            st.experimental_rerun()
    with colB:
        st.caption("Gas colors legend:")
        st.markdown("🟣 NH₃ &nbsp;&nbsp; 🔴 CO &nbsp;&nbsp; 🔵 Low O₂ &nbsp;&nbsp; 🟠 Ethanol &nbsp;&nbsp; 🟡 CH₄ &nbsp;&nbsp; 🟢 H₂S")

    # Canvas animation with JS
    components.html(f"""
    <div style="position:relative; width:100%; max-width:1200px; margin: 8px 0 16px 0;">
      <img id="bg" src="{facility_b64}" style="width:100%; height:auto; display:block; border-radius:12px; border:1px solid #1f2a44;"/>
      <canvas id="fx" style="position:absolute; left:0; top:0; width:100%; height:100%; pointer-events:none;"></canvas>
    </div>
    <script>
      const payload = {payload};
      const img = document.getElementById('bg');
      const canvas = document.getElementById('fx');
      const ctx = canvas.getContext('2d');
      function resize() {{
        const r = img.getBoundingClientRect();
        canvas.width = r.width; canvas.height = r.height;
        draw();
      }}
      function pctToPx(rectPct) {{
        // rectPct = [l,t,w,h] in %
        const r = img.getBoundingClientRect();
        const l = rectPct[0]*r.width/100, t = rectPct[1]*r.height/100;
        const w = rectPct[2]*r.width/100, h = rectPct[3]*r.height/100;
        return [l,t,w,h];
      }}
      function drawSmokeRect(rect, progress, color) {{
        const [l,t,w,h] = rect;
        const steps = 20;
        for (let i=0;i<steps;i++) {{
          const alpha = color[3] * (1 - i/steps) * Math.min(1, progress);
          ctx.fillStyle = `rgba(${color[0]},${color[1]},${color[2]},${alpha})`;
          const inset = (1 - progress) * (Math.min(w,h)*0.45) * (i/steps);
          ctx.fillRect(l+inset, t+inset, w-2*inset, h-2*inset);
        }}
      }}
      function drawShutters(rect, k) {{
        const [l,t,w,h] = rect;
        const y = t + (-h * (1-k)); // slide down from top
        ctx.fillStyle = 'rgba(148,163,184,0.22)';
        ctx.fillRect(l, y, w, h);
        // hatch
        ctx.strokeStyle = 'rgba(148,163,184,0.35)';
        ctx.lineWidth = 2;
        for (let x=l; x<l+w; x+=12) {{
          ctx.beginPath();
          ctx.moveTo(x, y);
          ctx.lineTo(x+20, y+h);
          ctx.stroke();
        }}
      }}
      function draw() {{
        ctx.clearRect(0,0,canvas.width,canvas.height);
        if (!payload.active) return;
        const now = Date.now()/1000;
        const a = payload.active;
        const rect = pctToPx(a.rect);
        const elapsed = now - a.start_ts;
        const p = Math.max(0, Math.min(1, elapsed / a.duration));
        let smokeP = Math.min(1, p*1.2);
        // start fading after fade_after
        if (elapsed > a.fade_after) {{
          const fadeK = Math.min(1, (elapsed - a.fade_after) / (a.duration - a.fade_after + 0.01));
          smokeP = Math.max(0, 1 - fadeK);
        }}
        drawSmokeRect(rect, smokeP, a.color);
        // shutters
        if (elapsed >= a.shutters_at) {{
          const k = Math.min(1, (elapsed - a.shutters_at)/0.8); // slide in 0.8s
          drawShutters(rect, k);
        }}
        requestAnimationFrame(draw);
      }}
      window.addEventListener('load', resize);
      window.addEventListener('resize', resize);
      if (img.complete) resize();
      else img.onload = resize;
    </script>
    """, height=720, scrolling=False)

# ===================== ROOM (image + canvas smoke/shutters) =====================
def render_room(rn: str):
    st.subheader(f"{rn} — Interior View")
    room_b64 = b64_image(ASSETS / f"{rn.replace(' ','_').lower()}.png")

    # Determine primary detector/gas for this room for the demo controls
    primary_key = ROOM_DETECTORS[rn][0]
    gas = gas_from_label(primary_key)

    # Controls
    colL, colR = st.columns([2,1])
    with colL:
        if st.button("← Back to Facility", use_column_width=True):
            set_view("facility")
            st.experimental_rerun()

    with colR:
        st.markdown("**Simulate Spike (Room)**")
        if st.button(f"Simulate {gas} Spike", use_column_width=True, key=f"room_spike_{rn}"):
            st.session_state.spike = {
                "room": rn,
                "gas": gas,
                "start_ts": time.time(),
                "duration": 14,
                "shutters_at": 5,
                "fade_after": 9
            }
            simulate_live_values()
            st.experimental_rerun()

    # Pack active spike info for this room
    sp = st.session_state.spike
    active = None
    if sp and sp["room"] == rn:
        rgba = GAS_COLOR.get(sp["gas"], (239,68,68,0.25))
        active = {**sp, "color": rgba}

    payload = json.dumps({
        "image": room_b64,
        "active": active
    })

    # Canvas animation
    components.html(f"""
    <div style="position:relative; width:100%; max-width:1200px; margin: 8px 0 16px 0;">
      <img id="bg" src="{room_b64}" style="width:100%; height:auto; display:block; border-radius:12px; border:1px solid #1f2a44;"/>
      <canvas id="fx" style="position:absolute; left:0; top:0; width:100%; height:100%; pointer-events:none;"></canvas>
    </div>
    <script>
      const payload = {payload};
      const img = document.getElementById('bg');
      const canvas = document.getElementById('fx');
      const ctx = canvas.getContext('2d');

      function resize() {{
        const r = img.getBoundingClientRect();
        canvas.width = r.width; canvas.height = r.height;
        draw();
      }}

      function drawBlob(cx, cy, baseR, color, layers=14) {{
        for (let i=0;i<layers;i++) {{
          const k = 1 - i/layers;
          const r = baseR * (0.25 + 0.85*k) * (1 + 0.08*Math.sin(i*1.7));
          const a = color[3] * (0.7*k);
          ctx.beginPath();
          ctx.fillStyle = `rgba(${color[0]},${color[1]},${color[2]},${a})`;
          ctx.ellipse(cx + 6*Math.sin(i*0.9), cy + 4*Math.cos(i*1.1), r*1.2, r, 0, 0, Math.PI*2);
          ctx.fill();
        }}
      }}

      function drawShutters(k) {{
        // slide from top
        const w = canvas.width, h = canvas.height;
        const y = -h*(1-k);
        ctx.fillStyle = 'rgba(148,163,184,0.22)';
        ctx.fillRect(0, y, w, h);
        ctx.strokeStyle = 'rgba(148,163,184,0.35)';
        ctx.lineWidth = 2;
        for (let x=0; x<w; x+=14) {{
          ctx.beginPath();
          ctx.moveTo(x, y);
          ctx.lineTo(x+22, y+h);
          ctx.stroke();
        }}
      }}

      function draw() {{
        ctx.clearRect(0,0,canvas.width,canvas.height);
        if (!payload.active) return;
        const now = Date.now()/1000;
        const a = payload.active;
        const elapsed = now - a.start_ts;
        const total = a.duration;
        const color = a.color;
        const r = img.getBoundingClientRect();
        // Use mid-right as leak source visually
        const cx = r.width*0.62, cy = r.height*0.48;

        let p = Math.max(0, Math.min(1, elapsed / total));
        let smokeP = Math.min(1, p*1.2);
        if (elapsed > a.fade_after) {{
          const fadeK = Math.min(1, (elapsed - a.fade_after) / (total - a.fade_after + 0.01));
          smokeP = Math.max(0, 1 - fadeK);
        }}

        // base radius
        const baseR = Math.max(r.width, r.height) * 0.12 * smokeP;
        // multi-blob to feel fume-like
        drawBlob(cx, cy, baseR, color, 16);
        drawBlob(cx-60, cy-20, baseR*0.9, color, 14);
        drawBlob(cx+40, cy+30, baseR*0.8, color, 12);

        if (elapsed >= a.shutters_at) {{
          const k = Math.min(1, (elapsed - a.shutters_at)/0.8);
          drawShutters(k);
        }}
        requestAnimationFrame(draw);
      }}

      window.addEventListener('load', resize);
      window.addEventListener('resize', resize);
      if (img.complete) resize();
      else img.onload = resize;
    </script>
    """, height=720, scrolling=False)

    # Detector list + simple trend placeholder
    st.markdown("### Detectors")
    for key in ROOM_DETECTORS.get(rn, []):
        c1, c2, c3 = st.columns([3,3,2])
        with c1:
            st.write(key)
            if st.button("Simulate Spike", key=f"spike_{key}", use_column_width=True):
                g = gas_from_label(key)
                st.session_state.spike = {
                    "room": rn,
                    "gas": g,
                    "start_ts": time.time(),
                    "duration": 14,
                    "shutters_at": 5,
                    "fade_after": 9
                }
                simulate_live_values()
                st.experimental_rerun()
        with c2:
            simulate_live_values()
            df = get_series(key)
            if df.empty:
                st.line_chart(pd.DataFrame({"value": []}))
            else:
                st.line_chart(pd.DataFrame({"value": df["value"].tail(150)}))
        with c3:
            live = st.session_state.latest.get(key, (0, float("nan")))[1]
            g = gas_from_label(key)
            thr = DEFAULT_THR[g]
            if math.isnan(live):
                st.info("No data yet")
            else:
                s = status_for_value(g, live)
                if s == "ALARM":
                    st.error(f"ALARM • {live:.2f}{thr['units']}")
                elif s == "WARN":
                    st.warning(f"WARN • {live:.2f}{thr['units']}")
                else:
                    st.success(f"Healthy • {live:.2f}{thr['units']}")

# ===================== ROUTING =====================
render_sidebar_ai()

if st.session_state.view == "facility":
    render_facility()
elif st.session_state.view == "room" and st.session_state.room:
    render_room(st.session_state.room)


