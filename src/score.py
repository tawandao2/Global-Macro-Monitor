"""Transparent early warning score. Six rules, set in advance from common rules of thumb, no fitted weights."""
import json, sys
import duckdb
import numpy as np
import pandas as pd
sys.path.insert(0, ".")

SNAPSHOT = 2025
# (indicator, label, direction, threshold). 'above' flags values over the threshold, 'below' flags values under it.
RULES = [("inflation", "High inflation", "above", 10.0), ("gdp_growth", "Weak growth", "below", 1.0),
         ("unemployment", "High unemployment", "above", 12.0), ("gov_debt", "High government debt", "above", 90.0),
         ("current_account", "Large external deficit", "below", -5.0), ("fiscal_balance", "Large budget deficit", "below", -5.0)]
MIN_AVAILABLE = 4
REGION_FIX = {"KOS": "Europe", "TWN": "Asia", "WBG": "Asia", "TLS": "Asia"}
ISO_FIX = {"KOS": 0, "WBG": 275, "TWN": 158}


def flags(wide):
    """One row per country. 1 means the rule fires, 0 means it does not, missing means no data."""
    return flags_with(wide, 1.0)


def tier(f):
    n_avail = f.notna().sum(axis=1); n_flag = f.sum(axis=1)
    t = pd.Series("Not rated", index=f.index)
    ok = n_avail >= MIN_AVAILABLE
    t[ok & (n_flag <= 1)] = "Low"; t[ok & (n_flag == 2)] = "Elevated"; t[ok & (n_flag >= 3)] = "High"
    return t, n_flag, n_avail


def snapshot(con, year=SNAPSHOT):
    d = con.sql(f"""select o.code, c.name, o.indicator, o.value, o.is_projection, o.latest_actual from observations o join countries c using(code)
                    where o.source='IMF WEO' and not c.is_group and o.year={year}""").df()
    wide = d.pivot_table(index=["code", "name"], columns="indicator", values="value").reset_index().set_index("code")
    est = d[d.indicator == "gdp_growth"].set_index("code")[["is_projection", "latest_actual"]]
    return wide, est


def region_income(wide):
    import pycountry, pycountry_convert as pc
    names = {"AF": "Africa", "AS": "Asia", "EU": "Europe", "NA": "North America", "SA": "South America", "OC": "Oceania"}
    reg, num = {}, {}
    for code in wide.index:
        c = pycountry.countries.get(alpha_3=code)
        num[code] = ISO_FIX.get(code, int(c.numeric) if c else 0)
        try:
            reg[code] = names[pc.country_alpha2_to_continent_code(c.alpha_2)]
        except Exception:
            reg[code] = REGION_FIX.get(code, "Other")
    q = pd.qcut(wide.gdp_per_capita.rank(method="first"), 4, labels=["Lowest income quarter", "Lower middle", "Upper middle", "Highest income quarter"])
    return pd.Series(reg), pd.Series(num), q.astype(str)


def flags_with(wide, tight=1.0):
    """tight below 1 makes every rule stricter (more countries flagged); above 1 makes it looser."""
    out = pd.DataFrame(index=wide.index)
    for ind, label, how, thr in RULES:
        t = thr * tight if how == "above" else (thr / tight if thr > 0 else thr * tight)
        v = wide[ind]
        out[ind] = np.where(v.isna(), np.nan, (v > t) if how == "above" else (v < t)).astype(float)
    return out


def sensitivity(wide):
    base_t, base_n, _ = tier(flags_with(wide))
    res = {}
    for name, tight in (("thresholds 20 percent stricter", 0.8), ("thresholds 25 percent looser", 1.25)):
        t2, n2, _ = tier(flags_with(wide, tight))
        both = base_t != "Not rated"
        res[name] = dict(rank_corr=float(base_n[both].corr(n2[both], method="spearman")), tier_changed=float((t2[both] != base_t[both]).mean()),
                         high_count=int((t2 == "High").sum()))
    return res


