"""
🛰️ ISRO NetOps Predictive Co-Pilot — Streamlit Dashboard (v2.0)

Stitch-inspired premium dark theme with five tabs:
1. 📊 Predictive Dashboard — Live KPI overview
2. 🗺️ Network Topology   — Interactive risk graph
3. 🚨 Predictive Alerts  — Failure predictions + runbooks
4. 📋 System Logs        — Live syslog stream with filtering
5. 💬 Co-Pilot Chat      — RAG-grounded operator Q&A
"""

import sys
import os
import io

# Fix Windows cp1252 encoding — must run before ANY emoji print() call
for _stream_name in ('stdout', 'stderr'):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, 'reconfigure'):
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

import re
import time
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
import networkx as nx

from src.agent.orchestrator import get_orchestrator
from src.utils.config import analytics_cfg

# ══════════════════════════════════════════════════════════════════════════════
# Page Config
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="ISRO NetOps Co-Pilot",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════════════════════
# Auth Gate — Show auth page between landing and dashboard
# ══════════════════════════════════════════════════════════════════════════════

_qp = st.query_params
_view = _qp.get("view", "")

# Start HTTP server on port 8502 for landing page (background, once)
import threading as _threading
import http.server as _http_server
import functools as _functools

_landing_dir = PROJECT_ROOT / "landing"
try:
    import socket as _sock
    _s = _sock.socket()
    _s.bind(("", 8502))
    _s.close()
    # Port free → start server
    def _run_landing_server():
        handler = _functools.partial(
            _http_server.SimpleHTTPRequestHandler,
            directory=str(_landing_dir),
        )
        srv = _http_server.HTTPServer(("", 8502), handler)
        srv.serve_forever()
    _threading.Thread(target=_run_landing_server, daemon=True).start()
except OSError:
    pass  # already running

# Patch landing page link → auth page
_html_path = _landing_dir / "index.html"
if _html_path.exists():
    _raw = _html_path.read_text(encoding="utf-8")
    _raw = _raw.replace('href="http://localhost:8501"', 'href="http://localhost:8502/auth.html"')
    (_landing_dir / "_index_patched.html").write_text(_raw, encoding="utf-8")

if _view == "":
    # Pre-warm the orchestrator (load ML models, build RAG) in the background so dashboard is instant
    if "prewarming" not in st.session_state:
        st.session_state.prewarming = True
        def _prewarm_orch():
            try:
                from src.agent.orchestrator import get_orchestrator
                get_orchestrator().initialize()
            except Exception:
                pass
        _threading.Thread(target=_prewarm_orch, daemon=True).start()

    # Initial visit to localhost:8501 -> Redirect to landing page on port 8502
    st.markdown("""
    <meta http-equiv="refresh" content="0; url=http://localhost:8502/_index_patched.html">
    <style>
        header, footer, #MainMenu { display: none !important; }
        section[data-testid="stSidebar"] { display: none !important; }
        body { background: #070B14 !important; margin: 0; }
    </style>
    """, unsafe_allow_html=True)
    st.stop()

# If _view == "dashboard", it falls through and renders the main dashboard





