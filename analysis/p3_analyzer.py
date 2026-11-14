"""ZEROPLUS logic-analyzer captures (11 and 12 Nov 2026).

Decoding, timebase validation against crystal-derived signals, per-family
metrics, and export of MEASURED edge windows for the waveform figures.
All values use the corrected run-length pairing (see alc.py); the legacy
pairing is evaluated only to document what the correction changes.
"""
import math, csv
import numpy as np
from common import *
from alc import Capture

R = {}
C11 = lambda rel: Capture(ALC11 / rel)
C12 = lambda rel: Capture(ALC12 / rel)

# expected 512-byte payload, computed from the firmware's own initialisation
sine = [int(128.0 + 96.0 * math.sin(2 * math.pi * i / 20)) for i in range(20)]
src = [(0x10000 + i) ^ sine[i % 20] for i in range(128)]
PAYLOAD = bytes(((src[i >> 2] >> ((i & 3) * 8)) & 0xFF) for i in range(512))


def level_fn(c, ch):
    t, l = c.edges(ch)
    ts = np.concatenate([[0.0], t]); ls = np.concatenate([[int(c.level(ch)[0])], l])
    return lambda x: ls[np.searchsorted(ts, x, side="right") - 1]


def uart_frames(c, ch=3, bit=1.0):
    lv = level_fn(c, ch); t, l = c.edges(ch)
    out = []; tcur = -1.0
    for f in t[l == 0]:
        if f < tcur: continue
        b = 0
        for k in range(8): b |= int(lv(f + (1.5 + k) * bit)) << k
        out.append((float(f), b, int(lv(f + 9.5 * bit)))); tcur = f + 9.5 * bit
    return out


def export_wave(name, c, ch, t0, t1, scale=1.0, shift=None):
    tt, ll = c.step_trace(ch, t0, t1)
    base = t0 if shift is None else shift
    write_dat(name, ["t", "v"], [((float(a) - base) * scale, int(b)) for a, b in zip(tt, ll)], fmt="%.5f")
    return len(tt)


def strat(c):
    """A1 pulse widths split by whether an A2 (ISR entry) rising edge falls inside."""
    s1, e1 = c.pulses(1); r2 = c.rises(2); w = e1 - s1
    k = np.searchsorted(r2, s1); has = (k < len(r2)) & (r2[np.minimum(k, len(r2) - 1)] < e1)
    j = np.searchsorted(s1, r2); ok = j < len(s1); lat = s1[j[ok]] - r2[ok]
    per = np.diff(r2)
    return {"n_a1": int(len(w)), "a1": dist(w), "a1_no": dist(w[~has]), "a1_isr": dist(w[has]),
            "frac_isr": float(has.mean()), "n_isr": int(has.sum()), "a2_period": dist(per),
            "a2_absjit": dist(np.abs(per - 50.0)), "a2_width": dist(c.pulses(2)[1] - c.pulses(2)[0]),
            "lat": dist(lat), "lat_gt50": float((lat > 50).mean()), "lat_lt10": float((lat < 10).mean()),
            "valid_ms": float(c.duration_us / 1000.0)}

# =============================================================== inventory
inv = []
for root, tag in ((ALC11, "11-Nov"), (ALC12, "12-Nov")):
    for f in sorted(root.rglob("*.alc")):
        c = Capture(f)
        inv.append({"session": tag, "file": str(f.relative_to(root)), "acq": f"{c.acq_date} {c.acq_time}",
                    "rate_mhz": c.header_rate / 1e6, "depth": c.depth, "trigger_record": c.trig,
                    "pretrigger_garbage_records": c.pre_garbage, "valid_ms": round(c.duration_us / 1000.0, 3),
                    "edges": [int(len(c.edges(ch)[0])) for ch in range(8)], "sha256": sha256(f)})
