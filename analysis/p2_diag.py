"""12-Nov diagnostic firmware: eight conditions, ONE run each, last 1024 events.

Everything here is descriptive.  No between-condition p-values are computed:
there is one run per cell and the events inside it are serially dependent.
"""
import numpy as np, csv
from common import *

CONDS = {"cache50_on": ("eight", "on"), "cache50_off": ("eight", "off"),
         "cache100_on": ("sixteen", "on"), "cache100_off": ("sixteen", "off"),
         "stress1_warm": ("base", "warm"), "stress1_cold": ("base", "cold"),
         "stress5_warm": ("stress", "warm"), "stress5_cold": ("stress", "cold")}


def load(name):
    """Parse raw cycles from the serial transcript (not the host-converted CSV)."""
    txt = (DIAG / f"{name}_r01_serial.txt").read_text(errors="replace").splitlines()
    b = next(i for i, l in enumerate(txt) if l.startswith("BEGIN_SAMPLES"))
    meta = dict(kv.split("=") for kv in txt[b].split(",")[1:])
    e = next(i for i, l in enumerate(txt) if l.startswith("END_SAMPLES"))
    s = np.array([[int(x) for x in l.split(",")] for l in txt[b + 2:e]], dtype=np.int64)
    b2 = next(i for i, l in enumerate(txt) if l.startswith("BEGIN_DIAG"))
    meta2 = dict(kv.split("=") for kv in txt[b2].split(",")[1:])
    e2 = next(i for i, l in enumerate(txt) if l.startswith("END_DIAG"))
    d = np.array([[int(x) for x in l.split(",")] for l in txt[b2 + 2:e2]], dtype=np.int64)
    assert (s[:, 0] == d[:, 0]).all(), "sample/diag index mismatch"
    assert (np.diff(s[:, 0]) == 1).all(), "non-contiguous index"
    meta.update({"flush_enabled": int(meta2["flush_enabled"])})
    return meta, {"idx": s[:, 0], "period": s[:, 2] / CPU_MHZ, "lat": s[:, 3] / CPU_MHZ, "load": s[:, 4] / CPU_MHZ,
                  "flush": d[:, 1] / CPU_MHZ, "cb": d[:, 2] / CPU_MHZ, "isr_flush": d[:, 3], "isr_load": d[:, 4],
                  "depth": d[:, 5]}


R = {}
for name, (a, b) in CONDS.items():
    meta, d = load(name)
    per = d["period"]; aj = np.abs(per - NOMINAL_US)
    no = d["isr_load"] == 0
    r = {"total": int(meta["total"]), "retained": int(meta["retained"]), "dropped": int(meta["dropped"]),
         "cache_mode": int(meta["cache_mode"]), "stress_priority": int(meta["stress_priority"]),
         "flush_enabled": meta["flush_enabled"], "n": int(len(per)),
         "period": dist(per), "absjit": dist(aj), "lat": dist(d["lat"]), "load": dist(d["load"]),
         "flush": dist(d["flush"]), "cb": dist(d["cb"]),
         "load_noisr": dist(d["load"][no]), "load_isr": dist(d["load"][~no]),
         "n_isr_load": int((~no).sum()), "frac_isr_load": float((~no).mean()),
         "n_isr_flush": int((d["isr_flush"] > 0).sum()),
         "flush_noisr": dist(d["flush"][d["isr_flush"] == 0]),
         "depth_nonzero": float((d["depth"] > 0).mean()), "depth_max": int(d["depth"].max()),
         "lat_gt50": float((d["lat"] > 50).mean()), "lat_lt10": float((d["lat"] < 10).mean()),
         "n_lt10": int((d["lat"] < 10).sum()),
         "lt10_depth_nonzero": int(((d["lat"] < 10) & (d["depth"] > 0)).sum()),
         "window_ms": float(per.sum() / 1000.0)}
    A = acf(per, 25); L = acf(d["lat"], 25)
    r["period_acf"] = {f"lag{k}": float(A[k]) for k in (1, 2, 3, 6, 20)}
    r["lat_acf"] = {f"lag{k}": float(L[k]) for k in (1, 3, 20)}
    # dominant short cycle: most common repeating triple of period values
    q = np.round(per, 2)
    tri = {}
    for i in range(len(q) - 5):
        if (q[i:i + 3] == q[i + 3:i + 6]).all():
            key = tuple(sorted(q[i:i + 3])); tri[key] = tri.get(key, 0) + 1
    if tri:
        k = max(tri, key=tri.get)
        r["cycle3"] = {"values": [float(x) for x in k], "count": int(tri[k]), "sum": float(sum(k)),
                       "frac_events_in_any_3cycle": float(sum(tri.values()) / len(q))}
    depth_rows = []
    for dep in range(0, 6):
        m = d["depth"] == dep
        if m.sum():
            x = d["lat"][m]
            depth_rows.append({"depth": dep, "n": int(m.sum()), "mean": float(x.mean()),
                               "sd": float(x.std(ddof=1)) if m.sum() > 1 else 0.0,
                               "p05": float(np.percentile(x, 5)), "p50": float(np.median(x)),
                               "p95": float(np.percentile(x, 95)), "min": float(x.min()), "max": float(x.max())})
    r["by_depth"] = depth_rows
    R[name] = r
    if a == "stress":
        write_dat(f"depth_{b}.dat", ["depth", "n", "mean", "sd", "p05", "p50", "p95"],
                  [(x["depth"], x["n"], x["mean"], x["sd"], x["p05"], x["p50"], x["p95"]) for x in depth_rows])
    if a in ("eight", "sixteen"):
        write_dat(f"cycle_{name}.dat", ["i", "period", "lat", "load"],
                  [(i, float(per[100 + i]), float(d["lat"][100 + i]), float(d["load"][100 + i])) for i in range(48)])
        write_dat(f"load_ecdf_{name}.dat", ["x", "p"], ecdf_points(d["load"][no], 120))

