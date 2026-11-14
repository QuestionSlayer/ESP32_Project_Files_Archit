"""Verify every raw input used by the pipeline against the handoff's SHA-256 manifest."""
import csv, json
from common import *
man = {r["relative_path"]: r["sha256"] for r in csv.DictReader(open(HANDOFF / "MANIFEST_SHA256.csv"))}
used = [p for root in (PRE, DIAG, ALC11, ALC12) for p in sorted(root.rglob("*")) if p.is_file()] + [FW_ORIG, FW_DIAG]
rows = []
for p in used:
    rel = str(p.relative_to(HANDOFF)); h = sha256(p)
    rows.append({"path": rel, "bytes": p.stat().st_size, "sha256": h,
                 "in_handoff_manifest": rel in man, "matches": man.get(rel) == h})
summary = {"files": len(rows), "listed": sum(r["in_handoff_manifest"] for r in rows),
           "matching": sum(r["matches"] for r in rows),
           "not_listed": [r["path"] for r in rows if not r["in_handoff_manifest"]][:20],
           "mismatched": [r["path"] for r in rows if r["in_handoff_manifest"] and not r["matches"]]}
(VALID / "input_manifest.json").write_text(json.dumps({"summary": summary, "files": rows}, indent=1))
print(summary)
