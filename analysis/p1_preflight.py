"""Original on-chip preflight (10 Nov 2026): timer/scheduling/cache/transfer.

Unit of replication: the RUN (one serial trial).  Events inside a run are
serially dependent; event-level SDs are descriptive only.
"""
import re, json, csv
import numpy as np
from common import *

rng = np.random.default_rng(20261112)
TESTS = {"stress1": "baseline", "stress5": "stress", "cache_warm": "warm",
         "cache12": "two", "cache50": "eight", "cache100": "sixteen"}


def parse_serial(path):
    """Return (meta, int array [index, entry, period, latency, work]) from raw cycles."""
    txt = path.read_text(errors="replace").splitlines()
    try:
        b = next(i for i, l in enumerate(txt) if l.startswith("BEGIN_SAMPLES"))
    except StopIteration:
        return None, None
    meta = dict(kv.split("=") for kv in txt[b].split(",")[1:])
    rows = []
    complete = False
    for l in txt[b + 2:]:
        if l.startswith("END_SAMPLES"):
            complete = True
            break
        p = l.split(",")
        if len(p) == 5 and all(s.strip().isdigit() for s in p):
            rows.append([int(s) for s in p])
    meta["complete"] = complete
    return meta, np.array(rows, dtype=np.int64)


runs = {}          # (test, rep) -> dict of arrays in microseconds
acceptance = []
for test in TESTS:
    for rep in range(1, 11):
        f = PRE / f"{test}_{rep:03d}_serial.txt"
        meta, a = parse_serial(f)
        reason = ""
        if a is None or len(a) == 0:
            reason = "no sample block"
        else:
            retained = int(meta["retained"])
            if len(a) != retained:
                reason = f"incomplete export: {len(a)} of {retained} rows"
            elif not (np.diff(a[:, 0]) == 1).all():
                reason = "non-contiguous sample index"
            elif int(meta["dropped"]) != 0:
                reason = f"ring overflow: dropped={meta['dropped']}"
        acceptance.append({"test": test, "repeat": rep, "file": f.name, "rows": 0 if a is None else len(a),
                           "retained": None if meta is None else int(meta["retained"]),
                           "cache_mode": None if meta is None else int(meta["cache_mode"]),
                           "stress_priority": None if meta is None else int(meta["stress_priority"]),
                           "accepted": reason == "", "reason": reason})
        if reason:
            continue
        per = a[:, 2].astype(float) / CPU_MHZ
        runs[(test, rep)] = {
            "entry": a[:, 1], "period": per, "valid": a[:, 2] != 0,
            "lat": a[:, 3] / CPU_MHZ, "work": a[:, 4] / CPU_MHZ,
            "lat_cyc": a[:, 3], "work_cyc": a[:, 4],
        }

with open(VALID / "run_acceptance.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(acceptance[0].keys()))
    w.writeheader(); w.writerows(acceptance)
with open(VALID / "excluded_runs.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(acceptance[0].keys()))
    w.writeheader(); w.writerows([r for r in acceptance if not r["accepted"]])

R = {"n_attempted": 110, "timer_runs_accepted": len(runs),
     "timer_runs_attempted": len(acceptance),
     "timer_events": int(sum(len(r["lat"]) for r in runs.values()))}


def pooled(test, key, only_valid=False):
    out = []
    for (t, rep), r in runs.items():
        if t == test:
            out.append(r[key][r["valid"]] if only_valid else r[key])
    return np.concatenate(out)


def per_run(test, fn):
    return np.array([fn(r) for (t, rep), r in sorted(runs.items()) if t == test])


def boot_ci(a, b, stat, n=20000):
    """Percentile bootstrap over RUNS for stat(a_runs, b_runs)."""
    a = np.asarray(a); b = np.asarray(b)
    ia = rng.integers(0, len(a), (n, len(a))); ib = rng.integers(0, len(b), (n, len(b)))
    s = np.array([stat(a[i], b[j]) for i, j in zip(ia, ib)])
    return float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))


