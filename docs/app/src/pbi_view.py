"""Power BI style report for the macro monitor: slicers, KPI cards and linked visuals."""
import json
import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

BLUE, NAVY, ORANGE, YELLOW, RED, GREY = "#118DFF", "#12239E", "#E66C37", "#D9B300", "#D64550", "#C8C6C4"
TIER_COLORS = {"Low": BLUE, "Elevated": YELLOW, "High": RED, "Not rated": GREY}
TIERS = ["High", "Elevated", "Low", "Not rated"]
RULE_LABELS = {"inflation": "High inflation (over 10%)", "gdp_growth": "Weak growth (under 1%)", "unemployment": "High unemployment (over 12%)",
               "gov_debt": "High government debt (over 90% of GDP)", "current_account": "Large external deficit (worse than -5% of GDP)",
               "fiscal_balance": "Large budget deficit (worse than -5% of GDP)"}

CSS = """
<style>
.stApp {background:#F3F2F1;}
.block-container {padding-top:3.5rem; max-width:1400px;}
.pbi-title {background:#12239E; color:white; padding:14px 22px; border-radius:4px; display:flex; justify-content:space-between; align-items:center;}
.pbi-title h2 {margin:0; padding:0; font-size:1.35rem !important; color:white !important; font-weight:600;}
.pbi-title span {font-size:.8rem; opacity:.85;}
.card {min-height:112px; background:white; border:1px solid #E1DFDD; border-radius:4px; padding:12px 16px; box-shadow:0 1px 2px rgba(0,0,0,.06);}
.card .lab {font-size:.78rem; color:#605E5C; margin-bottom:2px;}
.card .val {font-size:2rem; font-weight:600; color:#252423; line-height:1.15;}
.card .sub {font-size:.75rem; color:#605E5C;}
[class*="st-key-vis_"] {background:#FFFFFF !important; border:1px solid #E1DFDD !important; border-radius:4px !important; box-shadow:0 1px 2px rgba(0,0,0,.06);}
.vt {font-size:.92rem; font-weight:600; color:#252423; margin-bottom:2px;}
.note {font-size:.78rem; color:#605E5C;}
</style>
"""
_n = [0]


def card(col, label, value, sub=""):
    col.markdown(f'<div class="card"><div class="lab">{label}</div><div class="val">{value}</div><div class="sub">{sub}</div></div>', unsafe_allow_html=True)


def vis(title, key=None):
    _n[0] += 1
    box = st.container(border=True, key=f"vis_{key or _n[0]}")
    box.markdown(f'<div class="vt">{title}</div>', unsafe_allow_html=True)
    return box


def style(ch, h=240):
    return ch.properties(height=h, background="#FFFFFF").configure_view(strokeWidth=0).configure_axis(
        labelColor="#605E5C", titleColor="#605E5C", gridColor="#EDEBE9", domainColor="#C8C6C4").configure_legend(orient="top", title=None, labelLimit=300)


def title_bar(text, right):
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(f'<div class="pbi-title"><h2>{text}</h2><span>{right}</span></div>', unsafe_allow_html=True)
    st.write("")


def tier_scale():
    return alt.Scale(domain=TIERS, range=[TIER_COLORS[t] for t in TIERS])


