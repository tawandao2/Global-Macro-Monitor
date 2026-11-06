"""Build the country by year panel of actual (not projected) values from the database."""
import duckdb
import numpy as np
import pandas as pd

DB = "data/macro.duckdb"
VARS = ["gdp_growth", "inflation", "unemployment", "gov_debt", "fiscal_balance", "current_account", "gdp_per_capita", "population"]


def load_panel(db=DB, first=1990, last=2025, actual_only=True):
    con = duckdb.connect(db, read_only=True)
    o = con.sql("""select o.code, o.year, o.indicator, o.value from observations o join countries c using(code)
                   where o.source='IMF WEO' and not c.is_group and o.indicator in (%s) %s and o.year between %d and %d"""
                % (",".join(f"'{v}'" for v in VARS), "and not o.is_projection" if actual_only else "", first, last)).df()
    p = o.pivot_table(index=["code", "year"], columns="indicator", values="value").reset_index()
    p = p.sort_values(["code", "year"]).reset_index(drop=True)
    p["log_gdppc"] = np.log(p.gdp_per_capita)
    return p


def lag(p, cols, n=1):
    g = p.groupby("code")
    out = p.copy()
    for c in cols:
        out[f"{c}_l{n}"] = g[c].shift(n)
    # shift only counts if the previous row is really the previous year
    gap = p.groupby("code").year.diff().shift(0)
    for c in cols:
        out.loc[gap.ne(n) & gap.notna() | gap.isna(), f"{c}_l{n}"] = np.nan
    return out