# ---------------------------------------------------------------- scheduling
for test, tag in TESTS.items():
    per = pooled(test, "period", only_valid=True)
    lat = pooled(test, "lat"); work = pooled(test, "work")
    d = {"runs": int(sum(1 for k in runs if k[0] == test)), "events": int(len(lat)),
         "period": dist(per), "absjit": dist(np.abs(per - NOMINAL_US)),
         "sjit": dist(per - NOMINAL_US), "lat": dist(lat), "work": dist(work),
         "lat_gt50": float((lat > 50).mean()), "lat_lt10": float((lat < 10).mean())}
    # backlog proxy: next ISR entry precedes this event's dispatch
    bl = []
    for (t, rep), r in runs.items():
        if t != test: continue
        e = r["entry"].astype(np.int64)
        de = np.diff(e) % (1 << 32)
        bl.append(de < r["lat_cyc"][:-1])
    d["next_isr_before_dispatch"] = float(np.concatenate(bl).mean())
    # run-level summaries
    d["run_lat_mean"] = per_run(test, lambda r: r["lat"].mean()).tolist()
    d["run_lat_p99"] = per_run(test, lambda r: np.percentile(r["lat"], 99)).tolist()
    d["run_gt50"] = per_run(test, lambda r: (r["lat"] > 50).mean()).tolist()
    d["run_absjit"] = per_run(test, lambda r: np.abs(r["period"][r["valid"]] - NOMINAL_US).mean()).tolist()
    d["run_period_mean"] = per_run(test, lambda r: r["period"][r["valid"]].mean()).tolist()
    d["run_period_sd"] = per_run(test, lambda r: r["period"][r["valid"]].std(ddof=1)).tolist()
    d["run_work_mean"] = per_run(test, lambda r: r["work"].mean()).tolist()
    d["run_n"] = per_run(test, lambda r: len(r["lat"])).tolist()
    R[tag] = d

B, S = R["baseline"], R["stress"]
cmp = {}
for key, lab in [("run_lat_mean", "lat_mean"), ("run_lat_p99", "lat_p99"), ("run_gt50", "gt50"),
                 ("run_absjit", "absjit"), ("run_period_sd", "period_sd"), ("run_period_mean", "period_mean")]:
    a = np.array(S[key]); b = np.array(B[key])
    lo, hi = boot_ci(a, b, lambda x, y: x.mean() - y.mean())
    c = {"base_mean": float(b.mean()), "base_min": float(b.min()), "base_max": float(b.max()),
         "stress_mean": float(a.mean()), "stress_min": float(a.min()), "stress_max": float(a.max()),
         "diff": float(a.mean() - b.mean()), "diff_lo": lo, "diff_hi": hi,
         "separated": bool(a.min() > b.max() or a.max() < b.min())}
    if b.mean() > 0 and key not in ("run_gt50",):
        rl, rh = boot_ci(a, b, lambda x, y: x.mean() / y.mean())
        c.update({"ratio": float(a.mean() / b.mean()), "ratio_lo": rl, "ratio_hi": rh})
    cmp[lab] = c
# exact permutation p for complete separation of 10 vs 10 runs (two-sided), reported once
from math import comb
cmp["perm_p_complete_separation"] = 2.0 / comb(20, 10)
R["cmp"] = cmp

# Timer period in cycles: the modal value and what it implies
allper = np.concatenate([r["period"][r["valid"]] for (t, rep), r in runs.items() if t == "stress1"]) * CPU_MHZ
vals, cnts = np.unique(np.round(allper).astype(int), return_counts=True)
R["period_mode_cycles"] = int(vals[cnts.argmax()]); R["period_mode_frac"] = float(cnts.max() / cnts.sum())

# histogram of ISR period (fraction of events per 0.25 us bin)
edges = np.arange(40.0, 60.0001, 0.25)
hb, _ = np.histogram(pooled("stress1", "period", True), edges)
hs, _ = np.histogram(pooled("stress5", "period", True), edges)
write_dat("period_hist.dat", ["x", "base", "stress"],
          [(float(edges[i]), max(hb[i] / hb.sum(), 1e-6), max(hs[i] / hs.sum(), 1e-6)) for i in range(len(hb))] +
          [(float(edges[-1]), 1e-6, 1e-6)])
R["period_hist_outside"] = {"base": float(1 - hb.sum() / len(pooled("stress1", "period", True))),
                            "stress": float(1 - hs.sum() / len(pooled("stress5", "period", True)))}
for test, tag in TESTS.items():
    write_dat(f"lat_ecdf_{tag}.dat", ["x", "p"], ecdf_points(pooled(test, "lat")))
    write_dat(f"work_ecdf_{tag}.dat", ["x", "p"], ecdf_points(pooled(test, "work")))