def render_report(snap, world):
    title_bar("Global Macro Monitor", "IMF World Economic Outlook, October 2026 &nbsp;|&nbsp; snapshot year 2025")
    s1, s2, s3 = st.columns(3)
    region = s1.multiselect("Region", sorted(snap.region.unique()), placeholder="All")
    income = s2.multiselect("Income group", ["Lowest income quarter", "Lower middle", "Upper middle", "Highest income quarter"], placeholder="All")
    tiers = s3.multiselect("Risk tier", TIERS, placeholder="All")
    f = snap
    for col, sel in (("region", region), ("income_group", income), ("tier", tiers)):
        if sel:
            f = f[f[col].isin(sel)]
    if len(f) < 3:
        st.warning("Too few countries in this selection. Clear a slicer.")
        return
    rated = f[f.tier != "Not rated"]
    k = st.columns(5)
    card(k[0], "Countries in selection", f"{len(f)}", f"of {len(snap)}")
    card(k[1], "High risk tier", f"{(f.tier == 'High').sum()}", f"{(f.tier == 'Elevated').sum()} more elevated")
    card(k[2], "Median GDP growth, 2025", f"{f.gdp_growth.median():.1f}%", f"all countries {snap.gdp_growth.median():.1f}%")
    card(k[3], "Median inflation, 2025", f"{f.inflation.median():.1f}%", f"all countries {snap.inflation.median():.1f}%")
    card(k[4], "Inflation above 10%", f"{(f.inflation > 10).mean() * 100:.0f}%", "of countries in selection")
    st.write("")

    r1a, r1b = st.columns([7, 4])
    with r1a:
        box = vis("Risk tier by country")
        geo = alt.Data(values=world, format=alt.DataFormat(type="topojson", feature="countries"))
        data = f[["iso_numeric", "name", "tier", "inflation", "gdp_growth", "gov_debt", "n_flags"]].copy()
        ch = alt.Chart(geo).mark_geoshape(stroke="white", strokeWidth=0.3).transform_lookup(
            lookup="id", from_=alt.LookupData(data, "iso_numeric", ["name", "tier", "inflation", "gdp_growth", "gov_debt", "n_flags"])).encode(
            color=alt.condition("isValid(datum.tier)", alt.Color("tier:N", scale=tier_scale(), legend=alt.Legend(orient="bottom", title=None)), alt.value("#EDEBE9")),
            tooltip=[alt.Tooltip("name:N", title="Country"), alt.Tooltip("tier:N", title="Tier"), alt.Tooltip("n_flags:Q", title="Warning flags"),
                     alt.Tooltip("inflation:Q", format=".1f", title="Inflation %"), alt.Tooltip("gdp_growth:Q", format=".1f", title="Growth %"),
                     alt.Tooltip("gov_debt:Q", format=".0f", title="Debt % of GDP")]).project("equalEarth").properties(height=300, width="container", background="#FFFFFF")
        box.altair_chart(ch.configure_view(strokeWidth=0), width="stretch")
    with r1b:
        box = vis("Countries by region and tier")
        c = rated.groupby(["region", "tier"]).size().reset_index(name="n")
        ch = alt.Chart(c).mark_bar().encode(y=alt.Y("region:N", title=None, sort="-x"), x=alt.X("n:Q", title=None),
                                          color=alt.Color("tier:N", scale=tier_scale(), legend=alt.Legend(orient="top", title=None)),
                                          order=alt.Order("tier:N", sort="descending"), tooltip=["region", "tier", "n"])
        box.altair_chart(style(ch, 300), width="stretch")
    st.write("")

    r2a, r2b, r2c = st.columns([5, 4, 4])
    with r2a:
        box = vis("Inflation against growth, 2025 (each dot is a country)")
        p = f.dropna(subset=["inflation", "gdp_growth"]).copy()
        p["infl_plot"] = p.inflation.clip(-2, 60)
        ch = alt.Chart(p).mark_circle(size=70, opacity=0.8).encode(
            x=alt.X("gdp_growth:Q", title="GDP growth, %"), y=alt.Y("infl_plot:Q", title="Inflation, % (capped at 60)"),
            color=alt.Color("tier:N", scale=tier_scale(), legend=None),
            tooltip=[alt.Tooltip("name:N", title="Country"), alt.Tooltip("gdp_growth:Q", format=".1f"), alt.Tooltip("inflation:Q", format=".1f"), "tier"])
        box.altair_chart(style(ch, 270), width="stretch")
    with r2b:
        box = vis("Highest warning counts")
        t = rated.sort_values(["n_flags", "inflation"], ascending=False).head(10)
        ch = alt.Chart(t).mark_bar().encode(y=alt.Y("name:N", sort=None, title=None, axis=alt.Axis(labelLimit=200, labelOverlap=False)), x=alt.X("n_flags:Q", title="Flags out of the rules with data", axis=alt.Axis(tickMinStep=1)),
                                           color=alt.Color("tier:N", scale=tier_scale(), legend=None), tooltip=["name", "n_flags", "tier"])
        box.altair_chart(style(ch, 270), width="stretch")
    with r2c:
        box = vis("Which warnings fire most often")
        cnt = pd.DataFrame([{"rule": RULE_LABELS[i], "share": f["flag_" + i].dropna().mean(), "n": int(f["flag_" + i].notna().sum())} for i in RULE_LABELS])
        ch = alt.Chart(cnt).mark_bar(color=NAVY).encode(y=alt.Y("rule:N", sort="-x", title=None, axis=alt.Axis(labelLimit=240)),
                                                       x=alt.X("share:Q", title=None, axis=alt.Axis(format="%")), tooltip=["rule", alt.Tooltip("share:Q", format=".0%"), "n"])
        box.altair_chart(style(ch, 270), width="stretch")
    st.caption("Slicers filter every card and chart. Grey countries on the map are outside the selection or are small states not drawn at this map scale.")
    st.caption("Source: International Monetary Fund, World Economic Outlook Database, October 2026. Data have been transformed (reshaped, flagged and scored) by this project. "
               "World Bank data: World Development Indicators, updated 8 October 2026.")


