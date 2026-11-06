"""One year ahead forecasts of growth and inflation, scored with a rolling origin.
For each target year t the models see only data up to t-1, are trained on targets up to t-1, and are scored on t."""
import json, sys, warnings
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
sys.path.insert(0, ".")
from src.panel import load_panel

warnings.filterwarnings("ignore")
FIRST_TARGET, LAST_TARGET, SEED = 2008, 2025, 11


def features(p, target):
    """Feature frame for predicting `target`: everything is measured at or before target-1."""
    p = p.sort_values(["code", "year"]).copy()
    g = p.groupby("code")[target]
    f = pd.DataFrame({"code": p.code, "year": p.year + 1, "y": np.nan})  # row describes target year = year + 1
    f["lag1"] = p[target].values
    for n in (2, 3):
        f[f"lag{n}"] = g.shift(n - 1).values
    f["mean5"] = g.transform(lambda s: s.rolling(5, min_periods=3).mean()).values
    f["debt"] = p.gov_debt.values; f["cab"] = p.current_account.values; f["logpc"] = p.log_gdppc.values
    world = p.groupby("year")[target].median()
    f["world_lag1"] = p.year.map(world).values
    nxt = p[["code", "year", target]].assign(year=lambda d: d.year - 1).rename(columns={target: "y_next"})
    f = f.merge(nxt.assign(year=nxt.year + 1)[["code", "year", "y_next"]], on=["code", "year"], how="left")
    f["y"] = f.y_next; return f.drop(columns="y_next")


def clip(x, lo, hi):
    return np.clip(x, lo, hi)


def run(target, lo, hi):
    p = load_panel(first=1985)
    p = p[p[target].between(lo, hi) | p[target].isna()]
    f = features(p, target)
    cols = ["lag1", "lag2", "lag3", "mean5", "debt", "cab", "logpc", "world_lag1"]
    rows = []
    for t in range(FIRST_TARGET, LAST_TARGET + 1):
        tr = f[(f.year < t)].dropna(subset=["y", "lag1", "mean5"])
        te = f[(f.year == t)].dropna(subset=["y", "lag1", "mean5"]).copy()
        if len(te) < 50:
            continue
        te["naive"] = te.lag1
        te["mean5_fc"] = te.mean5
        # pooled AR(1) toward the cross country mean of last year: y = a + b*lag1 + c*mean5
        r = Ridge(alpha=1.0).fit(tr[["lag1", "mean5"]], tr.y); te["blend"] = r.predict(te[["lag1", "mean5"]])
        gb = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=150, l2_regularization=2.0, random_state=SEED, loss="absolute_error")
        gb.fit(tr[cols], tr.y); te["boosting"] = gb.predict(te[cols])
        te["target_year"] = t
        te["world_median"] = te.world_lag1
        rows.append(te[["code", "target_year", "y", "naive", "world_median", "mean5_fc", "blend", "boosting"]])
    d = pd.concat(rows)
    models = ["naive", "world_median", "mean5_fc", "blend", "boosting"]
    out = {"note": "Scored on observations inside the range used for cleaning (see lo and hi); real-time data vintages are not used.", "range": [lo, hi], "target": target, "n_scored": int(len(d)), "origins": f"{FIRST_TARGET} to {LAST_TARGET}", "models": {}, "by_year": {}}
    shock = d.target_year.isin([2009, 2020, 2021]) if target == "gdp_growth" else d.target_year.isin([2021, 2022])
    for m in models:
        e = (d[m] - d.y).abs()
        out["models"][m] = dict(mae=float(e.mean()), mae_calm_years=float(e[~shock].mean()), mae_shock_years=float(e[shock].mean()), median_abs_error=float(e.median()))
    # paired bootstrap over countries for the gain of each model over the naive forecast
    rng = np.random.default_rng(SEED)
    codes = d.code.unique(); by = {c: g for c, g in d.groupby("code")}
    diffs = {m: [] for m in models if m != "naive"}
    vs_blend = []
    for _ in range(300):
        s = pd.concat([by[c] for c in rng.choice(codes, len(codes))])
        for m in diffs:
            diffs[m].append((s[m] - s.y).abs().mean() - (s.naive - s.y).abs().mean())
        vs_blend.append((s.boosting - s.y).abs().mean() - (s.blend - s.y).abs().mean())
    for m, v in diffs.items():
        out["models"][m]["mae_minus_naive"] = float(np.mean(v)); out["models"][m]["ci"] = [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]
    out["boosting_minus_blend"] = dict(mean=float(np.mean(vs_blend)), ci=[float(np.percentile(vs_blend, 2.5)), float(np.percentile(vs_blend, 97.5))])
    for t, g in d.groupby("target_year"):
        out["by_year"][int(t)] = {m: float((g[m] - g.y).abs().mean()) for m in models}
    return out, d


def main(out="eval/results_forecast.json"):
    res = {}
    for target, lo, hi in (("gdp_growth", -30, 30), ("inflation", -10, 100)):
        res[target], _ = run(target, lo, hi)
    json.dump(res, open(out, "w"), indent=1)
    return res


if __name__ == "__main__":
    r = main()
    for t, v in r.items():
        print(f"\n{t}: {v['n_scored']} country-year forecasts, targets {v['origins']}")
        print("  boosting minus blend:", round(v["boosting_minus_blend"]["mean"], 3), np.round(v["boosting_minus_blend"]["ci"], 3))
        for m, x in v["models"].items():
            extra = f"  vs naive {x['mae_minus_naive']:+.3f} {np.round(x['ci'],3)}" if "ci" in x else ""
            print(f"  {m:10s} MAE {x['mae']:.3f}  calm {x['mae_calm_years']:.3f}  shock {x['mae_shock_years']:.3f}{extra}")