# run-level dot data
rows = []
for test, tag in (("stress1", "baseline"), ("stress5", "stress")):
    d = R[tag]
    for i in range(len(d["run_lat_mean"])):
        rows.append((tag, i + 1, d["run_n"][i], d["run_lat_mean"][i], d["run_lat_p99"][i], 100 * d["run_gt50"][i],
                     d["run_absjit"][i], d["run_period_sd"][i]))
write_dat("run_level.dat", ["cond", "rep", "n", "latmean", "latp99", "gt50", "absjit", "persd"], rows)

# ------------------------------------------------------------ determinism
def identical_fraction(test):
    ks = sorted(k for k in runs if k[0] == test)
    out = []
    for i in range(len(ks)):
        for j in range(i + 1, len(ks)):
            a = runs[ks[i]]["lat_cyc"]; b = runs[ks[j]]["lat_cyc"]
            n = min(len(a), len(b), 1000)
            out.append(float((a[:n] == b[:n]).mean()))
    return np.array(out)
for test, tag in (("stress1", "baseline"), ("stress5", "stress"), ("cache100", "sixteen")):
    f = identical_fraction(test)
    R[tag]["pair_identity"] = {"pairs": int(len(f)), "median": float(np.median(f)), "max": float(f.max()),
                               "min": float(f.min()), "n_gt90": int((f > 0.9).sum())}

# ------------------------------------------------------------ autocorrelation
ML = 45
def mean_acf(test, key, valid=False):
    out = []
    for (t, rep), r in sorted(runs.items()):
        if t != test: continue
        x = r[key][r["valid"]] if valid else r[key]
        out.append(acf(x, ML))
    return np.array(out)
A = {"base_lat": mean_acf("stress1", "lat"), "base_per": mean_acf("stress1", "period", True),
     "stress_lat": mean_acf("stress5", "lat"), "warm_lat": mean_acf("cache_warm", "lat"),
     "stress_per": mean_acf("stress5", "period", True)}
write_dat("acf.dat", ["lag", "base_lat", "base_lat_lo", "base_lat_hi", "base_per", "stress_lat"],
          [(k, A["base_lat"][:, k].mean(), A["base_lat"][:, k].min(), A["base_lat"][:, k].max(),
            A["base_per"][:, k].mean(), A["stress_lat"][:, k].mean()) for k in range(ML + 1)])
R["acf"] = {name: {"lag1": float(a[:, 1].mean()), "lag19": float(a[:, 19].mean()), "lag20": float(a[:, 20].mean()),
                   "lag21": float(a[:, 21].mean()), "lag20_min": float(a[:, 20].min()), "lag20_max": float(a[:, 20].max()),
                   "lag40": float(a[:, 40].mean())} for name, a in A.items()}
# pooled-concatenation version (what the project log quoted)
R["acf"]["base_lat_pooled_lag20"] = float(acf(pooled("stress1", "lat"), 21)[20])
R["acf"]["white_noise_band"] = float(1.96 / np.sqrt(np.median(R["baseline"]["run_n"])))

# ------------------------------------------------------------ 1 ms interferer
# Baseline latency has a floor near 13 us; events above 17 us recur every 20
# events.  A LUT-locked cause keeps (index mod 20) fixed for ever; a cause with
# period P != 20*T_isr slides through the grid and shifts the residue.
tick = {"runs": []}
rows = []
for (t, rep), r in sorted(runs.items()):
    if t != "stress1": continue
    lat = r["lat"]; idx = np.nonzero(lat > 17.0)[0]
    e = r["entry"].astype(np.int64); tt = np.concatenate([[0], np.cumsum(np.diff(e) % (1 << 32))]) / CPU_MHZ
    res = idx % 20
    # contiguous stretches of equal residue
    st = []; s0 = 0
    for i in range(1, len(idx) + 1):
        if i == len(idx) or res[i] != res[s0] or idx[i] - idx[i - 1] != 20:
            if i - s0 >= 5:
                st.append((int(res[s0]), int(i - s0), float(tt[idx[s0]]), float(tt[idx[i - 1]])))
            s0 = i
    tick["runs"].append({"rep": rep, "n_high": int(len(idx)), "residues": sorted(set(int(x) for x in res)),
                         "stretches": st})
    if rep == 2:
        for i in idx:
            rows.append((tt[i] / 1000.0, int(i % 20), lat[i]))
        write_dat("tick_run2_all.dat", ["t_ms", "lat"], [(tt[i] / 1000.0, lat[i]) for i in range(len(lat))])
