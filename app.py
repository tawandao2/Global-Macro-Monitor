import json, pathlib
import pandas as pd
import streamlit as st
from src import pbi_view

st.set_page_config(page_title="Global Macro Monitor", page_icon="🌍", layout="wide")
ROOT = pathlib.Path(__file__).parent


@st.cache_data
def load():
    snap = pd.read_csv(ROOT / "data" / "country_snapshot.csv")
    series = pd.read_csv(ROOT / "data" / "country_series.csv")
    world = json.load(open(ROOT / "data" / "world-110m.json"))
    ev = {k: json.load(open(ROOT / "eval" / f"results_{k}.json")) for k in ("regressions", "forecast", "score", "quality")}
    return snap, series, world, ev


snap, series, world, ev = load()
t0, t1, t2, t3, t4 = st.tabs(["Report", "Country view", "Statistics", "Data quality", "Limits"])
with t0:
    pbi_view.render_report(snap, world)
with t1:
    pbi_view.render_country(snap, series, ev["score"]["rules"], ev["score"])
with t2:
    pbi_view.render_stats(ev["regressions"], ev["forecast"], ev["score"])
with t3:
    pbi_view.render_quality(ev["quality"])
with t4:
    pbi_view.render_limits(ev["regressions"], ev["forecast"], ev["score"], ev["quality"])
