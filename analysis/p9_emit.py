"""Flatten build/results/*.json into LaTeX value macros (build/numbers.tex).

  \\V{pre.baseline.lat.mean}  -> full-precision value; rounding is done in LaTeX
                                by siunitx so that prose, tables and plots share
                                one source.  Only keys used by the report are
                                emitted when --prune <texfiles...> is given.
Also writes validation/claim_to_evidence.csv (key, value, result file, stage).
"""
import json, re, sys, csv
from common import *

STAGE = {"ri": ("readability.json", "readability.py", "report/ch01-ch11.tex (running prose)"),
         "xc": ("xcheck.json", "p4_figdata.py", "combination of the three sources (see result file)"),
         "pre": ("preflight.json", "p1_preflight.py", "data/raw_original/preflight_10nov (original firmware, on-chip)"),
         "diag": ("diag.json", "p2_diag.py", "data/raw_diagnostic/diagnostic_serial_12nov (diagnostic firmware, on-chip)"),
         "alc": ("analyzer.json", "p3_analyzer.py", "data/raw_analyzer/zeroplus_11nov|12nov (logic analyzer)")}


def flatten(prefix, obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten(f"{prefix}.{k}", v, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            flatten(f"{prefix}.{i}", v, out)
        out[f"{prefix}.len"] = len(obj)
    elif isinstance(obj, bool):
        out[prefix] = "yes" if obj else "no"
    elif isinstance(obj, int):
        out[prefix] = str(obj)
    elif isinstance(obj, float):
        out[prefix] = f"{obj:.6f}".rstrip("0").rstrip(".") if abs(obj) < 1e7 else f"{obj:.0f}"
        if 0.0 <= obj <= 1.0:
            out[prefix + ".pct"] = f"{100 * obj:.6f}".rstrip("0").rstrip(".")
    elif isinstance(obj, str):
        out[prefix] = obj.replace("_", r"\_").replace("%", r"\%")
    elif obj is None:
        pass


vals = {}; origin = {}
for pfx, (fn, script, src) in STAGE.items():
    o = {}
    flatten(pfx, json.loads((RES / fn).read_text()), o)
    for k, v in o.items():
        vals[k] = v; origin[k] = (fn, script, src)

# a few derived conveniences, each traceable to the keys it combines
def f(k): return float(vals[k])
def put(k, v, src): vals[k] = (f"{v:.6f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)); origin[k] = src
put("x.spill.forced_minus_resident", f("pre.spill.forced.0") - f("pre.spill.resident.0"), origin["pre.spill.forced.0"])
put("x.spill.forced_minus_resident_us", (f("pre.spill.forced.0") - f("pre.spill.resident.0")) / CPU_MHZ, origin["pre.spill.forced.0"])
put("x.spill.forced_ratio", f("pre.spill.forced.0") / f("pre.spill.resident.0"), origin["pre.spill.forced.0"])
put("x.spill.deep_ratio", f("pre.spill.deep.0") / f("pre.spill.resident.0"), origin["pre.spill.forced.0"])
for i, nm in enumerate(("resident", "deep", "forced")):
    put(f"x.spill.{nm}_us", f(f"pre.spill.{nm}.0") / CPU_MHZ, origin["pre.spill.forced.0"])
    put(f"x.spill.{nm}_batch_ms", f(f"pre.spill.{nm}.0") * 1000 / CPU_MHZ / 1000.0, origin["pre.spill.forced.0"])
    put(f"x.reg.width_ms.{i}", f(f"alc.reg.widths_us.{i}") / 1000.0, origin["alc.reg.widths_us.0"])
put("x.period.mode_us", f("pre.period_mode_cycles") / CPU_MHZ, origin["pre.period_mode_cycles"])
put("x.period.mode_timer_counts", f("pre.period_mode_cycles") / 4.0, origin["pre.period_mode_cycles"])
put("x.uart.isr_reduction_pct", 100 * (1 - f("alc.uart.120.a2_sum_us") / f("alc.uart.8.a2_sum_us")), origin["alc.uart.8.a2_sum_us"])
put("x.dac.lat_mean_ms", f("alc.dac.lat11.mean_us") / 1000.0, origin["alc.dac.lat11.mean_us"])
put("x.dac.persist_ms", f("alc.dac.stall11.events.0.persist_us") / 1000.0, origin["alc.dac.stall11.events.0.persist_us"])
put("x.dac.silent_ms", f("alc.dac.stall11.events.0.silent_us") / 1000.0, origin["alc.dac.stall11.events.0.silent_us"])
put("x.dac.stall_ms", f("alc.dac.stall11.events.0.stall_us") / 1000.0, origin["alc.dac.stall11.events.0.stall_us"])
put("x.poll.mean_shortfall", 5120.0 - f("pre.poll.wall.mean"), origin["pre.poll.wall.mean"])
put("x.diag.window_ms", f("diag.stress1_warm.window_ms"), origin["diag.stress1_warm.window_ms"])
sf = [f(f"pre.poll.shortfall_us.{i}") for i in range(10)]
put("x.poll.shortfall_min", min(sf), origin["pre.poll.wall.mean"]); put("x.poll.shortfall_max", max(sf), origin["pre.poll.wall.mean"])
put("x.poll.n_two_bytes", sum(1 for v in sf if 18.5 < v < 19.5), origin["pre.poll.wall.mean"])
put("x.ratio.s1", f("pre.stress.lat.mean") / f("pre.baseline.lat.mean"), origin["pre.stress.lat.mean"])
put("x.ratio.s2", f("alc.timer.hs01.lat.mean") / f("alc.timer.base01.lat.mean"), origin["alc.timer.hs01.lat.mean"])
put("x.ratio.s3", f("alc.timer.u5.lat.mean") / f("alc.timer.u1.lat.mean"), origin["alc.timer.u5.lat.mean"])
put("x.ratio.s4", f("diag.stress5_warm.lat.mean") / f("diag.stress1_warm.lat.mean"), origin["diag.stress5_warm.lat.mean"])
put("x.spill.shallow_per_call", f("alc.reg.cycles_per_iter.0") / 5.0, origin["alc.reg.widths_us.0"])
put("x.spill.deep_per_call", f("alc.reg.cycles_per_iter.1") / 25.0, origin["alc.reg.widths_us.0"])
put("x.spill.deep_excess_per_call", f("alc.reg.cycles_per_iter.1") / 25.0 - f("alc.reg.cycles_per_iter.0") / 5.0, origin["alc.reg.widths_us.0"])
put("x.spill.forced_minus_pin", f("alc.reg.cycles_per_iter.2") - f("alc.reg.cycles_per_iter.0"), origin["alc.reg.widths_us.0"])
put("x.overlap.cost16", f("alc.timer.sixteen.a1_isr.mean") - f("alc.timer.sixteen.a1_no.mean"), origin["alc.timer.sixteen.a1_no.mean"])
put("x.overlap.cost8", f("alc.timer.eight.a1_isr.mean") - f("alc.timer.eight.a1_no.mean"), origin["alc.timer.eight.a1_no.mean"])
put("x.overlap.costwarm", f("alc.timer.hs01.a1_isr.p50") - f("alc.timer.hs01.a1_no.p50"), origin["alc.timer.hs01.a1_no.p50"])
put("x.overlap.uniform16.pct", 100 * f("diag.cache100_on.load_noisr.mean") / f("diag.cache100_on.period.mean"), origin["diag.cache100_on.load_noisr.mean"])
put("x.overlap.uniform8.pct", 100 * f("diag.cache50_on.load_noisr.mean") / f("diag.cache50_on.period.mean"), origin["diag.cache50_on.load_noisr.mean"])
put("x.cycle.sum_over_3T", f("diag.cache50_on.cycle3.sum") / 3.0, origin["diag.cache50_on.cycle3.sum"])
put("x.line.revisit16", 2048 // 16, origin["pre.linemodel.k"]); put("x.line.revisit8", 2048 // 8, origin["pre.linemodel.k"]); put("x.line.revisit2", 2048 // 2, origin["pre.linemodel.k"])
put("x.spi.lines144", f("alc.spi.first_minus_later_queue") / f("pre.coldstart_per_line_us"), origin["alc.spi.first_minus_later_queue"])
put("x.dac.depth_diff_us", f("alc.dac.lat11.mean_us") - f("alc.dac.stall11.events.0.persist_us"), origin["alc.dac.lat11.mean_us"])
put("x.dac.blocks_equiv", f("alc.dac.lat11.mean_us") / 6400.0, origin["alc.dac.lat11.mean_us"])
put("x.cmp.perm_p", f"{float(vals['pre.cmp.perm_p_complete_separation']):.2e}", origin["pre.cmp.perm_p_complete_separation"])

(BUILD / "numbers_all.txt").write_text("\n".join(f"{k} = {v}" for k, v in sorted(vals.items())) + "\n")

used = None
if "--prune" in sys.argv:
    used = set()
    pat = re.compile(r"\\(?:V|Vn|us|ms|pct|cyc)\*?(?:\[[^\]]*\])?\{([^}]+)\}")
    for fn in sys.argv[sys.argv.index("--prune") + 1:]:
        used |= set(k for k in pat.findall(open(fn).read()) if "#" not in k)
    missing = sorted(k for k in used if k not in vals)
    if missing:
        print("UNDEFINED KEYS:", missing); sys.exit(1)

keys = sorted(vals) if used is None else sorted(used)
with open(BUILD / "numbers.tex", "w") as fh:
    fh.write("% Generated by analysis/p9_emit.py -- do not edit. One macro per reported value.\n")
    for k in keys:
        fh.write(f"\\expandafter\\def\\csname V@{k}\\endcsname{{{vals[k]}}}\n")
if used is not None:
    with open(VALID / "claim_to_evidence.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["key", "value", "result_file", "computed_by", "raw_source"])
        for k in keys:
            w.writerow([k, vals[k].replace("\\", ""), *origin[k]])
print(f"{len(vals)} values available; {len(keys)} emitted")
