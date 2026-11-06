"""Build the browser only version of the dashboard (stlite) into docs/.
Run from the repo root:  python web/build_web.py
Then serve docs/ with GitHub Pages (Settings > Pages > main branch > /docs)."""
import json, pathlib, shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs"
FILES = ["app.py", "src/__init__.py", "src/pbi_view.py", "src/briefing.py",
         "data/country_snapshot.csv", "data/country_series.csv", "data/world-110m.json",
         "eval/results_regressions.json", "eval/results_forecast.json",
         "eval/results_score.json", "eval/results_quality.json"]

if OUT.exists():
    shutil.rmtree(OUT)
for f in FILES:
    dst = OUT / "app" / f
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / f, dst)

files = {f: {"url": f"./app/{f}"} for f in FILES}
cfg = {"theme.primaryColor": "#118DFF", "theme.backgroundColor": "#F3F2F1",
       "theme.secondaryBackgroundColor": "#FFFFFF", "theme.textColor": "#252423"}
html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Global Macro Monitor</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@stlite/browser@1.12.0/build/stlite.css" />
</head>
<body>
  <div id="root"></div>
  <script type="module">
    import {{ mount }} from "https://cdn.jsdelivr.net/npm/@stlite/browser@1.12.0/build/stlite.js";
    mount({{
      entrypoint: "app.py",
      requirements: ["pandas", "numpy", "altair", "pydantic"],
      streamlitConfig: {json.dumps(cfg)},
      files: {json.dumps(files, indent=2)}
    }}, document.getElementById("root"));
  </script>
</body>
</html>
"""
(OUT / "index.html").write_text(html)
(OUT / ".nojekyll").write_text("")
print("built", OUT, sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file()) // 1024, "KB")
