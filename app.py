# Pharma Safety HMI — AI First (2.5D blueprint + live charts + smoke/shutters)
import os, time, math, json, base64
from pathlib import Path
from typing import Optional
import streamlit as st
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import streamlit.components.v1 as components

# -------------------- CONFIG --------------------
st.set_page_config(page_title="Pharma Safety HMI — AI First", layout="wide")

HERE = Path(__file__).parent.resolve()
ASSETS = (HERE / "assets").resolve()
ASSETS.mkdir(parents=True, exist_ok=True)

ROOMS = ["Room 1", "Room 2", "Room 3", "Room 12", "Production 1", "Production 2"]
ROOM_DETECTORS = {
    "Room 1": ["Room 1: NH3"],
    "Room 2": ["Room 2: CO"],
    "Room 3": ["Room 3: O2"],
    "Room 12": ["Room 12: Ethanol"],
    "Production 1": ["Production 1: O2", "Production 1: CH4"],
    "Production 2": ["Production 2: O2", "Production 2: H2S"],
}
# Facility clickable rectangles (percent of image width/height): left, top, width, height
ROOM_RECTS_PCT = {
    "Room 1":       (6.0,  8.0,  22.0, 20.0),
    "Room 2":       (30.0,  8.0,  22.0, 20.0),
    "Room 3":       (54.0,  8.0,  22.0, 20.0),
    "Room 12":      (78.0,  8.0,  18.0, 20.0),
    "Production 1": (18.0, 40.0, 30.0, 30.0),
    "Production 2": (52.0, 40.0, 30.0, 30.0),
}

