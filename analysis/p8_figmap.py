"""validation/FIGURE_SOURCE_MAP.csv: figure/table -> number, page, evidence tag, data files, script, raw source."""
import re, csv, glob, pathlib
from common import *
REPORT = WORK / "report"
aux = (REPORT / "main.aux").read_text()
labels = {m.group(1): (m.group(2), m.group(3)) for m in re.finditer(r"\\newlabel\{((?:fig|tab):[^}]+)\}\{\{([^}]*)\}\{([^}]*)\}", aux)}
scripts = {p.name: p.read_text() for p in (WORK / "analysis").glob("p*.py")}
RAW = {"p1_preflight.py": "data/raw_original/preflight_10nov (S1)", "p2_diag.py": "data/raw_diagnostic/diagnostic_serial_12nov (S4)",
       "p3_analyzer.py": "data/raw_analyzer/zeroplus_11nov, zeroplus_12nov (S2, S3)", "p4_figdata.py": "results of p1-p3 (S1-S4)",
       "p5_tables.py": "validation/*.csv"}
TAG = {"evM": "measured", "evD": "derived", "evH": "hypothesis", "evC": "conceptual"}
rows = []
for f in sorted(glob.glob(str(REPORT / "fig_*.tex"))) + sorted(glob.glob(str(REPORT / "ch*.tex"))) + [str(REPORT / "back.tex")]:
    t = pathlib.Path(f).read_text()
    for m in re.finditer(r"\\begin\{(figure|table|longtable)\}.*?\\end\{\1\}", t, flags=re.S):
        blk = m.group(0)
        lab = re.search(r"\\label\{((?:fig|tab):[^}]+)\}", blk)
        if not lab or lab.group(1) not in labels: continue
        tag = next((v for k, v in TAG.items() if "\\" + k in blk), "")
        dats = sorted(set(re.findall(r"\{([A-Za-z0-9_]+\.dat)\}", blk)) | set(x + ".tex" for x in re.findall(r"\\input\{((?:wf|tab)_[A-Za-z0-9_]+)\}", blk)))
        by = sorted({s for d in dats for s, src in scripts.items() if d.replace(".tex", "") in src or d in src})
        keys = len(set(re.findall(r"\\(?:V|Vn|us|ms|pct|cyc)(?:\[[^\]]*\])?\{([^}#]+)\}", blk)))
        num, page = labels[lab.group(1)]
        rows.append({"label": lab.group(1), "number": num, "page": page, "evidence_tag": tag, "source_file": pathlib.Path(f).name,
                     "data_files": "; ".join(dats), "written_by": "; ".join(by) or ("firmware source (drawn)" if tag == "conceptual" else "value macros (p9_emit.py)"),
                     "raw_source": "; ".join(sorted({RAW[b] for b in by if b in RAW})), "value_macros": keys})
rows.sort(key=lambda r: (r["label"].split(":")[0], [int(x) if x.isdigit() else ord(x[0]) + 100 for x in r["number"].split(".")]))
with open(VALID / "FIGURE_SOURCE_MAP.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(len(rows), "figures and tables mapped;", sum(r["label"].startswith("fig") for r in rows), "figures")