def validate(con):
    """Does a High tier mean anything? Compute the tier at year t from actual data only, then look at year t+1."""
    rows = []
    d = con.sql("""select o.code, o.year, o.indicator, o.value from observations o join countries c using(code)
                   where o.source='IMF WEO' and not c.is_group and not o.is_projection""").df()
    wide_all = d.pivot_table(index=["year", "code"], columns="indicator", values="value")
    for t in range(2000, 2025):
        try:
            w = wide_all.loc[t]; nxt = wide_all.loc[t + 1]
        except KeyError:
            continue
        ti, n, _ = tier(flags(w))
        rows.append(pd.DataFrame({"year": t, "tier": ti, "next_growth": nxt.gdp_growth.reindex(w.index), "next_infl": nxt.inflation.reindex(w.index)}))
    r = pd.concat(rows).dropna(subset=["next_growth"])
    r = r[r.tier != "Not rated"]
    g = r.groupby("tier").agg(country_years=("year", "size"), mean_next_growth=("next_growth", "mean"), median_next_growth=("next_growth", "median"),
                              share_negative_growth=("next_growth", lambda s: (s < 0).mean()),
                              share_next_inflation_over_10=("next_infl", lambda s: (s.dropna() > 10).mean())).round(4)
    # does this hold after removing the global 2009 and 2020 shocks?
    calm = r[~r.year.isin([2008, 2009, 2019, 2020])]
    g2 = calm.groupby("tier").agg(mean_next_growth=("next_growth", "mean"), share_negative_growth=("next_growth", lambda s: (s < 0).mean())).round(4)
    return g.reset_index().to_dict("records"), g2.reset_index().to_dict("records")


def main():
    con = duckdb.connect("data/macro.duckdb", read_only=True)
    wide, est = snapshot(con)
    f = flags(wide); t, nf, na = tier(f)
    reg, num, inc = region_income(wide)
    out = wide.copy()
    out["tier"] = t; out["n_flags"] = nf.astype(int); out["n_available"] = na.astype(int)
    for ind, label, how, thr in RULES:
        out["flag_" + ind] = f[ind]
    out["region"] = reg; out["iso_numeric"] = num; out["income_group"] = inc
    out["estimated"] = est.is_projection.reindex(out.index); out["latest_actual"] = est.latest_actual.reindex(out.index)
    from src.quality import cross_source
    cs = cross_source(con.sql("select * from observations").df())
    for ind in ("gdp_growth", "inflation"):
        out["gap_" + ind] = cs[cs.indicator == ind].groupby("code")["diff"].median().reindex(out.index)
    out.reset_index().to_csv("data/country_snapshot.csv", index=False)
    # long series for the country view, 1990 to 2031, with projection marker
    s = con.sql("""select o.code, c.name, o.indicator, o.year, o.value, o.is_projection from observations o join countries c using(code)
                   where o.source='IMF WEO' and not c.is_group and o.indicator in ('gdp_growth','inflation','unemployment','gov_debt','current_account','fiscal_balance')
                   and o.year >= 1990""").df()
    s.to_csv("data/country_series.csv", index=False)
    v_all, v_calm = validate(con)
    res = {"snapshot_year": SNAPSHOT, "rules": [dict(indicator=i, label=l, direction=h, threshold=x) for i, l, h, x in RULES], "min_available": MIN_AVAILABLE,
           "tiers": t.value_counts().to_dict(), "sensitivity": sensitivity(wide), "validation": v_all, "validation_calm_years": v_calm,
           "note": "Thresholds were set before looking at outcomes, from common rules of thumb. Validation looks one year ahead for 2000 to 2024."}
    json.dump(res, open("eval/results_score.json", "w"), indent=1)
    return res, out


if __name__ == "__main__":
    r, out = main()
    print(r["tiers"]); print(r["sensitivity"])
    print(pd.DataFrame(r["validation"]).to_string()); print(pd.DataFrame(r["validation_calm_years"]).to_string())
    print(out[out.tier == "High"].sort_values("n_flags", ascending=False)[["name", "n_flags", "inflation", "gdp_growth", "gov_debt"]].head(12).round(1).to_string())
    print(out.region.value_counts().to_dict(), out.iso_numeric.eq(0).sum())
