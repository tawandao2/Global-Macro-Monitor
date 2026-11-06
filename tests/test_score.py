import sys
sys.path.insert(0, ".")
import numpy as np
import pandas as pd
from src.score import flags, flags_with, tier, MIN_AVAILABLE


def wide(**kw):
    base = dict(inflation=2.0, gdp_growth=3.0, unemployment=5.0, gov_debt=50.0, current_account=0.0, fiscal_balance=-1.0)
    base.update(kw)
    return pd.DataFrame([base], index=["AAA"])


def test_each_rule_fires_only_past_its_threshold():
    w = wide(inflation=10.1, gdp_growth=0.9, unemployment=12.1, gov_debt=90.1, current_account=-5.1, fiscal_balance=-5.1)
    assert flags(w).iloc[0].sum() == 6
    w = wide(inflation=10.0, gdp_growth=1.0, unemployment=12.0, gov_debt=90.0, current_account=-5.0, fiscal_balance=-5.0)
    assert flags(w).iloc[0].sum() == 0


def test_tier_boundaries():
    for n, expect in ((0, "Low"), (1, "Low"), (2, "Elevated"), (3, "High"), (6, "High")):
        vals = [dict(inflation=11.0), dict(gdp_growth=0.0), dict(gov_debt=100.0), dict(unemployment=15.0), dict(current_account=-9.0), dict(fiscal_balance=-9.0)][:n]
        kw = {k: v for d in vals for k, v in d.items()}
        t, nf, na = tier(flags(wide(**kw)))
        assert t.iloc[0] == expect and nf.iloc[0] == n


def test_missing_data_is_not_a_flag_and_too_little_data_is_not_rated():
    w = wide(inflation=np.nan, gdp_growth=np.nan, unemployment=np.nan)
    t, nf, na = tier(flags(w))
    assert na.iloc[0] == 3 and t.iloc[0] == "Not rated" and nf.iloc[0] == 0
    w = wide(unemployment=np.nan)
    assert tier(flags(w))[2].iloc[0] == 5 >= MIN_AVAILABLE


def test_stricter_thresholds_never_flag_fewer():
    rng = np.random.default_rng(1)
    w = pd.DataFrame({"inflation": rng.uniform(-2, 30, 300), "gdp_growth": rng.uniform(-5, 8, 300), "unemployment": rng.uniform(1, 25, 300),
                      "gov_debt": rng.uniform(10, 200, 300), "current_account": rng.uniform(-20, 10, 300), "fiscal_balance": rng.uniform(-15, 5, 300)})
    assert (flags_with(w, 0.8).sum(axis=1) >= flags_with(w, 1.0).sum(axis=1)).all()
    assert (flags_with(w, 1.25).sum(axis=1) <= flags_with(w, 1.0).sum(axis=1)).all()
