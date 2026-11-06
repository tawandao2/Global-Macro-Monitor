import sys
sys.path.insert(0, ".")
import numpy as np
import pandas as pd
from src import quality as q


def obs(rows):
    d = pd.DataFrame(rows, columns=["source", "code", "indicator", "year", "value"])
    d["is_projection"] = False; d["latest_actual"] = 2025.0
    return d


def test_duplicates_are_caught():
    o = obs([("IMF WEO", "AAA", "gdp_growth", 2020, 1.0), ("IMF WEO", "AAA", "gdp_growth", 2020, 1.0), ("IMF WEO", "AAA", "gdp_growth", 2021, 2.0)])
    assert q.check_unique(o)["failed"] == 2


def test_out_of_range_values_are_flagged_not_dropped():
    o = obs([("IMF WEO", "AAA", "inflation", 2020, 5.0), ("IMF WEO", "AAA", "inflation", 2021, 900.0)])
    r = q.check_bounds(o)
    assert r["failed"] == 1 and len(o) == 2


def test_gap_inside_a_series_is_caught_but_edges_are_not():
    rows = [("IMF WEO", "AAA", "gdp_growth", y, 1.0) for y in (2010, 2011, 2013, 2014)]
    assert q.check_gaps(obs(rows))["failed"] == 1
    assert q.check_gaps(obs([("IMF WEO", "BBB", "gdp_growth", y, 1.0) for y in (2012, 2013, 2014)]))["failed"] == 0


def test_projection_years_are_excluded_from_gap_and_cross_checks():
    o = obs([("IMF WEO", "AAA", "gdp_growth", y, 1.0) for y in (2010, 2011, 2016)])
    o.loc[o.year == 2016, "is_projection"] = True
    assert q.check_gaps(o)["failed"] == 0


def test_internal_consistency_catches_a_wrong_growth_rate():
    lvl = [100, 102, 104.04]
    rows = [("IMF WEO", "AAA", "gdp_real_level", 2000 + i, v) for i, v in enumerate(lvl)]
    rows += [("IMF WEO", "AAA", "gdp_growth", 2001, 2.0), ("IMF WEO", "AAA", "gdp_growth", 2002, 5.0)]
    r = q.check_internal(obs(rows))
    assert r["tested"] == 2 and r["failed"] == 1


def test_cross_source_tolerances():
    rows = [("IMF WEO", "AAA", "gdp_growth", 2020, 2.0), ("World Bank WDI", "AAA", "gdp_growth", 2020, 2.3),
            ("IMF WEO", "AAA", "gdp_growth", 2021, 2.0), ("World Bank WDI", "AAA", "gdp_growth", 2021, 3.0),
            ("IMF WEO", "BBB", "inflation", 2020, 1000.0), ("World Bank WDI", "BBB", "inflation", 2020, 1010.0)]
    res = {r["id"]: r for r in q.check_cross(obs(rows))}
    assert res["cross_gdp_growth"]["failed"] == 1       # 1.0 gap is over 0.5, 0.3 is not
    assert res["cross_inflation"]["failed"] == 0        # 10 on a base of 1000 is within 2 percent


def test_stale_series_found():
    o = obs([("IMF WEO", "AAA", "gdp_growth", 2010, 1.0), ("IMF WEO", "BBB", "gdp_growth", 2010, 1.0)])
    o.loc[o.code == "AAA", "latest_actual"] = 2012.0
    assert q.check_stale(o)["failed"] == 1