# Expected overlap if ISR phase were uniform over the 50 us period
for name in ("cache50_on", "cache50_off", "cache100_on", "cache100_off"):
    R[name]["overlap_if_uniform"] = R[name]["load_noisr"]["mean"] / 50.05
# flush ON/OFF contrasts (descriptive, one run per cell)
C = {}
for pat, on, off in (("eight", "cache50_on", "cache50_off"), ("sixteen", "cache100_on", "cache100_off")):
    C[pat] = {"absjit_on": R[on]["absjit"]["mean"], "absjit_off": R[off]["absjit"]["mean"],
              "absjit_reduction_pct": 100 * (1 - R[off]["absjit"]["mean"] / R[on]["absjit"]["mean"]),
              "load_noisr_on": R[on]["load_noisr"]["mean"], "load_noisr_off": R[off]["load_noisr"]["mean"],
              "load_noisr_diff": R[off]["load_noisr"]["mean"] - R[on]["load_noisr"]["mean"],
              "load_noisr_diff_cycles": (R[off]["load_noisr"]["mean"] - R[on]["load_noisr"]["mean"]) * CPU_MHZ,
              "cb_on": R[on]["cb"]["mean"], "cb_off": R[off]["cb"]["mean"],
              "flush_on": R[on]["flush"]["mean"], "flush_off": R[off]["flush"]["mean"]}
R["contrast"] = C
write_dat("flush_toggle.dat", ["pat", "absjit_on", "absjit_off", "load_on", "load_off", "cb_on", "cb_off"],
          [(1, C["eight"]["absjit_on"], C["eight"]["absjit_off"], C["eight"]["load_noisr_on"], C["eight"]["load_noisr_off"], C["eight"]["cb_on"], C["eight"]["cb_off"]),
           (2, C["sixteen"]["absjit_on"], C["sixteen"]["absjit_off"], C["sixteen"]["load_noisr_on"], C["sixteen"]["load_noisr_off"], C["sixteen"]["cb_on"], C["sixteen"]["cb_off"])])
save_results("diag", R)

for name in CONDS:
    r = R[name]
    print(f"{name:13s} tot={r['total']} ret={r['retained']} fl={r['flush_enabled']} per {r['period']['mean']:.3f}+/-{r['period']['sd']:.3f} absj {r['absjit']['mean']:.3f} lat {r['lat']['mean']:.3f}+/-{r['lat']['sd']:.3f} "
          f"load {r['load']['mean']:.3f} noisr {r['load_noisr']['mean']:.3f}(n={r['load_noisr']['n']}) isr {r['load_isr'].get('mean',float('nan')):.3f}(n={r['n_isr_load']}) flush {r['flush']['mean']:.3f} cb {r['cb']['mean']:.3f} "
          f"depth>0 {100*r['depth_nonzero']:.1f}% <10us {r['n_lt10']} (depth>0 among them {r['lt10_depth_nonzero']}) isr_flush {r['n_isr_flush']} acf3 {r['period_acf']['lag3']:.2f} acf20 {r['period_acf']['lag20']:.2f} cyc {r.get('cycle3')}")
for name in ("stress5_warm", "stress5_cold"):
    print(name, [(x["depth"], x["n"], round(x["mean"], 2), round(x["sd"], 2)) for x in R[name]["by_depth"]])
print(C)

# ---- "already running" path: an event whose handler entry fell inside the previous callback's load
# is served as soon as that callback returns, without a wake-up.
R2 = json.loads((RES / "diag.json").read_text()) if False else R
import json as _json
for name in ("cache100_on", "cache50_on", "cache100_off", "stress1_cold"):
    meta, d = load(name)
    prev_ov = np.concatenate([[False], d["isr_load"][:-1] > 0])
    floor = 12.9
    r = R[name]
    r["fastpath"] = {"n_prev_overlap": int(prev_ov.sum()),
                     "lat_prev_overlap": dist(d["lat"][prev_ov]), "lat_prev_clear": dist(d["lat"][~prev_ov]),
                     "frac_below_floor_prev_overlap": float((d["lat"][prev_ov] < floor).mean()) if prev_ov.any() else None,
                     "frac_below_floor_prev_clear": float((d["lat"][~prev_ov] < floor).mean()),
                     "n_lt10_prev_overlap": int(((d["lat"] < 10) & prev_ov).sum()), "n_lt10_prev_clear": int(((d["lat"] < 10) & ~prev_ov).sum())}
    print(name, r["fastpath"]["n_prev_overlap"], round(r["fastpath"]["lat_prev_overlap"].get("mean", 0), 2), round(r["fastpath"]["lat_prev_clear"]["mean"], 2),
          r["fastpath"]["frac_below_floor_prev_overlap"], r["fastpath"]["frac_below_floor_prev_clear"], r["fastpath"]["n_lt10_prev_overlap"], r["fastpath"]["n_lt10_prev_clear"])
save_results("diag", R)