write_dat("tick_run2.dat", ["t_ms", "res", "lat"], rows)
# period of the interferer from pairs of stretches whose residue differs by -1 (same source, one grid step later)
Tisr = float(np.mean(R["baseline"]["run_period_mean"]))
est = []
for rr in tick["runs"]:
    st = rr["stretches"]
    for i in range(len(st)):
        for j in range(i + 1, len(st)):
            if (st[i][0] - st[j][0]) % 20 == 1 and abs(st[i][1] - st[j][1]) <= 3:
                dn = (st[j][2] - st[i][2]) / (20 * Tisr)      # occurrences between stretch starts
                est.append(20 * Tisr - Tisr / dn)
tick["Tisr"] = Tisr; tick["lut_period_us"] = 20 * Tisr
tick["interferer_period_estimates"] = est
tick["interferer_period_mean"] = float(np.mean(est)) if est else None
tick["interferer_period_sd"] = float(np.std(est, ddof=1)) if len(est) > 1 else None
tick["n_estimates"] = len(est)
tick["runs_with_residue_shift"] = int(sum(1 for rr in tick["runs"] if len(set(s[0] for s in rr["stretches"])) > 1))
tick["stretch_lengths"] = sorted(s[1] for rr in tick["runs"] for s in rr["stretches"])
R["tick"] = tick

# ------------------------------------------------------------ cache modes
warm_first = runs[("cache_warm", 1)]["work"]
R["warm_startup"] = {"n_initial_slow": int((warm_first[:40] > 5).sum()), "initial_value": float(warm_first[0]),
                     "steady_value": float(np.median(warm_first[100:]))}
for tag, test in (("eight", "cache50"), ("sixteen", "cache100"), ("two", "cache12"), ("warm", "cache_warm")):
    w = pooled(test, "work")
    v, c = np.unique(np.round(w * CPU_MHZ).astype(int), return_counts=True)
    order = np.argsort(-c)[:3]
    R[tag]["work_modes"] = [{"us": float(v[i] / CPU_MHZ), "frac": float(c[i] / c.sum())} for i in order]
w16 = pooled("cache100", "work")
R["sixteen"]["work_short"] = dist(w16[w16 < 24]); R["sixteen"]["work_long"] = dist(w16[w16 >= 24])
R["sixteen"]["work_long_frac"] = float((w16 >= 24).mean())
w8 = pooled("cache50", "work"); R["eight"]["work_long_frac"] = float((w8 >= 14).mean())
R["eight"]["work_short"] = dist(w8[w8 < 14])
# work vs period correlation (exploratory, mechanically confounded)
cc = []; cn = []
for (t, rep), r in sorted(runs.items()):
    if t != "cache100": continue
    v = r["valid"]; w = r["work"]; p = r["period"]
    cc.append(np.corrcoef(w[v], p[v])[0, 1]); cn.append(np.corrcoef(w[:-1][v[1:]], p[1:][v[1:]])[0, 1])
R["sixteen"]["corr_work_period_same"] = float(np.mean(cc)); R["sixteen"]["corr_work_period_next"] = float(np.mean(cn))
# lag-3 structure in the cold modes
for tag, test in (("eight", "cache50"), ("sixteen", "cache100")):
    a = mean_acf(test, "period", True)
    R[tag]["period_acf"] = {"lag1": float(a[:, 1].mean()), "lag2": float(a[:, 2].mean()), "lag3": float(a[:, 3].mean()),
                            "lag20": float(a[:, 20].mean())}
rows = [(lines, R[tag]["work"]["mean"], R[tag]["work"]["sd"], R[tag]["work"]["p50"], R[tag]["work"]["p99"])
        for lines, tag in ((0, "warm"), (2, "two"), (8, "eight"), (16, "sixteen"))]
write_dat("cache_modes.dat", ["lines", "mean", "sd", "p50", "p99"], rows)

# ------------------------------------------------------------ transfers
tr = list(csv.DictReader(open(PRE / "transfer_trials.csv")))
poll = [float(r["wall_us"]) for r in tr if r["test"] == "poll"]
intr = [r for r in tr if r["test"] == "interrupt"]
dma = [r for r in tr if r["test"] == "dma"]
spill = [r for r in tr if r["test"] == "spill"]
polls = sorted(int(m.group(1)) for f in sorted(PRE.glob("poll_*_serial.txt"))
               for m in [re.search(r"status-register polls : (\d+)", f.read_text())] if m)
