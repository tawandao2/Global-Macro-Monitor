import os, sys
import pytest
sys.path.insert(0, ".")
pytestmark = pytest.mark.skipif(not os.path.exists("data/raw/weo.csv"), reason="raw data not downloaded")
from src.ingest import load_weo, load_wdi


def test_projection_flag_follows_the_imf_latest_actual_year():
    o, _ = load_weo()
    g = o[(o.indicator == "gdp_growth") & (o.code == "USA")]
    last = int(g.latest_actual.iloc[0])
    assert not g[g.year <= last].is_projection.any() and g[g.year > last].is_projection.all()


def test_country_groups_are_separated():
    _, c = load_weo()
    assert c.is_group.sum() == 13 and not c[c.code == "USA"].is_group.any()


def test_wdi_missing_markers_become_missing_not_zero():
    d, _ = load_wdi()
    assert d.value.notna().all() and len(d) > 20000
