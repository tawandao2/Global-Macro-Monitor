"""Load the IMF World Economic Outlook (WEO) and World Bank WDI files into tidy tables."""
import hashlib
import re
import pandas as pd

WEO_PATH, WDI_PATH = "data/raw/weo.csv", "data/raw/wdi.csv"

# WEO series code (after the country prefix) -> short name, label, unit
WEO_INDICATORS = {
    "NGDP_RPCH.A": ("gdp_growth", "Real GDP growth", "percent"),
    "PCPIPCH.A": ("inflation", "Inflation, average consumer prices", "percent"),
    "LUR.A": ("unemployment", "Unemployment rate", "percent"),
    "GGXWDG_NGDP.A": ("gov_debt", "Government gross debt", "percent of GDP"),
    "GGXCNL_NGDP.A": ("fiscal_balance", "Government net lending or borrowing", "percent of GDP"),
    "BCA_NGDPD.A": ("current_account", "Current account balance", "percent of GDP"),
    "NGDPDPC.A": ("gdp_per_capita", "GDP per capita, current US dollars", "US dollars"),
    "NGDPD.A": ("gdp_usd", "GDP, current US dollars", "billions of US dollars"),
    "LP.A": ("population", "Population", "millions of persons"),
    "NGDP_R.A": ("gdp_real_level", "Real GDP, constant prices", "domestic currency (billions)"),
    "PCPI.A": ("cpi_index", "Consumer price index, period average", "index"),
}
WDI_INDICATORS = {"NY.GDP.MKTP.KD.ZG": "gdp_growth", "FP.CPI.TOTL.ZG": "inflation", "SL.UEM.TOTL.ZS": "unemployment"}
# IMF codes that differ from the World Bank's
WEO_TO_WDI = {"KOS": "XKX", "WBG": "PSE"}


def file_sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]


def _first_year(x):
    m = re.search(r"(\d{4})", str(x)) if pd.notna(x) else None
    return int(m.group(1)) if m else None


def load_weo(path=WEO_PATH):
    w = pd.read_csv(path, low_memory=False)
    w["code"] = w.SERIES_CODE.str.split(".", n=1).str[0]
    w["ind_code"] = w.SERIES_CODE.str.split(".", n=1).str[1]
    w = w[w.ind_code.isin(WEO_INDICATORS)].copy()
    w["indicator"] = w.ind_code.map(lambda c: WEO_INDICATORS[c][0])
    w["latest_actual"] = w.LATEST_ACTUAL_ANNUAL_DATA.map(_first_year)
    years = [c for c in w.columns if re.fullmatch(r"\d{4}", c)]
    long = w.melt(id_vars=["code", "COUNTRY", "indicator", "latest_actual", "SCALE"], value_vars=years, var_name="year", value_name="value")
    long = long.dropna(subset=["value"]).copy()
    long["year"] = long.year.astype(int)
    # Billions and millions are stated in the SCALE column; put everything in the unit named above
    long["source"] = "IMF WEO"
    # a year is a projection when it is after the latest actual year the IMF reports for that series
    known = long.latest_actual.notna()
    long["is_projection"] = (long.year > long.latest_actual).where(known, long.year >= 2026)
    long["projection_basis"] = known.map({True: "IMF latest actual year", False: "inferred, year 2026 or later"})
    countries = (w[["code", "COUNTRY"]].drop_duplicates().rename(columns={"COUNTRY": "name"}))
    countries["is_group"] = countries.code.str.startswith(("G0", "G1", "G2", "G4", "G5", "G6", "G9", "GX"))
    return long[["source", "code", "indicator", "year", "value", "is_projection", "projection_basis", "latest_actual"]], countries


def load_wdi(path=WDI_PATH):
    d = pd.read_csv(path)
    d = d[d["Series Code"].isin(WDI_INDICATORS)].copy()
    years = [c for c in d.columns if "[YR" in c]
    long = d.melt(id_vars=["Country Name", "Country Code", "Series Code"], value_vars=years, var_name="y", value_name="value")
    long["year"] = long.y.str.extract(r"(\d{4})").astype(int)
    long["value"] = pd.to_numeric(long.value.replace("..", None), errors="coerce")
    long = long.dropna(subset=["value"])
    long["indicator"] = long["Series Code"].map(WDI_INDICATORS)
    long["code"] = long["Country Code"]
    long["source"] = "World Bank WDI"
    return long[["source", "code", "indicator", "year", "value"]], d[["Country Name", "Country Code"]].drop_duplicates()
