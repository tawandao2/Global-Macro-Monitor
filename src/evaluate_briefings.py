"""Break clean briefings on purpose in known ways and count how many the checker catches."""
import json, re, sys
sys.path.insert(0, ".")
import pandas as pd
from src.briefing import build_findings, RulesOnlyWriter, Report, validate, run_briefing, NUM


def mutations(st, bundle):
    out = {}
    clone = lambda: json.loads(json.dumps(st))
    s = clone(); hit = False
    for x in s:
        m = re.search(r"\d+\.\d", x["text"])
        if m and not hit:
            x["text"] = x["text"].replace(m.group(0), f"{float(m.group(0)) + 7.3:.1f}", 1); hit = True
    if hit: out["changed a number"] = s
    s = clone(); hit = False
    for x in s:
        m = re.search(r"(?<![\w.])-(\d+\.\d)", x["text"])
        if m and not hit:
            x["text"] = x["text"].replace(m.group(0), m.group(1), 1); hit = True
    if hit: out["flipped a sign"] = s
    s = clone(); s[0]["text"] += " Roughly 4821 firms were surveyed."; out["invented number"] = s
    s = clone(); s[1 % len(s)]["text"] += " This weak performance is due to the government's policy."; out["causal wording"] = s
    s = clone(); s[-1]["finding_ids"] = ["made_up_id"]; out["invented finding id"] = s
    s = [x for x in clone() if x["finding_ids"] != ["tier"]]; out["dropped the tier"] = s
    s = [x for x in clone() if x["finding_ids"] != ["limits"]]; out["dropped the limits"] = s
    s = clone(); s[0]["finding_ids"] = []; out["no citation"] = s
    s = clone(); hit = False
    for x in s:
        if "projects" in x["text"]:
            x["text"] = x["text"].replace("The IMF projects", "The recorded figure was"); hit = True
    if hit: out["projection presented as recorded"] = s
    return out


def main(out="eval/results_briefings.json"):
    snap = pd.read_csv("data/country_snapshot.csv"); series = pd.read_csv("data/country_series.csv")
    sc = json.load(open("eval/results_score.json"))
    clean_ok, tried, caught, n = 0, {}, {}, 0
    for _, row in snap.iterrows():
        b = build_findings(row.to_dict(), series, snap, sc); n += 1
        r = run_briefing(b, RulesOnlyWriter())
        clean_ok += r["status"] == "ready"
        for name, st in mutations(r["statements"], b).items():
            tried[name] = tried.get(name, 0) + 1
            try:
                bad = bool(validate(Report.model_validate({"statements": st}), b))
            except Exception:
                bad = True
            caught[name] = caught.get(name, 0) + bad
    res = {"countries": n, "clean_briefings_passed": int(clean_ok), "mutations": {k: dict(tried=tried[k], caught=caught[k]) for k in tried},
           "total_tried": sum(tried.values()), "total_caught": sum(caught.values())}
    json.dump(res, open(out, "w"), indent=1); return res


if __name__ == "__main__":
    print(json.dumps(main(), indent=1))