def render_country(snap, series, rules, score=None):
    title_bar("Country view", "Dashed lines are IMF projections, solid lines are actual or estimated values")
    names = dict(zip(snap.code, snap.name))
    default = list(snap.name).index("Brazil") if "Brazil" in set(snap.name) else 0
    pick = st.selectbox("Country", list(snap.name.sort_values()), index=list(snap.name.sort_values()).index(snap.name.iloc[default]))
    row = snap[snap.name == pick].iloc[0]
    s = series[series.code == row.code]
    k = st.columns(5)
    card(k[0], "Risk tier", row.tier, f"{int(row.n_flags)} of {int(row.n_available)} rules fire")
    card(k[1], "GDP growth, 2025", "n/a" if pd.isna(row.gdp_growth) else f"{row.gdp_growth:.1f}%", f"all countries median {snap.gdp_growth.median():.1f}%")
    card(k[2], "Inflation, 2025", "n/a" if pd.isna(row.inflation) else f"{row.inflation:.1f}%", f"all countries median {snap.inflation.median():.1f}%")
    card(k[3], "Government debt", "n/a" if pd.isna(row.gov_debt) else f"{row.gov_debt:.0f}% of GDP", "2025")
    card(k[4], "Latest actual year", "unknown" if pd.isna(row.latest_actual) else f"{int(row.latest_actual)}", "later years are IMF staff estimates" if row.estimated else "2025 is reported")
    st.write("")
    names_i = {"gdp_growth": "GDP growth, %", "inflation": "Inflation, % (axis capped at 60)", "unemployment": "Unemployment, %", "gov_debt": "Government debt, % of GDP",
               "current_account": "Current account, % of GDP", "fiscal_balance": "Budget balance, % of GDP"}
    cols = st.columns(3)
    for i, (ind, label) in enumerate(names_i.items()):
        box = cols[i % 3].container(border=True, key=f"vis_c{i}")
        box.markdown(f'<div class="vt">{label}</div>', unsafe_allow_html=True)
        d = s[s.indicator == ind]
        if d.empty:
            box.caption("No data for this country."); continue
        ch = alt.Chart(d).mark_line(point=True, color=BLUE, strokeWidth=2).encode(
            x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0, values=list(range(1990, 2032, 5)))), y=alt.Y("value:Q", title=None, scale=alt.Scale(domain=[-10, 60], clamp=True) if ind == "inflation" else alt.Undefined),
            strokeDash=alt.StrokeDash("is_projection:N", legend=None, scale=alt.Scale(domain=[False, True], range=[[1, 0], [4, 3]])),
            tooltip=["year", alt.Tooltip("value:Q", format=".1f"), "is_projection"])
        box.altair_chart(style(ch, 190), width="stretch")
    st.write("")
    t = pd.DataFrame([{"Rule": RULE_LABELS[r["indicator"]], "Value, 2025": row[r["indicator"]], "Fires": ("yes" if row["flag_" + r["indicator"]] == 1 else "no" if row["flag_" + r["indicator"]] == 0 else "no data")} for r in rules])
    t["Value, 2025"] = t["Value, 2025"].map(lambda v: "n/a" if pd.isna(v) else f"{v:.1f}")
    st.markdown("**Warning rules for this country**")
    st.dataframe(t, hide_index=True, width="stretch")
    if score is not None:
        from src.briefing import build_findings, RulesOnlyWriter, run_briefing
        bundle = build_findings(row.to_dict(), series, snap, score)
        res = run_briefing(bundle, RulesOnlyWriter())
        st.markdown("**Checked briefing**")
        if res["status"] == "ready":
            for stmt in res["statements"]:
                st.write(stmt["text"])
        else:
            st.error("The checker rejected this briefing: " + "; ".join(res["problems"]))
        st.caption("Built by rules from the facts below. With an AI writer, the same checker validates every sentence before anyone sees it.")
        with st.expander("Facts the briefing may use"):
            for f in bundle["findings"]:
                st.markdown(f"**{f['id']}**")
                for fact in f["facts"]:
                    st.write("• " + fact)
    return row


