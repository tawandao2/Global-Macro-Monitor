"""Data quality checks. Each check returns how many things it tested, how many failed, and examples."""
import numpy as np
import pandas as pd

BOUNDS = {"gdp_growth": (-60, 60), "inflation": (-30, 200), "unemployment": (0, 60), "gov_debt": (0, 400),
          "fiscal_balance": (-60, 60), "current_account": (-80, 80)}
TOL_INTERNAL = 0.15     # percentage points, allows for rounding in published levels
TOL_CROSS = 0.5         # percentage points between IMF and World Bank


def _res(cid, name, tested, failed, examples, note=""):
    return dict(id=cid, name=name, tested=int(tested), failed=int(failed), failure_rate=float(failed / tested) if tested else 0.0,
                examples=examples, note=note)


def check_unique(obs):
    d = obs.duplicated(["source", "code", "indicator", "year"], keep=False)
    return _res("unique", "One value per source, country, indicator and year", len(obs), d.sum(), obs[d].head(5).to_dict("records"))


def check_bounds(obs):
    tested = failed = 0; ex = []
    for ind, (lo, hi) in BOUNDS.items():
        s = obs[(obs.indicator == ind) & (obs.source == "IMF WEO")]
        bad = s[(s.value < lo) | (s.value > hi)]
        tested += len(s); failed += len(bad)
        ex += [dict(code=r.code, indicator=ind, year=int(r.year), value=round(float(r.value), 1)) for r in bad.sort_values("value", key=abs, ascending=False).head(3).itertuples()]
    return _res("bounds", "Values inside plausible ranges (for example inflation under 200 percent)", tested, failed, ex[:8],
                "Large values are not always wrong. Hyperinflation is real, so these are flagged for review, not deleted.")


def check_gaps(obs):
    s = obs[(obs.source == "IMF WEO") & (~obs.is_projection.astype(bool)) & obs.indicator.isin(["gdp_growth", "inflation", "unemployment", "gov_debt"])]
    tested = failed = 0; ex = []
    for (c, i), g in s.groupby(["code", "indicator"]):
        yrs = set(g.year); span = range(min(yrs), max(yrs) + 1)
        miss = [y for y in span if y not in yrs]
        tested += 1
        if miss:
            failed += 1
            if len(ex) < 6: ex.append(dict(code=c, indicator=i, missing_years=miss[:6], n_missing=len(miss)))
    return _res("gaps", "No missing years between the first and last actual year of a series", tested, failed, ex)


def check_internal(obs):
    """Does published growth match growth computed from the published real GDP level? Same for inflation and the CPI index."""
    w = obs[(obs.source == "IMF WEO") & (~obs.is_projection.astype(bool))]
    out = []
    for lvl, rate, name in (("gdp_real_level", "gdp_growth", "growth"), ("cpi_index", "inflation", "inflation")):
        a = w[w.indicator == lvl].pivot(index="year", columns="code", values="value").sort_index()
        b = w[w.indicator == rate].pivot(index="year", columns="code", values="value").sort_index()
        calc = (a / a.shift(1) - 1) * 100
        diff = (calc - b.reindex_like(calc)).abs().stack().dropna()
        out.append((name, diff))
    tested = sum(len(d) for _, d in out); bad = [(n, d[d > TOL_INTERNAL]) for n, d in out]
    failed = sum(len(b) for _, b in bad)
    ex = []
    for n, b in bad:
        for (y, c), v in b.sort_values(ascending=False).head(3).items():
            ex.append(dict(measure=n, code=c, year=int(y), gap_pp=round(float(v), 2)))
    return _res("internal", "Published growth and inflation match the rates computed from the published levels", tested, failed, ex,
                f"Tolerance {TOL_INTERNAL} percentage points for rounding.")


def cross_source(obs):
    """Pair up IMF and World Bank values for the same country, indicator and year, actual years only."""
    imf = obs[(obs.source == "IMF WEO") & (~obs.is_projection.astype(bool)) & obs.indicator.isin(["gdp_growth", "inflation", "unemployment"])]
    wb = obs[obs.source == "World Bank WDI"]
    m = imf.merge(wb, on=["code", "indicator", "year"], suffixes=("_imf", "_wb"))
    m["diff"] = (m.value_imf - m.value_wb).abs()
    return m


def check_cross(obs):
    """One check per indicator. Inflation uses a relative allowance for very high values (hyperinflation is
    measured on different bases). That rule was chosen after seeing that a handful of hyperinflation cases drove
    the large gaps. Unemployment is checked against a wider limit because the IMF reports national definitions
    while the World Bank series is a modeled estimate on a common ILO definition."""
    m = cross_source(obs)
    out = []
    for ind, name, tol, rel in (("gdp_growth", "IMF and World Bank GDP growth agree within 0.5 percentage points", TOL_CROSS, 0.0),
                                ("inflation", "IMF and World Bank inflation agree within 0.5 points or 2 percent of the level", TOL_CROSS, 0.02),
                                ("unemployment", "IMF and World Bank unemployment agree within 1 point (different definitions)", 1.0, 0.0)):
        g = m[m.indicator == ind].copy()
        allow = np.maximum(tol, rel * g[["value_imf", "value_wb"]].abs().max(axis=1))
        bad = g[g["diff"] > allow]
        ex = [dict(code=r.code, year=int(r.year), imf=round(float(r.value_imf), 1), world_bank=round(float(r.value_wb), 1))
              for r in bad.sort_values("diff", ascending=False).head(5).itertuples()]
        per = g.groupby("code")["diff"].median()
        top15 = bad.code.value_counts().head(15).sum() / len(bad) if len(bad) else 0.0
        note = (f"{int((per > 0.5).sum())} of {len(per)} countries have a median gap above 0.5 points, and the 15 worst countries hold "
                f"{top15 * 100:.0f}% of all flagged pairs. ") + f"Median gap {g['diff'].median():.3f} percentage points, so most pairs match closely. Gaps cluster in particular countries ({', '.join(bad.code.value_counts().head(4).index)})."
        out.append(_res(f"cross_{ind}", name, len(g), len(bad), ex, note))
    return out


def check_stale(obs, ref_year=2025, lag=3):
    s = obs[(obs.source == "IMF WEO") & (obs.indicator == "gdp_growth")].dropna(subset=["latest_actual"]).drop_duplicates("code")
    bad = s[s.latest_actual < ref_year - lag + 1]
    return _res("stale", f"Latest actual GDP growth is no more than {lag} years old", len(s), len(bad),
                [dict(code=r.code, latest_actual=int(r.latest_actual)) for r in bad.sort_values("latest_actual").head(6).itertuples()],
                "A stale actual means the recent numbers are all estimates by IMF staff.")


def run_all(obs):
    return [check_unique(obs), check_bounds(obs), check_gaps(obs), check_internal(obs), *check_cross(obs), check_stale(obs)]