burst = sorted(set(int(m.group(1)) for f in PRE.glob("interrupt_*_serial.txt")
                   for m in [re.search(r"burst=(\d+) B/IRQ", f.read_text())] if m))
R["poll"] = {"n": len(poll), "wall": dist(poll), "walls": poll, "polls_min": polls[0], "polls_max": polls[-1],
             "shortfall_us": [5120.0 - p for p in poll],
             "implied_frames": [int(p // 10) for p in poll]}
R["intr16"] = {"n": len(intr), "burst_bytes": burst, "wall": dist([float(r["wall_us"]) for r in intr]),
               "walls": sorted(set(float(r["wall_us"]) for r in intr)),
               "isr_work": dist([float(r["isr_work_us"]) for r in intr]),
               "count": sorted(set(int(float(r["interrupt_count"])) for r in intr))}
q = np.array([float(r["queue_cpu_us"]) for r in dma]); wl = np.array([float(r["wall_us"]) for r in dma])
R["dma_pre"] = {"n": len(dma), "n_pass": int(sum(r["pass"] == "True" for r in dma)),
                "queue_first": float(q[0]), "queue_rest": dist(q[1:]), "wall_first": float(wl[0]), "wall_rest": dist(wl[1:]),
                "isr": dist([float(r["isr_cpu_us"]) for r in dma]),
                "mismatch_min": int(min(float(r["mismatched_bytes"]) for r in dma)),
                "mismatch_max": int(max(float(r["mismatched_bytes"]) for r in dma))}
write_dat("dma_preflight.dat", ["trial", "queue", "wall"], [(i + 1, q[i], wl[i]) for i in range(len(q))])
R["spill"] = {"n": len(spill),
              "resident": sorted(set(int(float(r["spill_resident_cycles"])) for r in spill)),
              "forced": sorted(set(int(float(r["spill_forced_cycles"])) for r in spill)),
              "deep": sorted(set(int(float(r["spill_deep_cycles"])) for r in spill))}
man = json.loads((PRE / "manifest.json").read_text())
R["manifest"] = {"started_utc": man["started_utc"], "finished_utc": man["finished_utc"],
                 "duration_s": man["duration_s"], "completed_trials": man["completed_trials"]}
R["all_timer_samples_rows"] = sum(1 for _ in open(PRE / "all_timer_samples.csv")) - 1
save_results("preflight", R)

print("accepted timer runs", R["timer_runs_accepted"], "events", R["timer_events"], "| csv rows", R["all_timer_samples_rows"])
for tag in ("baseline", "stress", "warm", "two", "eight", "sixteen"):
    d = R[tag]
    print(f"{tag:9s} runs={d['runs']} n={d['events']} period {d['period']['mean']:.3f}+/-{d['period']['sd']:.3f} absjit {d['absjit']['mean']:.3f} (p99 {d['absjit']['p99']:.2f}) "
          f"lat {d['lat']['mean']:.3f}+/-{d['lat']['sd']:.3f} p95 {d['lat']['p95']:.3f} p99 {d['lat']['p99']:.3f} >50 {100*d['lat_gt50']:.2f}% <10 {100*d['lat_lt10']:.2f}% "
          f"work {d['work']['mean']:.3f}+/-{d['work']['sd']:.3f} p99 {d['work']['p99']:.3f} backlog {100*d['next_isr_before_dispatch']:.2f}%")
print("cmp", json.dumps({k: {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()} if isinstance(v, dict) else v for k, v in cmp.items()}))
print("acf", {k: (round(v["lag20"], 3) if isinstance(v, dict) else round(v, 3)) for k, v in R["acf"].items()})
print("period mode", R["period_mode_cycles"], R["period_mode_frac"])
print("identity", R["baseline"]["pair_identity"], R["stress"]["pair_identity"], R["sixteen"]["pair_identity"])
print("tick", {k: v for k, v in tick.items() if k != "runs"})
for rr in tick["runs"]: print("   ", rr["rep"], rr["n_high"], rr["stretches"])
print("16-line", R["sixteen"]["work_modes"], R["sixteen"]["work_long_frac"], R["sixteen"]["work_short"]["mean"], R["sixteen"]["work_long"]["mean"], R["sixteen"]["corr_work_period_same"], R["sixteen"]["corr_work_period_next"], R["sixteen"]["period_acf"])
print("8-line", R["eight"]["work_modes"], R["eight"]["work_long_frac"], R["eight"]["period_acf"])
print("warm startup", R["warm_startup"]); print("poll", R["poll"]); print("intr", R["intr16"]); print("dma", R["dma_pre"]); print("spill", R["spill"])

# ------------------------------------------------------------ cold start of the warm window
# Same instruction sequence, cold on first touch: the first sweep of the 8 KiB
# resident window (256 lines, 16 per event) must miss on every load.
cs = []
for (t, rep), r in sorted(runs.items()):
    if t not in ("stress1", "stress5", "cache_warm"): continue
    w = r["work"]; n = 0
    while n < len(w) and w[n] > 5.0: n += 1
    if n: cs.append({"test": t, "rep": rep, "n_leading_slow": n, "slow_mean": float(w[:n].mean()),
                     "slow_min": float(w[:n].min()), "slow_max": float(w[:n].max()),
                     "after_median": float(np.median(w[n:n + 200]))})
R2 = json.loads((RES / "preflight.json").read_text())
R2["coldstart"] = cs
if cs:
    c = cs[0]
    R2["coldstart_per_line_us"] = (c["slow_mean"] - c["after_median"]) / 16.0
    R2["coldstart_per_line_cycles"] = R2["coldstart_per_line_us"] * CPU_MHZ
    T0 = c["after_median"]; k = R2["coldstart_per_line_us"]
    R2["linemodel"] = {"T0": T0, "k": k,
                       "pred": {"two": T0 + 2 * k, "eight": T0 + 8 * k, "sixteen": T0 + 16 * k},
                       "obs": {"two": R2["two"]["work_modes"][0]["us"], "eight": R2["eight"]["work_modes"][0]["us"],
                               "sixteen": R2["sixteen"]["work_modes"][0]["us"]}}
    r = runs[(c["test"], c["rep"])]
    write_dat("coldstart.dat", ["i", "work"], [(i, float(r["work"][i])) for i in range(40)])
save_results("preflight", R2)
print("coldstart", cs, R2.get("linemodel"))

# ------------------------------------------------------------ yield-residual model for equal-priority stress
# Dispatch instant D_i = entry_i + latency_i.  Events served in one drain share
# (almost) one D; the spacing of successive drains is the worker's chunk time.
gaps = []; sizes = []
for (t, rep), r in sorted(runs.items()):
    if t != "stress5": continue
    e = r["entry"].astype(np.int64); tt = np.concatenate([[0], np.cumsum(np.diff(e) % (1 << 32))]) / CPU_MHZ
    D = tt + r["lat"]
    new = np.concatenate([[True], np.diff(D) > 12.0])
    starts = D[new]
    gaps.append(np.diff(starts)); sizes.append(np.diff(np.nonzero(np.concatenate([new, [True]]))[0]))
gaps = np.concatenate(gaps); sizes = np.concatenate(sizes)
lat = pooled("stress5", "lat")
a, b = np.percentile(lat, 0.5), np.percentile(lat, 99.5)
xs = np.sort(lat); F = (np.arange(1, len(xs) + 1)) / len(xs)
U = np.clip((xs - a) / (b - a), 0, 1)
R3 = json.loads((RES / "preflight.json").read_text())
R3["yieldmodel"] = {"drain_gap": dist(gaps), "drain_gap_mode": float(np.round(np.median(gaps), 2)),
                    "drain_gap_iqr": [float(np.percentile(gaps, 25)), float(np.percentile(gaps, 75))],
                    "drain_size_mean": float(sizes.mean()),
                    "drain_size_frac": {str(k): float((sizes == k).mean()) for k in range(1, 6)},
                    "uniform_a": float(a), "uniform_b": float(b),
                    "uniform_mean": float((a + b) / 2), "uniform_sd": float((b - a) / np.sqrt(12)),
                    "ks_distance_to_uniform": float(np.abs(F - U).max()),
                    "pred_gt50": float((b - 50) / (b - a)), "pred_lt10": float((10 - a) / (b - a))}
edges = np.arange(0, 200.01, 2.0); h, _ = np.histogram(gaps, edges)
write_dat("drain_gap_hist.dat", ["x", "frac"], [(float(edges[i]), float(h[i] / h.sum())) for i in range(len(h))] + [(200.0, 0.0)])
save_results("preflight", R3)
print("yield model", R3["yieldmodel"])