with open(VALID / "analyzer_inventory.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(inv[0].keys())); w.writeheader(); w.writerows(inv)
R["inventory"] = {"n": len(inv), "n11": sum(i["session"] == "11-Nov" for i in inv), "n12": sum(i["session"] == "12-Nov" for i in inv),
                  "n_not_25mhz": sum(i["rate_mhz"] != 25 for i in inv),
                  "not_25mhz": [(i["file"], i["rate_mhz"]) for i in inv if i["rate_mhz"] != 25],
                  "n_pretrigger": sum(i["trigger_record"] > 0 for i in inv),
                  "n_garbage": sum(i["pretrigger_garbage_records"] > 0 for i in inv),
                  "garbage_files": [i["file"] for i in inv if i["pretrigger_garbage_records"] > 0],
                  "depth": sorted(set(i["depth"] for i in inv))}

# =============================================================== UART
U = {}
c = C11("01_Transfer/Polling_01.alc")
fr = uart_frames(c); b = bytes(x[1] for x in fr)
miss = next(k for k in range(len(b)) if b[k] != PAYLOAD[k])
s0, e0 = c.pulses(0); s1, e1 = c.pulses(1); k0 = int(np.argmax(e0 - s0))
st = np.array([x[0] for x in fr])
U["poll"] = {"frames": len(fr), "framing_errors": int(sum(1 for x in fr if x[2] != 1)),
             "first_mismatch_index": int(miss), "missing_byte_expected": int(PAYLOAD[miss]),
             "tail_matches_shifted": bool(b[miss:] == PAYLOAD[miss + 1:]), "n_tail": len(b) - miss,
             "a0_us": float((e0 - s0)[k0]), "a1_us": float((e1 - s1)[0]),
             "frame_spacing_min": float(np.diff(st).min()), "frame_spacing_max": float(np.diff(st).max()),
             "wire_span_us": float(st[-1] - st[0] + 10.0), "first_start_after_a0": float(st[0] - s0[k0])}
# measured wire window around the lost byte
i0 = miss - 3; t0 = st[i0] - 2.0; t1 = st[miss + 3] + 12.0
export_wave("wf_poll_a3.dat", c, 3, t0, t1)
write_dat("wf_poll_bytes.dat", ["t", "idx", "got", "exp"],
          [(float(st[i] - t0), i, f"{b[i]:02X}", f"{PAYLOAD[i]:02X}") for i in range(i0, miss + 4)], fmt="%.3f")
U["poll"]["window_us"] = float(t1 - t0)

for burst in (8, 16, 64, 120):
    c = C11(f"01_Transfer/Intr_{burst}B_01.alc")
    fr = uart_frames(c); b = bytes(x[1] for x in fr); st = np.array([x[0] for x in fr])
    s0, e0 = c.pulses(0); s1, e1 = c.pulses(1); s2, e2 = c.pulses(2); k0 = int(np.argmax(e0 - s0)); T0 = s0[k0]
    # A1 pulse inside each ISR entry (the first A1 pulse is the task-context priming write)
    a1w = np.zeros(len(s2))
    for i in range(len(s2)):
        m = (s1 >= s2[i] - 0.05) & (e1 <= e2[i] + 0.05)
        a1w[i] = (e1 - s1)[m].sum() if m.any() else 0.0
    started = np.array([int(((st >= s2[i]) & (st < (s2[i + 1] if i + 1 < len(s2) else 1e18))).sum()) for i in range(len(s2))])
    gaps = np.diff(s2)
    txfifo = len(s2) - 1                                   # last entry is TX_DONE (no A1 pulse)
    thr = 0.5 * (np.median(a1w[:txfifo][a1w[:txfifo] > np.median(a1w[:txfifo])]) + np.min(a1w[1:txfifo]))
    carry = a1w[:txfifo] > thr
    U[str(burst)] = {
        "frames": len(fr), "framing_errors": int(sum(1 for x in fr if x[2] != 1)),
        "bytes_match": int(sum(x == y for x, y in zip(b, PAYLOAD))), "a0_us": float((e0 - s0)[k0]),
        "isr_entries": int(len(s2)), "txfifo_entries": int(txfifo), "a1_pulses": int(len(s1)),
        "data_entries": int(carry.sum()), "reentries": int((~carry).sum()),
        "a2_sum_us": float((e2 - s2).sum()), "a2_sum_txfifo_us": float((e2 - s2)[:txfifo].sum()),
        "a2_data_us": float(np.median((e2 - s2)[:txfifo][carry])), "a2_reentry_us": float(np.median((e2 - s2)[:txfifo][~carry])),
        "a1_data_us": float(np.median(a1w[:txfifo][carry])), "a1_reentry_us": float(np.median(a1w[:txfifo][~carry])),
        "a2_txdone_us": float((e2 - s2)[-1]), "prime_a1_us": float((e1 - s1)[0]),
        "pair_gap_us": float(np.median(gaps[:-1][gaps[:-1] < 0.2 * np.median(gaps[:-1][gaps[:-1] > np.median(gaps[:-1]) * 0.5]) ])) if (gaps[:-1] < 30).any() else None,
        "long_gap_us": float(np.median(gaps[:-1][gaps[:-1] > 0.5 * gaps[:-1].max()])),
        "expected_data_refills": int(math.ceil(384 / burst)), "expected_refill_period_us": float(burst * 10.0),
        "first_entry_after_a0": float(s2[0] - T0), "txdone_after_last_frame_end": float(s2[-1] - (st[-1] + 10.0)),
        "last_frame_end_after_a0": float(st[-1] + 10.0 - T0), "service_frac_pct": float(100 * (e2 - s2).sum() / (e0 - s0)[k0]),
    }
    write_dat(f"uart_isr_{burst}.dat", ["t_ms", "kind"],
              [(float((s2[i] - T0) / 1000.0), (2 if i == len(s2) - 1 else (1 if carry[i] else 0))) for i in range(len(s2))])
    if burst == 8:
        # zoom: two refill pairs with the wire underneath
        j = 20; w0 = s2[j] - 12.0; w1 = w0 + 190.0
        for ch, nm in ((2, "a2"), (1, "a1"), (3, "a3")):
            export_wave(f"wf_uart8_{nm}.dat", c, ch, w0, w1)
        U["8"]["zoom_window_us"] = 190.0
write_dat("uart_sweep.dat", ["burst", "entries", "data", "reentry", "sum_us", "a0"],
          [(bb, U[str(bb)]["txfifo_entries"], U[str(bb)]["data_entries"], U[str(bb)]["reentries"],
            U[str(bb)]["a2_sum_us"], U[str(bb)]["a0_us"]) for bb in (8, 16, 64, 120)])
R["uart"] = U

# =============================================================== SPI
S = {}
for key, c in (("spi11", C11("01_Transfer/SPI_DMA_01.alc")), ("d1", C12("run_d_1.alc")), ("d2", C12("run_d_2.alc")), ("d3", C12("run_d_3.alc"))):
    t4, l4 = c.edges(4); rises = t4[l4 == 1]
    mosi = level_fn(c, 5)(rises + 0.02); miso = level_fn(c, 6)(rises + 0.02)
    tx = np.packbits(mosi.astype(np.uint8)[:4096]).tobytes(); rx = np.packbits(miso.astype(np.uint8)[:4096]).tobytes()
    cs_s, cs_e = c.pulses(7, high=False); s0, e0 = c.pulses(0); s1, e1 = c.pulses(1); s2, e2 = c.pulses(2); s3, e3 = c.pulses(3)
    k0 = int(np.argmax(e0 - s0)); T0 = s0[k0]
    S[key] = {"sclk_rises": int(len(rises)), "sclk_period_mean": float(np.diff(rises)[np.diff(rises) < 5].mean()),
              "sclk_freq_khz": float(1000.0 / np.diff(rises)[np.diff(rises) < 5].mean()),
              "byte_gap_us": float(np.median(np.diff(rises)[7::8])),
              "tx_matches_payload": bool(tx == PAYLOAD), "rx_equals_tx": bool(rx == tx),
              "mismatch": int(sum(a != b for a, b in zip(tx, rx))),
              "cs_low_us": float((cs_e - cs_s)[0]), "a0_us": float((e0 - s0)[k0]), "queue_us": float((e1 - s1)[0]),
              "cb_us": float((e2 - s2)[0]), "a0_to_cs": float(cs_s[0] - T0), "a0_to_sclk": float(rises[0] - T0),
              "last_sclk_to_cb": float(s2[0] - rises[-1]), "cs_rise_minus_a0_fall": float(cs_e[0] - e0[k0]),
              "pre_cb_after_a0": float(s3[0] - T0) if len(s3) else None,
              "overhead_us": float((e0 - s0)[k0] - (cs_e - cs_s)[0]), "acq": f"{c.acq_date} {c.acq_time}"}
    if key == "spi11":
        sp = (cs_s[0], cs_e[0])
        for ch, nm in ((0, "a0"), (1, "a1"), (2, "a2"), (7, "a7")):
            export_wave(f"wf_spi_{nm}.dat", c, ch, T0 - 300.0, e0[k0] + 300.0, scale=1e-3, shift=T0)
        write_dat("wf_spi_clkspan.dat", ["t0", "t1"], [((rises[0] - T0) / 1000.0, (rises[-1] - T0) / 1000.0)])
        z0 = cs_s[0] - 1.5; z1 = rises[23] + 2.0
        for ch, nm in ((7, "a7"), (4, "a4"), (5, "a5"), (6, "a6")):
            export_wave(f"wf_spiz_{nm}.dat", c, ch, z0, z1)
        S[key]["zoom_us"] = float(z1 - z0); S[key]["zoom_bytes"] = [f"{x:02X}" for x in tx[:3]]
        write_dat("wf_spiz_bytes.dat", ["t", "hex"], [(float(rises[8 * i] - z0), f"{tx[i]:02X}") for i in range(3)], fmt="%.3f")
S["first_minus_later_queue"] = S["d1"]["queue_us"] - 0.5 * (S["d2"]["queue_us"] + S["d3"]["queue_us"])
S["first_minus_later_precb"] = S["d1"]["pre_cb_after_a0"] - 0.5 * (S["d2"]["pre_cb_after_a0"] + S["d3"]["pre_cb_after_a0"])
S["precb_to_queue_return"] = [S[k]["queue_us"] - S[k]["pre_cb_after_a0"] for k in ("d1", "d2", "d3")]
write_dat("spi_trials.dat", ["i", "queue", "frame", "cs"],
          [(i + 1, S[k]["queue_us"], S[k]["a0_us"], S[k]["cs_low_us"]) for i, k in enumerate(("spi11", "d1", "d2", "d3"))])
R["spi"] = S

# =============================================================== timer / cache / stress captures
T = {}
files = {"base01": (ALC11, "02_Stress/Baseline_01.alc"), "base02": (ALC11, "02_Stress/Baseline_02.alc"),
         "hs01": (ALC11, "02_Stress/HighStress_01.alc"), "hs02": (ALC11, "02_Stress/Highstress_02.alc"),
         "warm": (ALC11, "03_Cache/Warm_01.alc"), "two": (ALC11, "03_Cache/cache125_01.alc"),
         "eight": (ALC11, "03_Cache/cache50_01.alc"), "sixteen": (ALC11, "03_Cache/coldlinemax_01.alc"),
         "regov1": (ALC11, "Reg_overflow_01.alc"), "regov2": (ALC11, "regoverflow_02.alc"),
         "c50on": (ALC12, "C50_flushON.alc"), "c50off": (ALC12, "C50_flushOFF.alc"),
         "c100on": (ALC12, "C100_flushON.alc"), "c100off": (ALC12, "C100_flushOFF.alc"),
         "u1": (ALC12, "u1.alc"), "x71": (ALC12, "71.alc"), "u5": (ALC12, "u5.alc"), "x75": (ALC12, "75.alc")}
caps = {}
for key, (root, rel) in files.items():
    c = Capture(root / rel); caps[key] = c
    d = strat(c); d["file"] = rel; d["acq"] = f"{c.acq_date} {c.acq_time}"
    s0, e0 = c.pulses(0)
    d["a0_period"] = dist(np.diff(c.rises(0))[np.abs(np.diff(c.rises(0)) - 1000) < 200]); d["a0_high"] = dist(e0 - s0)
    if root == ALC12:                      # A3 probes GPIO26 (whole-callback marker)
        s3, e3 = c.pulses(3); s1, e1 = c.pulses(1)
        i = np.searchsorted(s1, s3); ok = i < len(s1); i = i[ok]
        ins = (s1[i] >= s3[ok]) & (e1[i] <= e3[ok] + 0.5)
        d["a3"] = dist(e3 - s3); d["lead"] = dist((s1[i] - s3[ok])[ins]); d["trail"] = dist((e3[ok] - e1[i])[ins])
        d["lead_median"] = float(np.median((s1[i] - s3[ok])[ins]))
    # signature-based label for the access pattern (inferred, not logged)
    m = d["a1_no"]["p50"]
    d["inferred_pattern"] = "warm" if m < 2 else "two-line" if m < 6 else "eight-line" if m < 15 else "sixteen-line"
    lg = Capture(root / rel, legacy_pairing=True); sl, el = lg.pulses(1)
    d["legacy_a1_median"] = float(np.median(el - sl))
    T[key] = d
# flush state of 12-Nov captures inferred from GPIO26->GPIO22 lead (flush sits between the two edges)
for k in ("c50on", "c50off", "c100on", "c100off", "u1", "x71", "u5", "x75"):
    T[k]["inferred_flush"] = "on" if T[k]["lead_median"] > 2.0 else "off-or-warm"
R["timer"] = T
# histogram of sixteen-line A1 widths, split by whether a handler entry (A2 rise) falls inside the pulse
c = caps["sixteen"]
s1, e1 = c.pulses(1); r2 = c.rises(2); w = e1 - s1
k = np.searchsorted(r2, s1)
has = (k < len(r2)) & (r2[np.minimum(k, len(r2) - 1)] < e1)
ed = np.arange(18.0, 37.01, 0.5)
h_no = np.histogram(w[~has], ed)[0] / len(w); h_isr = np.histogram(w[has], ed)[0] / len(w)
write_dat("overlap_sixteen.dat", ["x", "no", "isr"],
          [(float(ed[i]), float(h_no[i]), float(h_isr[i])) for i in range(len(ed) - 1)] + [(float(ed[-1]), 0.0, 0.0)])

# measured windows
c = caps["base01"]; r2 = c.rises(2); w0 = r2[400] - 20.0
for ch, nm in ((2, "a2"), (1, "a1")):
    export_wave(f"wf_base_{nm}.dat", c, ch, w0, w0 + 620.0)
c = caps["hs01"]; r2 = c.rises(2); w0 = r2[400] - 20.0
for ch, nm in ((2, "a2"), (1, "a1")):
    export_wave(f"wf_hs_{nm}.dat", c, ch, w0, w0 + 620.0)
c = caps["sixteen"]; r2 = c.rises(2); w0 = r2[600] - 20.0
for ch, nm in ((2, "a2"), (1, "a1")):
    export_wave(f"wf_c16_{nm}.dat", c, ch, w0, w0 + 420.0)
c = caps["c100on"]; r2 = c.rises(2); w0 = r2[300] - 10.0
for ch, nm in ((2, "a2"), (3, "a3"), (1, "a1")):
    export_wave(f"wf_anat_on_{nm}.dat", c, ch, w0, w0 + 260.0)
c = caps["c100off"]; r2 = c.rises(2); w0 = r2[300] - 10.0
for ch, nm in ((2, "a2"), (3, "a3"), (1, "a1")):
    export_wave(f"wf_anat_off_{nm}.dat", c, ch, w0, w0 + 260.0)

# =============================================================== DAC
D = {}
for key, n in (("v", 8), ("w", 64), ("f", 256), ("x", 1024)):
    c = C11(f"SetupB/Run_{key}_01.alc"); s1, e1 = c.pulses(1); r1 = c.rises(1); r0 = c.rises(0)
    D[key] = {"n": n, "a1_pulses": int(len(s1)), "a1_period": dist(np.diff(r1)), "a1_width": dist(e1 - s1),
              "a0_period": dist(np.diff(r0)), "valid_ms": float(c.duration_us / 1000.0),
              "rate_hz": float(1e6 / np.diff(r1).mean()), "expected_period_us": float(n * 2 * 50.0),
              "fill_us_per_sample": float((e1 - s1).mean() / n), "marker_duty_pct": float(100 * (e1 - s1).mean() / np.diff(r1).mean()),
              "pulses_in_100ms": int(((r1 - r1[0]) < 100000.0).sum())}
    write_dat(f"dac_feed_{key}.dat", ["t_ms"], [((float(x - r1[0])) / 1000.0,) for x in r1 if x - r1[0] <= 110000.0], fmt="%.4f")
write_dat("dac_feeder.dat", ["n", "rate", "width", "period"], [(D[k]["n"], D[k]["rate_hz"], D[k]["a1_width"]["mean"], D[k]["a1_period"]["mean"]) for k in "vwfx"])
for key, c in (("lat11", C11("SetupB/Dac_output_latency_01.alc")), ("lat12", C12("DAC_latency_diag.alc"))):
    t1, l1 = c.edges(1); t0, l0 = c.edges(0)
    lags = []
    for tt, ll in zip(t1, l1):
        j = np.nonzero((t0 > tt) & (l0 == ll))[0]
        if len(j): lags.append((float(tt), int(ll), float(t0[j[0]] - tt)))
    D[key] = {"lags_us": [x[2] for x in lags], "polarity": [x[1] for x in lags], "mean_us": float(np.mean([x[2] for x in lags])),
              "spread_us": float(np.ptp([x[2] for x in lags])), "n": len(lags), "samples_equiv": float(np.mean([x[2] for x in lags]) / 50.0),
              "half_period_ms": float(np.diff(t1).mean() / 1000.0) if len(t1) > 1 else None, "valid_ms": float(c.duration_us / 1000.0)}
    if key == "lat11":
        for ch, nm in ((1, "a1"), (0, "a0")):
            export_wave(f"wf_daclat_{nm}.dat", c, ch, 0.0, c.duration_us, scale=1e-3, shift=0.0)
for key, c in (("stall11", C11("SetupB/Dac_feeder_stall_01.alc")), ("stall11b", C11("SetupB/Dac_feeder_stall_02.alc")),
               ("stall12", C12("DAC_stall_diag_highres.alc")), ("stall12b", C12("DAC_stall_diag_lowres.alc"))):
    s1, e1 = c.pulses(1); t0, l0 = c.edges(0); w = e1 - s1
    big = np.nonzero(w > 10000.0)[0]
    ev = []
    for i in big:
        before = t0[t0 < s1[i]]; inside = t0[(t0 >= s1[i]) & (t0 <= e1[i])]; after = t0[t0 > e1[i]]
        gaps = np.diff(t0[(t0 > s1[i] - 2000) & (t0 < e1[i] + 15000)])
        g = int(np.argmax(gaps)); tw = t0[(t0 > s1[i] - 2000) & (t0 < e1[i] + 15000)]
        ev.append({"stall_us": float(w[i]), "persist_us": float(tw[g] - s1[i]), "silent_us": float(gaps[g]),
                   "resume_after_stall_end_us": float(tw[g + 1] - e1[i])})
    D[key] = {"rate_mhz": c.header_rate / 1e6, "n_stalls": int(len(big)), "events": ev, "valid_ms": float(c.duration_us / 1000.0),
              "a0_period_med": float(np.median(np.diff(c.rises(0))))}
    if key == "stall11":
        i = big[0]; w0 = s1[i] - 8000.0; w1 = e1[i] + 14000.0
        for ch, nm in ((1, "a1"), (0, "a0")):
            export_wave(f"wf_stall_{nm}.dat", c, ch, w0, w1, scale=1e-3, shift=s1[i])
c = C12("DAC_stall_diag_highres.alc"); s3, e3 = c.pulses(3)
D["write12"] = {"n": int(len(s3)), "width": dist(e3 - s3), "period": dist(np.diff(s3))}
R["dac"] = D

# =============================================================== register windows
c = C11("regflow_1000x_comp_01.alc"); s1, e1 = c.pulses(1)
lg = Capture(ALC11 / "regflow_1000x_comp_01.alc", legacy_pairing=True); sl, el = lg.pulses(1)
R["reg"] = {"widths_us": [float(x) for x in (e1 - s1)], "gaps_us": [float(x) for x in (s1[1:] - e1[:-1])],
            "legacy_widths_us": [float(x) for x in (el - sl)],
            "cycles_per_iter": [float(x * CPU_MHZ / 1000.0) for x in (e1 - s1)]}
export_wave("wf_reg_a1.dat", c, 1, s1[0] - 1500.0, e1[-1] + 1500.0, scale=1e-3, shift=s1[0])

# =============================================================== timebase validation
V = {"uart_bit_us": {}, "notes": "each row compares an analyzer-measured interval with a quantity fixed by the ESP32 crystal"}
c = C11("01_Transfer/Intr_16B_01.alc"); fr = uart_frames(c); st = np.array([x[0] for x in fr])
V["uart_frame_us"] = float((st[-1] - st[0]) / (len(st) - 1)); V["uart_frame_expected"] = 10.0
V["spi_bit_us"] = float((lambda r: (r[-1] - r[0]))(C11("01_Transfer/SPI_DMA_01.alc").rises(4)) / 4095.0)
V["dac_cycle_us"] = D["v"]["a0_period"]["mean"]; V["dac_cycle_expected"] = 200.0
V["timer_period_us"] = T["base01"]["a2_period"]["mean"]
V["dac_lowrate_cycle_us"] = D["stall11b"]["a0_period_med"]; V["dac_10mhz_cycle_us"] = D["stall12b"]["a0_period_med"]
V["uart_payload_ok"] = {k: U[k]["bytes_match"] for k in ("8", "16", "64", "120")}
V["spi_payload_ok"] = {k: S[k]["tx_matches_payload"] and S[k]["rx_equals_tx"] for k in ("spi11", "d1", "d2", "d3")}
# legacy pairing on the same UART capture
lg = Capture(ALC11 / "01_Transfer/Intr_16B_01.alc", legacy_pairing=True); frl = uart_frames(lg)
V["legacy_uart_bytes_match"] = int(sum(x[1] == y for x, y in zip(frl, PAYLOAD))); V["legacy_uart_framing_errors"] = int(sum(1 for x in frl if x[2] != 1))
R["validation"] = V
save_results("analyzer", R)
(VALID / "alc_validation.json").write_text((RES / "analyzer.json").read_text())

import json
pp = lambda d: json.dumps(d, default=float)[:1500]
print("inventory", pp(R["inventory"]))
print("poll", pp(U["poll"]))
for bb in ("8", "16", "64", "120"): print("uart", bb, pp(U[bb]))
for k in ("spi11", "d1", "d2", "d3"): print(k, pp(S[k]))
print({k: S[k] for k in ("first_minus_later_queue", "first_minus_later_precb", "precb_to_queue_return")})
for k, d in T.items():
    print(f"{k:8s} {d['acq']} pat={d['inferred_pattern']:12s} A1 no-ISR {d['a1_no']['mean']:.3f} (n={d['a1_no']['n']}) ISR {d['a1_isr'].get('mean', float('nan')):.3f} ({100*d['frac_isr']:.2f}%) lat {d['lat']['mean']:.2f}+/-{d['lat']['sd']:.2f} >50 {100*d['lat_gt50']:.1f}% <10 {100*d['lat_lt10']:.1f}% per sd {d['a2_period']['sd']:.2f} absjit {d['a2_absjit']['mean']:.3f} legacyA1med {d['legacy_a1_median']:.2f}"
          + (f" A3 {d['a3']['mean']:.2f} lead {d['lead']['p50']:.2f} trail {d['trail']['p50']:.2f} flush={d['inferred_flush']}" if 'a3' in d else ""))
for k in "vwfx": print("dac", k, pp(D[k]))
for k in ("lat11", "lat12", "stall11", "stall11b", "stall12", "stall12b", "write12"): print(k, pp(D[k]))
print("reg", R["reg"]); print("valid", pp(V))
