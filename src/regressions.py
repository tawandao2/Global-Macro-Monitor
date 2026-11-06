"""Cross country panel regressions. These describe associations, not causes."""
import json, sys
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
sys.path.insert(0, ".")
from src.panel import load_panel, lag

LABELS = {"log_gdppc_l1": "Income level, per doubling of GDP per capita, last year", "infl_c_l1": "Inflation last year, per 10 points (capped at 50%)",
          "gov_debt_l1": "Government debt last year (per 10 points of GDP)", "current_account_l1": "Current account last year (per 10 points of GDP)",
          "fiscal_balance_l1": "Fiscal balance last year (per 10 points of GDP)"}


def prepare():
    p = load_panel()
    p["infl_c"] = p.inflation.clip(-5, 50)
    p = lag(p, ["log_gdppc", "infl_c", "gov_debt", "current_account", "fiscal_balance"])
    for c in ("gov_debt_l1", "current_account_l1", "fiscal_balance_l1", "infl_c_l1"):
        p[c] = p[c] / 10.0                     # coefficients are then per 10 points
    p["log_gdppc_l1"] = p["log_gdppc_l1"] / np.log(2)   # per doubling of income
    return p


def fit(d, formula, cluster="code"):
    d = d.dropna(subset=["gdp_growth"] + [c for c in ["log_gdppc_l1", "infl_c_l1", "gov_debt_l1", "current_account_l1", "fiscal_balance_l1"] if c in formula])
    d = d[d.gdp_growth.between(-30, 30)]
    m = smf.ols(formula, d).fit(cov_type="cluster", cov_kwds={"groups": d[cluster].astype("category").cat.codes})
    return m, d


def tidy(m, keys):
    ci = m.conf_int()
    return {k: dict(label=LABELS[k], coef=float(m.params[k]), lo=float(ci.loc[k, 0]), hi=float(ci.loc[k, 1]), p=float(m.pvalues[k])) for k in keys}


def main(out="eval/results_regressions.json"):
    p = prepare()
    keys = ["log_gdppc_l1", "infl_c_l1", "gov_debt_l1", "current_account_l1", "fiscal_balance_l1"]
    rhs = " + ".join(keys)
    specs = {
        "no_fixed_effects": f"gdp_growth ~ {rhs}",
        "country_effects": f"gdp_growth ~ {rhs} + C(code)",
        "country_and_year_effects": f"gdp_growth ~ {rhs} + C(code) + C(year)",
    }
    res = {"models": {}, "outcome": "Real GDP growth, percent", "years": "1991 to 2025, actual values only"}
    for name, f in specs.items():
        m, d = fit(p, f)
        res["models"][name] = dict(n=int(m.nobs), countries=int(d.code.nunique()), r2=float(m.rsquared), coefs=tidy(m, keys))
    # robustness for the preferred model
    f = specs["country_and_year_effects"]
    rob = {}
    for name, sub in {"excluding 2020 and 2021": p[~p.year.isin([2020, 2021])], "dropping extreme years (growth over 20 percent either way)": p[p.gdp_growth.abs() < 20],
                      "since 2000 only": p[p.year >= 2000]}.items():
        m, d = fit(sub, f)
        rob[name] = dict(n=int(m.nobs), coefs=tidy(m, keys))
    res["robustness"] = rob
    # does the income level result survive? convergence is the headline
    res["notes"] = ["Standard errors are clustered by country.", "All variables are lagged one year so the regressors are known before growth is measured.",
                    "Fixed effects remove differences between countries that do not change (and, for year effects, shocks every country shared)."]
    json.dump(res, open(out, "w"), indent=1)
    return res


if __name__ == "__main__":
    r = main()
    for name, m in r["models"].items():
        print(f"\n{name}  n={m['n']} countries={m['countries']} R2={m['r2']:.3f}")
        for k, c in m["coefs"].items(): print(f"  {k:20s} {c['coef']:+.3f} [{c['lo']:+.3f}, {c['hi']:+.3f}] p={c['p']:.3f}")
    for name, m in r["robustness"].items():
        print("\nrobust:", name, m["n"]); [print(f"  {k:20s} {c['coef']:+.3f} [{c['lo']:+.3f}, {c['hi']:+.3f}]") for k, c in m["coefs"].items()]