def render_quality(checks):
    title_bar("Data quality", "Every check runs on each data load. Flagged means worth a look, not deleted")
    t = pd.DataFrame([dict(Check=c["name"], Tested=f"{c['tested']:,}", Flagged=f"{c['failed']:,}", Rate=f"{c['failure_rate'] * 100:.1f}%") for c in checks])
    st.dataframe(t, hide_index=True, width="stretch")
    for c in checks:
        if c["examples"] or c["note"]:
            with st.expander(f"{c['name']}: {c['failed']:,} of {c['tested']:,} flagged"):
                if c["note"]:
                    st.write(c["note"])
                if c["examples"]:
                    st.dataframe(pd.DataFrame(c["examples"]), hide_index=True, width="stretch")


def render_stats(reg, fc, score):
    title_bar("Statistics", "Associations and forecast tests. Nothing here shows a cause")
    c1, c2 = st.columns(2)
    with c1:
        box = vis("What moves with GDP growth (preferred model, with 95% intervals)")
        m = reg["models"]["country_and_year_effects"]["coefs"]
        d = pd.DataFrame([dict(label=v["label"], coef=v["coef"], lo=v["lo"], hi=v["hi"]) for v in m.values()])
        base = alt.Chart(d).encode(y=alt.Y("label:N", sort=None, title=None, axis=alt.Axis(labelLimit=330)))
        err = base.mark_rule(strokeWidth=3, color=NAVY).encode(x=alt.X("lo:Q", title="Change in growth, percentage points"), x2="hi:Q")
        pts = base.mark_point(filled=True, size=110, color=ORANGE).encode(x="coef:Q", tooltip=["label", alt.Tooltip("coef:Q", format=".3f")])
        zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=RED, strokeDash=[4, 3]).encode(x="x:Q")
        box.altair_chart(style(err + pts + zero, 260), width="stretch")
        box.markdown('<div class="note">Every coefficient keeps its sign across six versions of the model, but only income is statistically clear in all six (inflation in five, budget balance four, debt three, current account one). Income effect is probably overstated by a known bias.</div>', unsafe_allow_html=True)
    with c2:
        box = vis("Forecast error, one year ahead (lower is better)")
        rows = []
        for target, lab in (("gdp_growth", "GDP growth"), ("inflation", "Inflation")):
            for k, name in (("naive", "Same as last year"), ("mean5_fc", "5 year average"), ("blend", "Simple blend"), ("boosting", "Boosting model")):
                rows.append(dict(target=lab, model=name, mae=fc[target]["models"][k]["mae"]))
        d = pd.DataFrame(rows)
        ch = alt.Chart(d).mark_bar().encode(x=alt.X("model:N", sort=None, title=None, axis=alt.Axis(labelAngle=-20)), xOffset="target:N", y=alt.Y("mae:Q", title="Mean absolute error, percentage points"),
                                          color=alt.Color("target:N", scale=alt.Scale(range=[BLUE, ORANGE]), legend=alt.Legend(orient="top", title=None)), tooltip=["target", "model", alt.Tooltip("mae:Q", format=".2f")])
        box.altair_chart(style(ch, 260), width="stretch")
        g = fc["gdp_growth"]["boosting_minus_blend"]; i = fc["inflation"]["boosting_minus_blend"]
        box.markdown(f'<div class="note">Boosting against the simple blend: growth {g["mean"]:+.2f} points, inflation {i["mean"]:+.2f} points. In the shock years 2020 (growth) and 2022 (inflation) no model did well.</div>', unsafe_allow_html=True)
    st.write("")
    box = vis("Does the early warning tier mean anything? Outcomes one year later, 2000 to 2024")
    v = pd.DataFrame(score["validation"]).set_index("tier").loc[["Low", "Elevated", "High"]].reset_index()
    cc = st.columns(3)
    long = v.melt("tier", ["share_negative_growth", "share_next_inflation_over_10"], var_name="outcome", value_name="share")
    long["outcome"] = long.outcome.map({"share_negative_growth": "Economy shrinks next year", "share_next_inflation_over_10": "Inflation over 10% next year"})
    ch = alt.Chart(long).mark_bar().encode(x=alt.X("tier:N", sort=["Low", "Elevated", "High"], title=None, axis=alt.Axis(labelAngle=0)), xOffset="outcome:N",
                                         y=alt.Y("share:Q", title=None, axis=alt.Axis(format="%")), color=alt.Color("outcome:N", scale=alt.Scale(range=[BLUE, ORANGE]), legend=alt.Legend(orient="top", title=None)),
                                         tooltip=["tier", "outcome", alt.Tooltip("share:Q", format=".1%")])
    box.altair_chart(style(ch, 230), width="stretch")
    box.markdown('<div class="note">Countries in the High tier shrank the next year about 20% of the time against about 12% for Low. The inflation result is partly persistence, since high inflation tends to stay high. Rules were fixed before this check.</div>', unsafe_allow_html=True)


