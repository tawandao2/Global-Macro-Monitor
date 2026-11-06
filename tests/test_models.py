import sys
sys.path.insert(0, ".")
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from src.panel import lag
from src.forecast import features


def panel(n_c=3, years=range(2000, 2012)):
    rows = []
    for i in range(n_c):
        for y in years:
            rows.append(dict(code=f"C{i}", year=y, gdp_growth=float(i * 10 + (y - 2000)), gov_debt=1.0, current_account=1.0, log_gdppc=1.0, inflation=1.0))
    return pd.DataFrame(rows)


def test_lag_uses_the_previous_year_only():
    p = lag(panel(), ["gdp_growth"])
    r = p[(p.code == "C1") & (p.year == 2005)].iloc[0]
    assert r.gdp_growth_l1 == 10 + 4


def test_lag_is_missing_when_a_year_is_skipped():
    p = panel(); p = p[p.year != 2004]
    p = lag(p, ["gdp_growth"])
    assert np.isnan(p[(p.code == "C0") & (p.year == 2005)].gdp_growth_l1.iloc[0])


def test_forecast_features_never_use_the_target_year():
    p = panel()
    f = features(p, "gdp_growth")
    row = f[(f.code == "C1") & (f.year == 2006)].iloc[0]      # predicting 2006
    assert row.lag1 == 10 + 5 and row.lag2 == 10 + 4 and row.y == 10 + 6
    assert row.mean5 == np.mean([10 + k for k in (1, 2, 3, 4, 5)])
    # changing the 2006 value must not change any feature for 2006
    q = p.copy(); q.loc[(q.code == "C1") & (q.year == 2006), "gdp_growth"] = 999.0
    row2 = features(q, "gdp_growth").query("code == 'C1' and year == 2006").iloc[0]
    assert row2.lag1 == row.lag1 and row2.mean5 == row.mean5 and row2.world_lag1 == row.world_lag1 and row2.y == 999.0


def test_regression_recovers_a_known_effect_and_year_effects_remove_a_shared_shock():
    rng = np.random.default_rng(0)
    n, t = 120, 25
    d = pd.DataFrame({"code": np.repeat(np.arange(n), t), "year": np.tile(np.arange(t), n)})
    d["x"] = rng.normal(size=len(d))
    shock = rng.normal(scale=3, size=t)
    d["y"] = 0.5 * d.x + shock[d.year] + rng.normal(size=len(d))
    m = smf.ols("y ~ x + C(code) + C(year)", d).fit()
    assert abs(m.params["x"] - 0.5) < 0.05