# Gas -> smoke color (RGBA with alpha 0-1)
GAS_COLOR = {
    "NH3":      (168, 85, 247, 0.24),   # purple
    "CO":       (239, 68, 68, 0.26),    # red
    "O2":       (30, 58, 138, 0.30),    # deep blue (low O2 "void")
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

# -------------------- STATE --------------------
if "view" not in st.session_state: st.session_state.view = "facility"
if "room" not in st.session_state: st.session_state.room = None
if "spike" not in st.session_state: st.session_state.spike = None  # dict with room/gas/timing

def set_view(view: str, room: Optional[str] = None):
    st.session_state.view = view
    st.session_state.room = room

# -------------------- HELPERS --------------------
def gas_from_label(key: str) -> str:
    k = key.lower()
    if "o2" in k: return "O2"
    if "h2s" in k: return "H2S"
    if "ch4" in k or "lel" in k or "methane" in k: return "CH4"
    if "nh3" in k or "ammonia" in k: return "NH3"
    if "ethanol" in k: return "Ethanol"
    if "co" in k and "co2" not in k: return "CO"
    return "CO"

def b64_image(path: Path) -> str:
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")

# -------------------- AUTO-GENERATE 2.5D FACILITY --------------------
def draw_facility_2p5d(path: Path, rects_pct: dict[str, tuple[float,float,float,float]]):
    W, H = 1400, 820
    img = Image.new("RGBA", (W, H), (10, 15, 25, 255))
    d = ImageDraw.Draw(img)

    # faint grid glow
    grid = Image.new("RGBA", (W, H), (0,0,0,0))
    dg = ImageDraw.Draw(grid)
    for x in range(0, W, 40): dg.line((x, 0, x, H), fill=(22, 78, 99, 25), width=1)
    for y in range(0, H, 40): dg.line((0, y, W, y), fill=(22, 78, 99, 25), width=1)
    grid = grid.filter(ImageFilter.GaussianBlur(0.6))
    img.alpha_composite(grid)

    wall_neon = (0, 200, 255, 255)
    wall_inner = (15, 90, 135, 255)
    floor_col = (18, 28, 45, 255)
    shadow = (5, 8, 14, 130)

    # % -> px
    rooms_px = {}
    for name, (L,T,Wp,Hp) in rects_pct.items():
        x0 = int(L*W/100); y0 = int(T*H/100)
        x1 = x0 + int(Wp*W/100); y1 = y0 + int(Hp*H/100)
        rooms_px[name] = (x0,y0,x1,y1)

    # floors with drop shadow
    for (x0,y0,x1,y1) in rooms_px.values():
        ImageDraw.Draw(img).rectangle((x0+7, y0+9, x1+7, y1+9), fill=shadow)
        d.rounded_rectangle((x0, y0, x1, y1), 18, fill=floor_col)

    # wall thickness + neon rim
    for (x0,y0,x1,y1) in rooms_px.values():
        d.rounded_rectangle((x0, y0, x1, y0+12), 6, fill=wall_inner)
        d.rounded_rectangle((x0, y1-12, x1, y1), 6, fill=wall_inner)
        d.rounded_rectangle((x0, y0, x0+12, y1), 6, fill=wall_inner)
        d.rounded_rectangle((x1-12, y0, x1, y1), 6, fill=wall_inner)
        d.rounded_rectangle((x0, y0, x1, y1), 18, outline=wall_neon, width=3)

    # furniture (blueprint line art)
    def boiler(x,y,w,h):
        d.rounded_rectangle((x,y,x+w,y+h), 12, outline=wall_neon, width=2)
        d.ellipse((x+w*0.35, y-10, x+w*0.65, y+14), outline=wall_neon, width=2)
    def tank(x,y,r):
        d.ellipse((x-r,y-r,x+r,y+r), outline=wall_neon, width=2)
    def bench(x,y,w,h):
        d.rounded_rectangle((x,y,x+w,y+h), 8, outline=wall_neon, width=2)

    for name,(x0,y0,x1,y1) in rooms_px.items():
        cx, cy = (x0+x1)//2, (y0+y1)//2
        if "Production 1" in name:
            boiler(x0+28, y0+40, 120, 160); bench(cx-140, cy+40, 120, 22); bench(cx+20, cy+40, 120, 22); tank(x1-70, y0+90, 40)
        elif "Production 2" in name:
            boiler(x1-160, y0+40, 120, 160); tank(x0+80, cy, 45); bench(cx-60, cy+60, 140, 22)
        elif "Room 1" in name:
            tank(cx-30, cy-10, 35); bench(x0+30, y1-60, 160, 22)
        elif "Room 2" in name:
            boiler(cx-70, y0+30, 140, 140)
        elif "Room 3" in name:
            bench(cx-90, cy-20, 180, 22); tank(x1-80, cy+20, 35)
        elif "Room 12" in name:
            bench(x0+40, y0+40, 160, 22); bench(x1-200, y1-70, 160, 22)
        d.text((x0+14, y0+10), name, fill=wall_neon)

    img.convert("RGB").save(path)

# ensure facility image exists
fac_png = ASSETS / "facility.png"
if not fac_png.exists():
    draw_facility_2p5d(fac_png, ROOM_RECTS_PCT)

# ensure simple room images exist (matching style)
def draw_room_png(path: Path, label: str):
    W, H = 1200, 700
    img = Image.new("RGBA", (W, H), (15, 20, 35, 255))
    d = ImageDraw.Draw(img)
    # floor + shadow
    d.rectangle((18, 26, W-18, H-18), fill=(5,8,14,130))
    d.rounded_rectangle((10, 18, W-10, H-10), 16, fill=(18,28,45,255))
    # walls
    d.rounded_rectangle((10, 18, W-10, 30), 8, fill=(15,90,135,255))
    d.rounded_rectangle((10, H-30, W-10, H-10), 8, fill=(15,90,135,255))
    d.rounded_rectangle((10, 18, 22, H-10), 8, fill=(15,90,135,255))
    d.rounded_rectangle((W-22, 18, W-10, H-10), 8, fill=(15,90,135,255))
    d.rounded_rectangle((10, 18, W-10, H-10), 16, outline=(0,200,255,255), width=3)
    # a few devices
    d.rounded_rectangle((140, 180, 280, 360), 12, outline=(0,200,255,255), width=2)
    d.ellipse((850, 220, 920, 290), outline=(0,200,255,255), width=2)
    d.rounded_rectangle((500, 460, 760, 490), 8, outline=(0,200,255,255), width=2)
    d.text((26, 26), label, fill=(0,200,255,255))
    img.convert("RGB").save(path)

for rn in ROOMS:
    p = ASSETS / f"{rn.replace(' ', '_').lower()}.png"
    if not p.exists():
        draw_room_png(p, rn)

# -------------------- AI CHAT (sidebar) --------------------
def render_sidebar_ai():
    st.sidebar.header("AI Safety Assistant")
    sp = st.session_state.spike
    data = None
    if sp:
        data = {
            "room": sp["room"], "gas": sp["gas"], "start_ts": sp["start_ts"],
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
      function ts() {{ return new Date().toLocaleTimeString(); }}
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
        bubble(`[${{ts()}}] 🤖 AI: ${{ gasEmoji[data.gas] || '' }} ${{data.events[0].msg}}`);
        for (let i=1;i<data.events.length;i++) {{
          const ev = data.events[i];
          setTimeout(() => {{
            bubble(`[${{ts()}}] 🤖 AI: ${{ gasEmoji[data.gas] || '' }} ${{ev.msg}}`);
          }}, ev.at*1000);
        }}
      }}
    </script>
    """, height=560, scrolling=True)

# -------------------- FACILITY VIEW --------------------
def render_facility():
    st.title("Pharma Safety HMI — AI First")
    st.subheader("Facility Overview (2.5D Blueprint)")
    facility_b64 = b64_image(ASSETS / "facility.png")

    rects = ROOM_RECTS_PCT
    sp = st.session_state.spike
    active = None
    if sp:
        rgba = GAS_COLOR.get(sp["gas"], (239,68,68,0.25))
        active = {
            "room": sp["room"], "gas": sp["gas"], "start_ts": sp["start_ts"],
            "duration": sp["duration"], "shutters_at": sp["shutters_at"],
            "fade_after": sp["fade_after"], "color": rgba, "rect": rects.get(sp["room"])
        }

    payload = json.dumps({"image": facility_b64, "rects": rects, "active": active})

    # Navigation buttons
    st.markdown("#### Rooms")
    cols = st.columns(3)
    for i, rn in enumerate(ROOMS):
        with cols[i % 3]:
            if st.button(rn, key=f"enter_{rn}"):
                set_view("room", rn)
                st.rerun()

    # Spike controls
    st.markdown("---")
    colA, colB = st.columns([1,2])
    with colA:
        room_choice = st.selectbox("Simulate spike in…", ROOMS, key="fac_spike_room")
        first_key = ROOM_DETECTORS[room_choice][0]
        gas = gas_from_label(first_key)
        if st.button("Simulate Spike (Facility View)", key="fac_spike_btn"):
            st.session_state.spike = {
                "room": room_choice, "gas": gas, "start_ts": time.time(),
                "duration": 14, "shutters_at": 5, "fade_after": 9
            }
            st.rerun()
    with colB:
        st.caption("Legend:  🟣 NH₃   🔴 CO   🔵 Low O₂   🟠 Ethanol   🟡 CH₄   🟢 H₂S")

    # Image + canvas overlay (smoke + shutters)
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
          ctx.fillStyle = `rgba(${{color[0]}},${{color[1]}},${{color[2]}},${{alpha}})`;
          const inset = (1 - progress) * (Math.min(w,h)*0.45) * (i/steps);
          ctx.fillRect(l+inset, t+inset, w-2*inset, h-2*inset);
        }}
      }}
      function drawShutters(rect, k) {{
        const [l,t,w,h] = rect;
        const y = t + (-h * (1-k));
        ctx.fillStyle = 'rgba(148,163,184,0.22)';
        ctx.fillRect(l, y, w, h);
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
        if (elapsed > a.fade_after) {{
          const fadeK = Math.min(1, (elapsed - a.fade_after) / (a.duration - a.fade_after + 0.01));
          smokeP = Math.max(0, 1 - fadeK);
        }}
        drawSmokeRect(rect, smokeP, a.color);
        if (elapsed >= a.shutters_at) {{
          const k = Math.min(1, (elapsed - a.shutters_at)/0.8);
          drawShutters(rect, k);
        }}
        requestAnimationFrame(draw);
      }}
      window.addEventListener('load', resize);
      window.addEventListener('resize', resize);
      if (img.complete) resize(); else img.onload = resize;
    </script>
    """, height=720, scrolling=False)