def render_limits(reg, fc, score, checks):
    title_bar("Limits", "What this project does not show")
    sens = score["sensitivity"]
    st.markdown(f"""
- **Associations, not causes.** The regressions describe how things move together across countries. They do not show that changing one thing changes another.
- **The size of the income effect is probably too large.** Country effects with a lagged level are known to overstate convergence speed. The direction is reliable.
- **Debt and budget balance results are fragile.** They lose statistical significance in some versions of the model.
- **Forecasts do not predict shocks.** Every model missed 2020 growth by about 8 points and 2022 inflation by about 6 points.
- **Real time data is not used.** Scoring uses today's revised data, not the numbers that were available at the time, and extreme values are left out of the forecast scoring.
- **Cannot compare with IMF forecasts.** The file holds only the current edition, so past IMF forecasts are not available to score.
- **The warning tiers depend on thresholds.** The six thresholds come from common rules of thumb. Making them 20% stricter moves the High tier from 15 countries to {sens['thresholds 20 percent stricter']['high_count']}, and 25% looser moves it to {sens['thresholds 25 percent looser']['high_count']}. The country ranking is stable (rank correlation {sens['thresholds 20 percent stricter']['rank_corr']:.2f} and {sens['thresholds 25 percent looser']['rank_corr']:.2f}), so use the ranking more than the tier labels.
- **Recent values are estimates.** For many countries the latest years are IMF staff estimates, marked in the country view.
- **Sources differ.** IMF and World Bank values match for most countries but not all, and unemployment is measured on different definitions.
- **The briefing checker is strong but not perfect.** It confirms every number and sign appears in the cited facts, that projections are labelled, and that no cause is claimed. It cannot tell whether a true number sits in the right sentence.
- **Small states are missing from the map** because the map file leaves out many islands. They remain in every table and chart.
""")