# ══════════════════════════════════════════════════════════════════════════════
# Premium CSS — Stitch Dark Theme
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

  :root {
    --bg-root:     #080d18;
    --bg-surface:  #0f1629;
    --bg-card:     #141c30;
    --bg-card-h:   #1c2640;
    --bg-panel:    #1a2236;
    --accent-blue: #3b82f6;
    --accent-cyan: #22d3ee;
    --accent-purple:#a855f7;
    --accent-green: #10b981;
    --accent-amber: #f59e0b;
    --accent-red:   #ef4444;
    --accent-pink:  #ec4899;
    --text-1: #f0f6ff;
    --text-2: #8fa0c0;
    --text-3: #4e6080;
    --border: rgba(255,255,255,0.07);
    --glow-blue:   rgba(59,130,246,0.18);
    --glow-purple: rgba(168,85,247,0.18);
  }

  /* ── Base ── */
  html, body, .stApp {
    background-color: var(--bg-root);
    font-family: 'Inter', sans-serif;
    color: var(--text-1);
  }
  .stApp {
    background: var(--bg-root) !important;
  }

  /* ── Sidebar ── */
  section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0a1020 0%, #10183a 100%) !important;
    border-right: 1px solid var(--border) !important;
  }

  /* ── Header Banner ── */
  .hdr-banner {
    background: linear-gradient(135deg, rgba(59,130,246,0.12) 0%, rgba(168,85,247,0.12) 100%);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 22px 32px;
    margin-bottom: 22px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    backdrop-filter: blur(20px);
    box-shadow: 0 4px 40px rgba(59,130,246,0.08);
  }
  .hdr-title {
    color: var(--text-1);
    font-size: 22px;
    font-weight: 800;
    margin: 0;
    letter-spacing: -0.5px;
  }
  .hdr-sub {
    color: var(--text-2);
    font-size: 12px;
    margin-top: 5px;
    letter-spacing: 0.3px;
  }

  /* ── Status badge ── */
  .badge-online {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 7px 16px;
    border-radius: 30px;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    background: rgba(16,185,129,0.12);
    color: #34d399;
    border: 1px solid rgba(16,185,129,0.28);
  }
  .dot-pulse {
    width: 7px; height: 7px;
    background: #10b981;
    border-radius: 50%;
    display: inline-block;
    animation: pulse 2s ease-in-out infinite;
  }
  @keyframes pulse {
    0%,100%{ opacity:1; box-shadow: 0 0 0 0 rgba(16,185,129,0.5); }
    50%{ opacity:0.7; box-shadow: 0 0 0 5px rgba(16,185,129,0); }
  }

  /* ── Metric cards ── */
  .kpi-grid { display:flex; gap:14px; margin-bottom:20px; }
  .kpi-card {
    flex: 1;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 18px 20px;
    position: relative;
    overflow: hidden;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
  }
  .kpi-card:hover { transform: translateY(-2px); box-shadow: 0 8px 30px rgba(0,0,0,0.3); }
  .kpi-card::after {
    content:''; position:absolute; top:0; left:0; right:0;
    height:3px; border-radius:14px 14px 0 0;
  }
  .kpi-blue::after   { background: linear-gradient(90deg,#3b82f6,#22d3ee); }
  .kpi-green::after  { background: linear-gradient(90deg,#10b981,#34d399); }
  .kpi-amber::after  { background: linear-gradient(90deg,#f59e0b,#fbbf24); }
  .kpi-red::after    { background: linear-gradient(90deg,#ef4444,#f87171); }
  .kpi-purple::after { background: linear-gradient(90deg,#a855f7,#c084fc); }
  .kpi-lbl { font-size:11px; font-weight:600; color:var(--text-2); text-transform:uppercase; letter-spacing:1px; }
  .kpi-val { font-size:34px; font-weight:800; color:var(--text-1); line-height:1.1; margin:6px 0 4px; }
  .kpi-sub { font-size:12px; color:var(--text-2); }

  /* ── Alert cards ── */
  .alert-card {
    background: var(--bg-card);
    border-left: 4px solid;
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 13px;
    transition: all 0.25s ease;
  }
  .alert-card:hover { background: var(--bg-card-h); transform: translateX(5px); }
  .alert-critical { border-left-color: #ef4444; }
  .alert-high     { border-left-color: #f59e0b; }
  .alert-medium   { border-left-color: #3b82f6; }
  .alert-low      { border-left-color: #10b981; }
  .alert-hdr { display:flex; justify-content:space-between; align-items:center; margin-bottom:9px; }
  .alert-dev { font-weight:700; color:var(--text-1); font-size:15px; }
  .alert-prob {
    font-family:'JetBrains Mono',monospace;
    font-size:13px; font-weight:700;
    padding:3px 12px; border-radius:8px;
  }
  .prob-critical { background:rgba(239,68,68,0.18); color:#f87171; }
  .prob-high     { background:rgba(245,158,11,0.18); color:#fbbf24; }
  .prob-medium   { background:rgba(59,130,246,0.18); color:#60a5fa; }
  .alert-body { color:var(--text-2); font-size:13px; line-height:1.65; }

  /* ── Chat bubbles ── */
  .chat-wrap { display:flex; flex-direction:column; gap:12px; padding:4px 0; }
  .chat-user {
    align-self: flex-end;
    background: linear-gradient(135deg,rgba(59,130,246,0.22),rgba(168,85,247,0.22));
    border: 1px solid rgba(59,130,246,0.32);
    border-radius: 14px 14px 4px 14px;
    padding: 12px 18px;
    max-width: 78%;
    color: var(--text-1);
    font-size: 14px;
    line-height: 1.65;
  }
  .chat-bot {
    align-self: flex-start;
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: 14px 14px 14px 4px;
    padding: 14px 18px;
    max-width: 85%;
    color: var(--text-1);
    font-size: 14px;
    line-height: 1.7;
  }
  .chat-role { font-weight:700; font-size:12px; margin-bottom:5px; text-transform:uppercase; letter-spacing:0.5px; }
  .chat-user .chat-role { color:#60a5fa; }
  .chat-bot  .chat-role { color:#a78bfa; }
  .chat-src { font-size:11px; color:var(--accent-cyan); margin-top:8px; font-family:'JetBrains Mono',monospace; }

  /* ── System log lines ── */
  .log-stream {
    background: #060b15;
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    line-height: 1.8;
    max-height: 480px;
    overflow-y: auto;
  }
  .log-critical { color: #f87171; }
  .log-error    { color: #fb923c; }
  .log-warning  { color: #fbbf24; }
  .log-info     { color: #94a3b8; }
  .log-debug    { color: #475569; }
  .log-ts       { color: #334155; margin-right: 8px; }
  .log-dev      { color: #38bdf8; margin-right: 8px; font-weight:600; }
  .log-lvl-crit { color:#f87171; font-weight:700; }
  .log-lvl-err  { color:#fb923c; font-weight:700; }
  .log-lvl-warn { color:#fbbf24; font-weight:700; }
  .log-lvl-info { color:#64748b; }

  /* ── Tabs ── */
  .stTabs [data-baseweb="tab-list"] {
    gap:6px; background:transparent; padding:2px 0 10px;
  }
  .stTabs [data-baseweb="tab"] {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    color: var(--text-2);
    font-weight: 600;
    font-size: 13px;
    padding: 10px 20px;
    transition: all 0.2s;
  }
  .stTabs [data-baseweb="tab"]:hover { background: var(--bg-card-h); color:var(--text-1); }
  .stTabs [aria-selected="true"] {
    background: linear-gradient(135deg,rgba(59,130,246,0.28),rgba(168,85,247,0.28)) !important;
    border-color: rgba(59,130,246,0.5) !important;
    color: var(--text-1) !important;
    box-shadow: 0 2px 12px rgba(59,130,246,0.2);
  }
  .stTabs [data-baseweb="tab-highlight"] { display:none !important; }

  /* ── Selectbox ── */
  .stSelectbox > div > div {
    background: var(--bg-card) !important;
    border-color: var(--border) !important;
    color: var(--text-1) !important;
  }

  /* ── Misc ── */
  .stMetric { background: var(--bg-card) !important; border-radius:12px !important; padding:16px !important; }
  .stMetric label { color: var(--text-2) !important; font-size:11px !important; text-transform:uppercase; letter-spacing:0.8px; }
  .stMetric [data-testid="metric-container"] > div:first-child { color: var(--text-1) !important; font-size: 28px !important; font-weight:800 !important; }

  section[data-testid="stExpander"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
  }

  footer { visibility:hidden; }
  header[data-testid="stHeader"] { background:transparent !important; z-index: 1000 !important; }

  /* ── Sidebar Toggle Button (Hide/Unhide) ── */
  [data-testid="collapsedControl"] svg,
  [data-testid="stSidebarCollapseButton"] svg {
    display: none !important;
  }
  
  [data-testid="collapsedControl"] button,
  [data-testid="stSidebarCollapseButton"] {
    color: transparent !important;
    position: relative !important;
    width: 40px !important;
    height: 40px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    cursor: pointer !important;
    z-index: 99999 !important;
  }
  
  [data-testid="collapsedControl"] button::before,
  [data-testid="stSidebarCollapseButton"]::before {
    content: "☰" !important;
    font-size: 22px;
    font-weight: 800;
    line-height: 1;
    color: var(--accent-cyan) !important;
    position: absolute;
    font-family: sans-serif !important;
    pointer-events: none !important;
  }

  [data-testid="collapsedControl"],
  [data-testid="stSidebarCollapseButton"],
  [data-testid="stSidebar"] button[kind="header"] {
    background: rgba(34, 211, 238, 0.15) !important;
    border: 1px solid var(--accent-cyan) !important;
    border-radius: 8px !important;
    transition: all 0.2s ease;
  }
  [data-testid="collapsedControl"]:hover,
  [data-testid="stSidebarCollapseButton"]:hover,
  [data-testid="stSidebar"] button[kind="header"]:hover {
    background: var(--accent-cyan) !important;
    box-shadow: 0 0 15px rgba(34, 211, 238, 0.4) !important;
  }
  
  [data-testid="collapsedControl"] button:hover::before,
  [data-testid="stSidebarCollapseButton"]:hover::before {
    color: #080d18 !important;
  }

  ::-webkit-scrollbar { width:5px; height:5px; }
  ::-webkit-scrollbar-track { background:var(--bg-root); }
  ::-webkit-scrollbar-thumb { background:#1e293b; border-radius:3px; }
  ::-webkit-scrollbar-thumb:hover { background:#334155; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Initialize System
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def init_system():
    orch = get_orchestrator()
    orch.initialize()
    return orch


if "initialized" not in st.session_state:
    with st.spinner("🛰️ Initializing Co-Pilot — Generating data, training models, building knowledge base…"):
        orch = init_system()
    st.session_state.initialized = True
    st.session_state.chat_messages = []
else:
    orch = init_system()


# ══════════════════════════════════════════════════════════════════════════════
# Sidebar
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("""
    <div style="text-align:center;padding:24px 0 16px;">
      <div style="font-size:52px;margin-bottom:10px;">🛰️</div>
      <h2 style="color:#f0f6ff;margin:0;font-size:17px;font-weight:800;letter-spacing:-0.3px;">NetOps Co-Pilot</h2>
      <p style="color:#4e6080;font-size:11px;margin-top:5px;">Predictive • Air-Gapped • MLS-Aware</p>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    model_metrics = orch.get_model_metrics()

    st.markdown("#### 📊 System Status")
    st.markdown("""
    <div style="background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.28);
                border-radius:10px;padding:11px 16px;margin:8px 0;display:flex;align-items:center;gap:8px;">
      <span class="dot-pulse"></span>
      <span style="color:#34d399;font-weight:700;font-size:12px;letter-spacing:0.5px;">SYSTEM ONLINE</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="background:var(--bg-card);border-radius:10px;padding:14px;margin:8px 0;
                border:1px solid var(--border);">
      <div style="color:#4e6080;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;">
        Model Performance
      </div>
      <div style="display:flex;justify-content:space-between;">
        <div style="text-align:center;">
          <div style="color:#f0f6ff;font-size:22px;font-weight:800;">{model_metrics.get('f1_score',0):.2f}</div>
          <div style="color:#4e6080;font-size:10px;">F1 Score</div>
        </div>
        <div style="text-align:center;">
          <div style="color:#f0f6ff;font-size:22px;font-weight:800;">{model_metrics.get('auc_roc',0):.2f}</div>
          <div style="color:#4e6080;font-size:10px;">AUC-ROC</div>
        </div>
        <div style="text-align:center;">
          <div style="color:#f0f6ff;font-size:22px;font-weight:800;">{model_metrics.get('precision',0):.2f}</div>
          <div style="color:#4e6080;font-size:10px;">Precision</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    st.markdown("#### 🔐 MLS Access Control")
    clearance = st.selectbox(
        "Operator Clearance",
        ["UNCLASSIFIED", "RESTRICTED", "CONFIDENTIAL"],
        index=1,
        key="clearance_level",
    )

    st.divider()

    st.markdown("""
    <div style="background:rgba(168,85,247,0.1);border:1px solid rgba(168,85,247,0.28);
                border-radius:10px;padding:11px 16px;margin:8px 0;">
      <div style="color:#c084fc;font-weight:700;font-size:12px;">🔒 AIR-GAPPED MODE</div>
      <div style="color:#4e6080;font-size:11px;margin-top:5px;line-height:1.6;">
        Zero outbound network calls<br>All models run locally on CPU
      </div>
    </div>
    """, unsafe_allow_html=True)

    import streamlit.components.v1 as components
    components.html("""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@700&display=swap');
      a {
        display: block;
        text-align: center;
        padding: 12px;
        background: linear-gradient(135deg, rgba(239,68,68,0.15), rgba(220,38,38,0.05));
        border: 1px solid rgba(239,68,68,0.3);
        border-radius: 10px;
        color: #f87171;
        font-family: 'Inter', sans-serif;
        font-weight: 700;
        text-decoration: none;
        font-size: 13px;
        letter-spacing: 0.5px;
        transition: all 0.2s ease;
        cursor: pointer;
      }
      a:hover {
        background: rgba(239,68,68,0.25);
        border-color: rgba(239,68,68,0.5);
        color: #fca5a5;
      }
      body { margin: 0; padding: 0; overflow: hidden; }
    </style>
    <a onclick="if(document.referrer && !document.referrer.includes('8501')) { window.parent.location.href = document.referrer; } else { window.parent.history.back(); }">
      🚪 Exit Dashboard
    </a>
    """, height=50)

    st.markdown(f"""
    <div style="color:#334155;font-size:10px;text-align:center;margin-top:24px;">
      v2.0.0 &nbsp;|&nbsp; {datetime.now().strftime("%Y-%m-%d %H:%M UTC")}
    </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Load live data
# ══════════════════════════════════════════════════════════════════════════════

topo_data    = orch.get_topology_data()
alerts       = orch.get_alerts()
risk_summary = orch.get_risk_summary()

devices        = topo_data["devices"]
total_devices  = len(devices)
critical_count = sum(1 for d in devices.values() if d["status"] == "critical")
warning_count  = sum(1 for d in devices.values() if d["status"] == "warning")
healthy_count  = total_devices - critical_count - warning_count


# ══════════════════════════════════════════════════════════════════════════════
# Header Banner
# ══════════════════════════════════════════════════════════════════════════════

st.markdown(f"""
<div class="hdr-banner">
  <div>
    <div class="hdr-title">🛰️ ISRO NetOps Predictive Co-Pilot</div>
    <div class="hdr-sub">Air-Gapped &nbsp;•&nbsp; Predictive Failure Analytics &nbsp;•&nbsp; RAG-Grounded Operations</div>
  </div>
  <span class="badge-online"><span class="dot-pulse"></span>Monitoring Active</span>
</div>
""", unsafe_allow_html=True)


# ── KPI Row ──
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.markdown(f"""
    <div class="kpi-card kpi-blue">
      <div class="kpi-lbl">Total Devices</div>
      <div class="kpi-val">{total_devices}</div>
      <div class="kpi-sub" style="color:#60a5fa;">Monitored 24/7</div>
    </div>""", unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="kpi-card kpi-green">
      <div class="kpi-lbl">Healthy</div>
      <div class="kpi-val">{healthy_count}</div>
      <div class="kpi-sub" style="color:#34d399;">✓ Nominal</div>
    </div>""", unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="kpi-card kpi-amber">
      <div class="kpi-lbl">Warning</div>
      <div class="kpi-val">{warning_count}</div>
      <div class="kpi-sub" style="color:#fbbf24;">↗ Degrading</div>
    </div>""", unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="kpi-card kpi-red">
      <div class="kpi-lbl">Critical</div>
      <div class="kpi-val">{critical_count}</div>
      <div class="kpi-sub" style="color:#f87171;">⚠ Action Required</div>
    </div>""", unsafe_allow_html=True)

with col5:
    st.markdown(f"""
    <div class="kpi-card kpi-purple">
      <div class="kpi-lbl">Active Alerts</div>
      <div class="kpi-val">{len(alerts)}</div>
      <div class="kpi-sub" style="color:#c084fc;">Predictive</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Main Tabs
# ══════════════════════════════════════════════════════════════════════════════

tab_topo, tab_alerts, tab_logs, tab_chat, tab_forecast = st.tabs([
    "🗺️ Network Topology",
    "🚨 Predictive Alerts",
    "📋 System Logs",
    "💬 Co-Pilot Chat",
    "📈 Forecast Accuracy",
])


# ════════════════════════════════════════
# TAB 1 — Network Topology
# ════════════════════════════════════════

with tab_topo:
    st.markdown("### 🗺️ Network Topology — Live Risk View")
    st.markdown('<p style="color:#8fa0c0;font-size:13px;">Node color indicates predicted failure risk. Hover for device details.</p>',
                unsafe_allow_html=True)

    edges = topo_data["edges"]
    G = nx.Graph()
    for dev_id in devices:
        G.add_node(dev_id)
    for edge in edges:
        G.add_edge(edge["source"], edge["target"])

    pos = nx.spring_layout(G, seed=42, k=2.5)

    status_colors = {
        "healthy":  "#10b981",
        "degraded": "#3b82f6",
        "warning":  "#f59e0b",
        "critical": "#ef4444",
    }
    type_icons = {"router": "🔀", "switch": "🔗", "server": "🖥️", "firewall": "🛡️"}

    edge_x, edge_y = [], []
    for edge in edges:
        if edge["source"] in pos and edge["target"] in pos:
            x0, y0 = pos[edge["source"]]
            x1, y1 = pos[edge["target"]]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=1.2, color="rgba(100,116,139,0.25)"),
        hoverinfo="none", mode="lines",
    )

    node_traces = []
    for status, color in status_colors.items():
        nx_, ny_, texts, hovers, sizes = [], [], [], [], []
        for dev_id, meta in devices.items():
            if meta.get("status") == status and dev_id in pos:
                x, y = pos[dev_id]
                nx_.append(x); ny_.append(y)
                icon = type_icons.get(meta["type"], "📡")
                risk = meta.get("risk_score", 0)
                texts.append(icon)
                hovers.append(
                    f"<b>{dev_id}</b><br>"
                    f"Type: {meta['type'].title()}<br>"
                    f"Vendor: {meta['vendor']}<br>"
                    f"IP: {meta['ip']}<br>"
                    f"Location: {meta['location']}<br>"
                    f"Status: {meta['status'].upper()}<br>"
                    f"Risk Score: {risk:.1%}"
                )
                sizes.append(22 + risk * 32)

        if nx_:
            node_traces.append(go.Scatter(
                x=nx_, y=ny_,
                mode="markers+text",
                name=status.upper(),
                marker=dict(
                    size=sizes, color=color,
                    line=dict(width=2, color="rgba(255,255,255,0.25)"),
                    symbol="circle",
                ),
                text=texts, textfont=dict(size=10),
                hovertext=hovers, hoverinfo="text",
            ))

    fig_topo = go.Figure(
        data=[edge_trace] + node_traces,
        layout=go.Layout(
            showlegend=True,
            hovermode="closest",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            height=560,
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(
                x=1, y=1,
                bgcolor="rgba(10,16,32,0.85)",
                bordercolor="rgba(255,255,255,0.08)",
                font=dict(color="#f0f6ff", size=12),
            ),
            font=dict(color="#f0f6ff"),
        ),
    )
    st.plotly_chart(fig_topo, use_container_width=True, key="topology_chart")

    st.markdown("### Device Inventory")
    device_rows = []
    for dev_id, meta in sorted(devices.items()):
        risk = meta.get("risk_score", 0)
        emoji = {"healthy": "🟢", "degraded": "🔵", "warning": "🟡", "critical": "🔴"}
        device_rows.append({
            "Status":     emoji.get(meta["status"], "⚪"),
            "Device ID":  dev_id,
            "Type":       meta["type"].title(),
            "Vendor":     meta["vendor"],
            "IP":         meta["ip"],
            "Location":   meta["location"],
            "Risk Score": f"{risk:.1%}",
        })
    st.dataframe(pd.DataFrame(device_rows), use_container_width=True, hide_index=True, height=300)


# ════════════════════════════════════════
# TAB 2 — Predictive Alerts
# ════════════════════════════════════════

with tab_alerts:
    st.markdown("### 🚨 Predictive Failure Alerts")
    st.markdown(
        '<p style="color:#8fa0c0;font-size:13px;">'
        'Proactive alerts generated by the predictive analytics engine. '
        'Each alert includes recommended runbook actions.</p>',
        unsafe_allow_html=True,
    )

    if not alerts:
        st.success("✅ No active predictive alerts. All devices within normal parameters.")
    else:
        for alert in alerts:
            risk_class = alert["risk_level"].lower()
            fp = alert["failure_probability"]
            prob_class = "critical" if fp >= 0.8 else ("high" if fp >= 0.6 else "medium")

            contributing = alert.get("contributing_metrics", [])
            metrics_str = ", ".join(contributing) if isinstance(contributing, list) and contributing else str(contributing) or "Multiple signals"
            runbooks    = ", ".join(alert.get("recommended_runbooks", []))

            st.markdown(f"""
            <div class="alert-card alert-{risk_class}">
              <div class="alert-hdr">
                <span class="alert-dev">⚠️ {alert['device_id']}</span>
                <span class="alert-prob prob-{prob_class}">{fp:.0%} failure risk</span>
              </div>
              <div class="alert-body">
                <strong>Risk Level:</strong> {alert['risk_level']} &nbsp;|&nbsp;
                <strong>Contributing:</strong> {metrics_str}<br>
                <strong>Recommended Runbooks:</strong> {runbooks}<br>
                <strong>Generated:</strong> {alert['timestamp'][:19]}
              </div>
            </div>
            """, unsafe_allow_html=True)

            with st.expander(f"📋 Co-Pilot Analysis — {alert['device_id']}", expanded=False):
                st.markdown(alert.get("explanation", "No explanation available."))

    st.markdown("### Risk Summary — All Devices")
    risk_rows = []
    for r in risk_summary:
        emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}
        risk_rows.append({
            "Risk":            emoji.get(r["risk_level"], "⚪"),
            "Device":          r["device_id"],
            "Level":           r["risk_level"],
            "Max Prob":        f"{r['max_failure_prob']:.1%}",
            "Avg Prob":        f"{r['avg_failure_prob']:.1%}",
            "Latest Prob":     f"{r['latest_failure_prob']:.1%}",
            "Predicted Failure": "⚠️ YES" if r["predicted_failure"] else "✅ No",
        })
    st.dataframe(pd.DataFrame(risk_rows), use_container_width=True, hide_index=True, height=420)


# ════════════════════════════════════════
# TAB 3 — System Logs (NEW)
# ════════════════════════════════════════

with tab_logs:
    st.markdown("### 📋 System Logs — Live Stream")
    st.markdown(
        '<p style="color:#8fa0c0;font-size:13px;">'
        'Real-time syslog feed from all monitored network devices. '
        'Filter by severity to focus on critical events.</p>',
        unsafe_allow_html=True,
    )

    # Controls
    log_col1, log_col2, log_col3 = st.columns([2, 2, 2])
    with log_col1:
        log_level_filter = st.selectbox(
            "Min Severity",
            ["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            index=0,
            key="log_level_filter",
        )
    with log_col2:
        device_ids = ["ALL"] + sorted(list(devices.keys()))
        log_device_filter = st.selectbox(
            "Device Filter",
            device_ids,
            index=0,
            key="log_device_filter",
        )
    with log_col3:
        log_limit = st.selectbox("Show Last", [50, 100, 200, 500], index=0, key="log_limit")

    st.markdown("<br>", unsafe_allow_html=True)

    # Fetch logs from SQLite
    def fetch_logs(limit: int = 100, min_level: str = "ALL", device_id: str = "ALL") -> list[dict]:
        from src.utils.config import analytics_cfg as _cfg
        cfg = _cfg()
        db_path = cfg.get("syslog_db", "copilot/data/syslogs.db")
        if not Path(db_path).exists():
            return []
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            query = "SELECT * FROM syslogs"
            conditions = []
            params = []
            level_order = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            if min_level != "ALL" and min_level in level_order:
                idx = level_order.index(min_level)
                allowed = level_order[idx:]
                placeholders = ",".join(["?" for _ in allowed])
                conditions.append(f"severity IN ({placeholders})")
                params.extend(allowed)
            if device_id != "ALL":
                conditions.append("device_id = ?")
                params.append(device_id)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += f" ORDER BY timestamp DESC LIMIT {int(limit)}"
            rows = conn.execute(query, params).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            return []

    log_entries = fetch_logs(
        limit=log_limit,
        min_level=log_level_filter,
        device_id=log_device_filter,
    )

    # Summary stats row
    if log_entries:
        total_shown = len(log_entries)
        crit_count  = sum(1 for l in log_entries if l.get("severity", "").upper() == "CRITICAL")
        err_count   = sum(1 for l in log_entries if l.get("severity", "").upper() == "ERROR")
        warn_count  = sum(1 for l in log_entries if l.get("severity", "").upper() == "WARNING")

        stat_c1, stat_c2, stat_c3, stat_c4 = st.columns(4)
        stat_c1.metric("Log Entries", total_shown)
        stat_c2.metric("🔴 Critical", crit_count)
        stat_c3.metric("🟠 Errors", err_count)
        stat_c4.metric("🟡 Warnings", warn_count)

        st.markdown("<br>", unsafe_allow_html=True)

        # Render log stream
        level_css = {
            "CRITICAL": "log-critical",
            "ERROR":    "log-error",
            "WARNING":  "log-warning",
            "INFO":     "log-info",
            "DEBUG":    "log-debug",
        }

        lines_html = ""
        for entry in log_entries:
            sev  = str(entry.get("severity", "INFO")).upper()
            ts   = str(entry.get("timestamp", ""))[:19]
            dev  = str(entry.get("device_id", "UNK"))
            msg  = str(entry.get("message", ""))
            css  = level_css.get(sev, "log-info")
            lines_html += (
                f'<div class="{css}">'
                f'<span class="log-ts">{ts}</span>'
                f'<span class="log-dev">[{dev}]</span>'
                f'<span>[{sev}]</span>&nbsp;{msg}'
                f'</div>'
            )

        st.markdown(f'<div class="log-stream">{lines_html}</div>', unsafe_allow_html=True)

        # Log severity distribution
        st.markdown("#### Log Severity Distribution")
        all_logs_df = pd.DataFrame(log_entries)
        if not all_logs_df.empty and "severity" in all_logs_df.columns:
            sev_counts = all_logs_df["severity"].str.upper().value_counts().reset_index()
            sev_counts.columns = ["Severity", "Count"]
            color_map = {
                "CRITICAL": "#ef4444", "ERROR": "#fb923c",
                "WARNING": "#f59e0b", "INFO": "#64748b", "DEBUG": "#334155",
            }
            fig_sev = go.Figure(go.Bar(
                x=sev_counts["Severity"],
                y=sev_counts["Count"],
                marker_color=[color_map.get(s, "#64748b") for s in sev_counts["Severity"]],
                marker_line=dict(color="rgba(255,255,255,0.1)", width=1),
            ))
            fig_sev.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#f0f6ff", size=12),
                height=280,
                margin=dict(l=40, r=20, t=20, b=40),
                xaxis=dict(title="Severity Level", gridcolor="rgba(100,116,139,0.15)"),
                yaxis=dict(title="Count", gridcolor="rgba(100,116,139,0.15)"),
            )
            st.plotly_chart(fig_sev, use_container_width=True, key="log_sev_chart")

        # Log events over time
        st.markdown("#### Log Events Over Time")
        if "timestamp" in all_logs_df.columns:
            try:
                ts_df = all_logs_df.copy()
                ts_df["timestamp"] = pd.to_datetime(ts_df["timestamp"], errors="coerce")
                ts_df = ts_df.dropna(subset=["timestamp"])
                ts_df["minute"] = ts_df["timestamp"].dt.floor("5min")
                time_counts = (
                    ts_df.groupby(["minute", "severity"])
                    .size().reset_index(name="count")
                )
                fig_ts = px.line(
                    time_counts, x="minute", y="count",
                    color="severity",
                    color_discrete_map={
                        "CRITICAL": "#ef4444", "ERROR": "#fb923c",
                        "WARNING":  "#f59e0b", "INFO":  "#64748b",
                    },
                )
                fig_ts.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#f0f6ff", size=11),
                    height=280,
                    margin=dict(l=40, r=20, t=20, b=50),
                    xaxis=dict(title="Time", gridcolor="rgba(100,116,139,0.15)"),
                    yaxis=dict(title="Events/5min", gridcolor="rgba(100,116,139,0.15)"),
                    legend=dict(
                        bgcolor="rgba(10,16,32,0.85)",
                        bordercolor="rgba(255,255,255,0.08)",
                        font=dict(color="#f0f6ff"),
                    ),
                )
                st.plotly_chart(fig_ts, use_container_width=True, key="log_ts_chart")
            except Exception:
                pass

    else:
        st.info("⏳ No log entries available. Run the orchestrator pipeline to generate logs.")

    # Auto-refresh
    if st.button("🔄 Refresh Logs", key="refresh_logs"):
        st.rerun()


# ════════════════════════════════════════
# TAB 4 — Co-Pilot Chat
# ════════════════════════════════════════

with tab_chat:
    st.markdown("### 💬 NetOps Co-Pilot Chat")
    st.markdown(
        f'<p style="color:#8fa0c0;font-size:13px;">'
        f'Ask questions about network issues and get runbook-grounded answers with citations. '
        f'Current clearance: <strong style="color:#a78bfa;">{clearance}</strong></p>',
        unsafe_allow_html=True,
    )

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # Chat history rendering
    if st.session_state.chat_messages:
        chat_html = '<div class="chat-wrap">'
        for msg in st.session_state.chat_messages:
            if msg["role"] == "user":
                chat_html += f"""
                <div class="chat-user">
                  <div class="chat-role">🧑‍💻 Operator</div>
                  {msg['content']}
                </div>"""
            else:
                src_html = ""
                if msg.get("sources"):
                    srcs = " &nbsp;•&nbsp; ".join(
                        f"{s['runbook_id']} <span style='opacity:.6'>({s['score']:.2f})</span>"
                        for s in msg["sources"]
                    )
                    src_html = f'<div class="chat-src">📖 Sources: {srcs}</div>'
                chat_html += f"""
                <div class="chat-bot">
                  <div class="chat-role">🛰️ Co-Pilot</div>
                  {msg['content']}
                  {src_html}
                </div>"""
        chat_html += "</div>"
        st.markdown(chat_html, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

    # Quick queries
    st.markdown("**Quick queries:**")
    qcols = st.columns(3)
    examples = [
        "How do I fix high CPU on a router?",
        "What to do about CRC errors on an interface?",
        "Temperature alarm — server overheating",
    ]
    for col, ex in zip(qcols, examples):
        if col.button(ex, key=f"ex_{ex[:20]}", use_container_width=True):
            st.session_state.pending_query = ex

    user_input = st.chat_input("Ask the Co-Pilot about network issues…")
    query = user_input or st.session_state.get("pending_query")

    if query:
        st.session_state.pop("pending_query", None)
        st.session_state.chat_messages.append({"role": "user", "content": query})

        with st.spinner("🔍 Searching runbooks and generating response…"):
            result = orch.handle_chat(query, operator_clearance=clearance)

        st.session_state.chat_messages.append({
            "role":       "assistant",
            "content":    result["answer"],
            "sources":    result.get("sources", []),
            "latency_ms": result.get("latency_ms", 0),
            "model_type": result.get("model_type", ""),
        })
        st.rerun()

    if st.session_state.chat_messages:
        if st.button("🗑️ Clear Chat History", key="clear_chat"):
            st.session_state.chat_messages = []
            st.rerun()


# ════════════════════════════════════════
# TAB 5 — Forecast Accuracy
# ════════════════════════════════════════

with tab_forecast:
    st.markdown("### 📈 Forecast Accuracy & Backtest Results")
    st.markdown(
        '<p style="color:#8fa0c0;font-size:13px;">'
        'How well does our model predict failures? Showing predicted vs actual failure events '
        'with lead-time metrics.</p>',
        unsafe_allow_html=True,
    )

    metrics     = orch.get_model_metrics()
    importances = orch.get_feature_importances()

    # Large metric display
    m1, m2, m3, m4 = st.columns(4)
    def big_metric(col, label, value, color):
        col.markdown(f"""
        <div style="background:var(--bg-card);border-radius:14px;padding:22px;border:1px solid var(--border);text-align:center;">
          <div style="color:#4e6080;font-size:11px;text-transform:uppercase;letter-spacing:1px;">{label}</div>
          <div style="color:{color};font-size:36px;font-weight:900;margin:8px 0;">{value}</div>
        </div>
        """, unsafe_allow_html=True)

    big_metric(m1, "Precision", f"{metrics.get('precision',0):.2%}", "#22d3ee")
    big_metric(m2, "Recall",    f"{metrics.get('recall',0):.2%}",    "#10b981")
    big_metric(m3, "F1 Score",  f"{metrics.get('f1_score',0):.2%}", "#a855f7")
    big_metric(m4, "AUC-ROC",   f"{metrics.get('auc_roc',0):.2%}",  "#3b82f6")

    st.markdown("<br>", unsafe_allow_html=True)
    st.divider()

    # Feature importance
    if importances:
        st.markdown("#### Top Predictive Features")
        top_feats = list(importances.items())[:15]
        feat_names = [f[0] for f in top_feats]
        feat_vals  = [f[1] for f in top_feats]

        fig_feat = go.Figure(go.Bar(
            x=feat_vals[::-1],
            y=feat_names[::-1],
            orientation="h",
            marker=dict(
                color=feat_vals[::-1],
                colorscale=[[0, "#3b82f6"], [0.5, "#8b5cf6"], [1, "#ef4444"]],
                line=dict(color="rgba(255,255,255,0.05)", width=1),
            ),
        ))
        fig_feat.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#f0f6ff", size=11),
            height=450,
            margin=dict(l=200, r=20, t=20, b=40),
            xaxis=dict(title="Importance", gridcolor="rgba(100,116,139,0.15)"),
            yaxis=dict(gridcolor="rgba(100,116,139,0.15)"),
        )
        st.plotly_chart(fig_feat, use_container_width=True, key="feature_importance")

    # Ground truth events
    st.markdown("#### Ground Truth — Injected Failure Events")
    failure_events = orch.get_failure_events()
    if failure_events:
        fe_rows = [{
            "Device":             e["device_id"],
            "Failure Time":       e["failure_time"],
            "Severity":           e["severity"].upper(),
            "Fault Type":         e["fault_type"].replace("_", " ").title(),
            "Affected Metrics":   ", ".join(e["affected_metrics"]),
            "Pre-Warning Window": f"{e['pre_failure_window_min']} min",
        } for e in failure_events]
        st.dataframe(pd.DataFrame(fe_rows), use_container_width=True, hide_index=True)

    # Probability distribution
    st.markdown("#### Failure Probability Distribution")
    predictions_df = orch.get_predictions_df()
    if not predictions_df.empty and "failure_prob" in predictions_df.columns:
        fig_dist = go.Figure()
        fig_dist.add_trace(go.Histogram(
            x=predictions_df["failure_prob"],
            nbinsx=50,
            marker=dict(
                color="rgba(59,130,246,0.65)",
                line=dict(color="rgba(59,130,246,0.9)", width=1),
            ),
            name="All Predictions",
        ))
        threshold = analytics_cfg().get("failure_probability_threshold", 0.65)
        fig_dist.add_vline(
            x=threshold, line_dash="dash", line_color="#ef4444",
            annotation_text=f"Alert Threshold ({threshold:.0%})",
            annotation_font_color="#ef4444",
        )
        fig_dist.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#f0f6ff"),
            xaxis=dict(title="Failure Probability", gridcolor="rgba(100,116,139,0.15)"),
            yaxis=dict(title="Count", gridcolor="rgba(100,116,139,0.15)"),
            height=340,
            margin=dict(l=60, r=20, t=20, b=60),
        )
        st.plotly_chart(fig_dist, use_container_width=True, key="prob_distribution")


# ══════════════════════════════════════════════════════════════════════════════
# Footer
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<div style="text-align:center;padding:32px 0 10px;color:#2d3f5a;font-size:11px;
            border-top:1px solid rgba(255,255,255,0.04);margin-top:48px;">
  🛰️ ISRO NetOps Predictive Co-Pilot v2.0.0 &nbsp;|&nbsp;
  🔒 Air-Gapped Operation &nbsp;|&nbsp;
  🤖 All inference runs locally &nbsp;|&nbsp;
  📚 Answers grounded in verified SOPs
</div>
""", unsafe_allow_html=True)
