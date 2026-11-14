"""Shared paths and helpers for the report pipeline.

Every number that appears in the report is written by one of the p*.py
scripts into build/results/*.json and reaches LaTeX through build/numbers.tex
(see p9_emit.py).  Raw inputs are opened read-only and never modified.
"""
import json, pathlib, hashlib
import numpy as np

HANDOFF = pathlib.Path("/home/claude/handoff")
WORK = pathlib.Path("/home/claude/work")
BUILD = WORK / "build"
DATA = BUILD / "data"
RES = BUILD / "results"
VALID = WORK / "validation"
PRE = HANDOFF / "data/raw_original/preflight_10nov/esp32_preflight_results/20261110_221648"
DIAG = HANDOFF / "data/raw_diagnostic/diagnostic_serial_12nov/esp32_diag_results/20261112_121720"
ALC11 = HANDOFF / "data/raw_analyzer/zeroplus_11nov/zeroplus_11nov"
ALC12 = HANDOFF / "data/raw_analyzer/zeroplus_12nov/zeroplus_12nov"
FW_ORIG = HANDOFF / "firmware/original/esp32_benchmark_logged.ino"
FW_DIAG = HANDOFF / "firmware/diagnostic/ESP32_Diag_Fixed/ESP32_Diag.ino"
CPU_MHZ = 160.0
NOMINAL_US = 50.0
for d in (DATA, RES, VALID):
    d.mkdir(parents=True, exist_ok=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def save_results(name, obj):
    def conv(o):
        if isinstance(o, (np.floating,)): return float(o)
        if isinstance(o, (np.integer,)): return int(o)
        if isinstance(o, (np.bool_,)): return bool(o)
        if isinstance(o, np.ndarray): return o.tolist()
        raise TypeError(type(o))
    (RES / f"{name}.json").write_text(json.dumps(obj, indent=1, default=conv, sort_keys=True))


def write_dat(name, columns, rows, fmt="%.6g"):
    """Whitespace table readable by pgfplots: header line + rows."""
    path = DATA / name
    with open(path, "w") as f:
        f.write(" ".join(columns) + "\n")
        for r in rows:
            f.write(" ".join((fmt % v) if isinstance(v, (float, np.floating)) else str(v) for v in r) + "\n")
    return path


def dist(x):
    """Descriptive summary of an event-level sample (no inferential claim)."""
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return {"n": 0}
    return {
        "n": int(len(x)), "mean": float(x.mean()),
        "sd": float(x.std(ddof=1)) if len(x) > 1 else 0.0,
        "min": float(x.min()), "p01": float(np.percentile(x, 1)), "p05": float(np.percentile(x, 5)),
        "p50": float(np.percentile(x, 50)), "p95": float(np.percentile(x, 95)),
        "p99": float(np.percentile(x, 99)), "max": float(x.max()),
    }


def acf(x, maxlag):
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    den = float((x * x).sum())
    return np.array([1.0] + [float((x[:-k] * x[k:]).sum() / den) for k in range(1, maxlag + 1)])


def ecdf_points(x, npts=240):
    """Quantile-thinned ECDF: exact extremes plus evenly spaced probabilities."""
    x = np.sort(np.asarray(x, dtype=float))
    n = len(x)
    p = np.unique(np.concatenate([np.linspace(0, 1, npts), [0.9, 0.95, 0.99, 0.995, 0.999]]))
    idx = np.clip(np.ceil(p * n).astype(int) - 1, 0, n - 1)
    return [(float(x[i]), float((i + 1) / n)) for i in idx]
