"""Build data/macro.duckdb from the two downloaded files, record the load, and run the quality checks."""
import json, sys, datetime
import duckdb
import pandas as pd
sys.path.insert(0, ".")
from src.ingest import load_weo, load_wdi, file_sha, WEO_PATH, WDI_PATH, WEO_TO_WDI
from src.quality import run_all, cross_source

DB = "data/macro.duckdb"


def build():
    weo, countries = load_weo()
    wdi, wdi_names = load_wdi()
    # put IMF-specific codes onto the World Bank code so the two sources join
    countries["wdi_code"] = countries.code.map(lambda c: WEO_TO_WDI.get(c, c))
    wdi["code"] = wdi.code.replace({v: k for k, v in WEO_TO_WDI.items()})
    obs = pd.concat([weo, wdi.assign(is_projection=False, projection_basis="World Bank estimate or actual", latest_actual=None)], ignore_index=True)
    checks = run_all(obs)
    registry = pd.DataFrame([
        dict(source="IMF WEO", dataset="World Economic Outlook, October 2026 (IMF.RES:WEO 9.0.0)", file_sha=file_sha(WEO_PATH), rows=len(weo), loaded_at=datetime.datetime.now().isoformat(timespec="seconds")),
        dict(source="World Bank WDI", dataset="World Development Indicators, updated 10/08/2026", file_sha=file_sha(WDI_PATH), rows=len(wdi), loaded_at=datetime.datetime.now().isoformat(timespec="seconds"))])
    con = duckdb.connect(DB)
    for t in ("countries", "observations", "source_registry", "quality_checks"):
        con.execute(f"DROP TABLE IF EXISTS {t}")
    con.register("c", countries); con.execute("CREATE TABLE countries AS SELECT * FROM c")
    con.register("o", obs); con.execute("CREATE TABLE observations AS SELECT * FROM o")
    con.register("r", registry); con.execute("CREATE TABLE source_registry AS SELECT * FROM r")
    q = pd.DataFrame([{k: (json.dumps(v) if k == "examples" else v) for k, v in c.items()} for c in checks])
    con.register("q", q); con.execute("CREATE TABLE quality_checks AS SELECT * FROM q")
    con.close()
    json.dump(checks, open("eval/results_quality.json", "w"), indent=1)
    return checks, obs


if __name__ == "__main__":
    checks, obs = build()
    print(len(obs), "observations")
    for c in checks:
        print(f"{c['id']:13s} tested {c['tested']:>7,} failed {c['failed']:>6,} ({c['failure_rate']*100:.2f}%)  {c['examples'][:2]}")