# -------------------- ROOM VIEW --------------------
def render_room(rn: str):
    st.subheader(f"{rn} — Interior View")
    room_b64 = b64_image(ASSETS / f"{rn.replace(' ','_').lower()}.png")

    # Primary gas in this room (for one-click demo)
    primary_key = ROOM_DETECTORS[rn][0]
    gas = gas_from_label(primary_key)

    colL, colR = st.columns([2,1])
    with colL:
        if st.button("← Back to Facility", key=f"back_{rn}"):
            set_view("facility")
            st.rerun()
    with colR:
        st.markdown("**Simulate Spike (Room)**")
        if st.button(f"Simulate {gas} Spike", key=f"room_spike_{rn}"):
            st.session_state.spike = {
                "room": rn, "gas": gas, "start_ts": time.time(),
                "duration": 14, "shutters_at": 5, "fade_after": 9
            }
            st.rerun()

    # If spike for this room -> animate here too
    sp = st.session_state.spike
    active = None
    if sp and sp["room"] == rn:
        rgba = GAS_COLOR.get(sp["gas"], (239,68,68,0.25))
        active = {**sp, "color": rgba}
    payload = json.dumps({"image": room_b64, "active": active})

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
          ctx.fillStyle = `rgba(${{color[0]}},${{color[1]}},${{color[2]}},${{a}})`;
          ctx.ellipse(cx + 6*Math.sin(i*0.9), cy + 4*Math.cos(i*1.1), r*1.2, r, 0, 0, Math.PI*2);
          ctx.fill();
        }}
      }}

      function drawShutters(k) {{
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
        const cx = r.width*0.62, cy = r.height*0.48;

        let p = Math.max(0, Math.min(1, elapsed / total));
        let smokeP = Math.min(1, p*1.2);
        if (elapsed > a.fade_after) {{
          const fadeK = Math.min(1, (elapsed - a.fade_after) / (total - a.fade_after + 0.01));
          smokeP = Math.max(0, 1 - fadeK);
        }}

        const baseR = Math.max(r.width, r.height) * 0.12 * smokeP;
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
      if (img.complete) resize(); else img.onload = resize;
    </script>
    """, height=720, scrolling=False)

    # Detectors + live chart (Chart.js; 500ms updates)
    st.markdown("### Detectors")
    for key in ROOM_DETECTORS.get(rn, []):
        c1, c2, c3 = st.columns([3,4,2])
        with c1:
            st.write(key)
            if st.button("Simulate Spike", key=f"spike_{key}"):
                g = gas_from_label(key)
                st.session_state.spike = {
                    "room": rn, "gas": g, "start_ts": time.time(),
                    "duration": 14, "shutters_at": 5, "fade_after": 9
                }
                st.rerun()
        with c2:
            g = gas_from_label(key)
            thr = DEFAULT_THR[g]
            sp_here = st.session_state.spike
            active_for_this = bool(sp_here and sp_here["room"] == rn and sp_here["gas"] == g)
            js_payload = json.dumps({
                "units": thr["units"], "mode": thr["mode"],
                "warn": thr["warn"], "alarm": thr["alarm"],
                "spike": active_for_this
            })
            components.html(f"""
            <div style="background:#0b1220;border:1px solid #1f2a44;border-radius:10px;padding:6px">
              <canvas id="ch_{key.replace(' ','_')}" height="140"></canvas>
            </div>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <script>
              const cfg = {js_payload};
              const ctx = document.getElementById('ch_{key.replace(' ','_')}').getContext('2d');
              const N = 120; // last 60s @ 500ms
              const data = [];
              const labels = [];
              for (let i=0;i<N;i++){{labels.push(''); data.push(null);}}
              const color = 'rgba(59,130,246,0.9)';
              const chart = new Chart(ctx, {{
                type: 'line',
                data: {{
                  labels: labels,
                  datasets: [{{
                    label: 'Live',
                    data: data,
                    borderColor: color,
                    backgroundColor: 'rgba(59,130,246,0.2)',
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.25
                  }}]
                }},
                options: {{
                  responsive: true,
                  animation: false,
                  scales: {{
                    x: {{ display:false }},
                    y: {{
                      beginAtZero: false,
                      grid: {{ color: 'rgba(148,163,184,0.15)' }},
                      ticks: {{ color:'#cbd5e1' }}
                    }}
                  }},
                  plugins: {{
                    legend: {{ display:false }},
                    tooltip: {{ enabled: true }}
                  }}
                }}
              }});
              function baseValue(t) {{
                if (cfg.mode === 'low' && cfg.units.includes('%')) {{
                  return 20.8 + 0.2*Math.sin(t/2200);
                }} else if (cfg.units === 'ppm') {{
                  return 10 + 6*Math.sin(t/1500);
                }} else if (cfg.units.includes('%LEL')) {{
                  return 4 + 2*Math.sin(t/1100);
                }} else {{
                  return 10 + 5*Math.sin(t/1500);
                }}
              }}
              let t0 = performance.now();
              let spikeK = 0;
              function step() {{
                const now = performance.now();
                const t = now - t0;
                if (cfg.spike) spikeK = Math.min(1, spikeK + 0.02);
                else           spikeK = Math.max(0, spikeK - 0.02);
                let v = baseValue(t);
                if (cfg.mode === 'low' && cfg.units.includes('%')) v -= 2.5*spikeK;
                else v += 12*spikeK;
                data.push(v);
                if (data.length > N) data.shift();
                chart.update();
                setTimeout(step, 500);
              }}
              step();
            </script>
            """, height=190, scrolling=False)
        with c3:
            st.caption(f"{DEFAULT_THR[g]['mode'].upper()} mode")
            st.caption(f"Warn: {DEFAULT_THR[g]['warn']}  •  Alarm: {DEFAULT_THR[g]['alarm']} {DEFAULT_THR[g]['units']}")

# -------------------- ROUTER --------------------
render_sidebar_ai()
if st.session_state.view == "facility":
    render_facility()
elif st.session_state.view == "room" and st.session_state.room:
    render_room(st.session_state.room)

