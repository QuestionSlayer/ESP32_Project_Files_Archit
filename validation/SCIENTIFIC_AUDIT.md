# Scientific audit

Scope: every number, figure and table in `ESP32_Project_Report.pdf`. All values are recomputed from the raw
files in the handoff by `analysis/p0..p9`; none is copied from the handoff's narrative documents.
Per-value traceability is in `claim_to_evidence.csv` (445 value macros: key, value, result file, script, raw
source) and per-figure traceability in `FIGURE_SOURCE_MAP.csv` (25 figures, 21 tables).

## 1. Inputs

- 379 raw input files used (S1 preflight, S4 diagnostic serial, 38 analyzer captures, two firmware sources).
  All 379 SHA-256 hashes match `MANIFEST_SHA256.csv` from the handoff (`input_manifest.json`). Nothing in the
  handoff tree was modified; all outputs are written under `work/`.
- On-chip runs are parsed from the raw cycle counts in each serial transcript, not from the host-converted CSVs.
  Acceptance: row count equals the firmware's announced count, contiguous index, no ring overflow.
  59 of 60 timer runs accepted; `cache_warm_005` is one row short and excluded (`run_acceptance.csv`,
  `excluded_runs.csv`). 75,351 events, identical to `all_timer_samples.csv`.

## 2. Handoff headline values against recomputation

| Quantity | Handoff value | Recomputed from raw | Status |
|---|---|---|---|
| Baseline ISR-entry period, mean ± SD (µs) | 50.051 ± 0.670 | 50.051 ± 0.670 | reproduced |
| Baseline mean |jitter| (µs) | 0.173 | 0.173 | reproduced |
| Stress period, mean ± SD (µs) | 50.052 ± 1.706 | 50.052 ± 1.706 | reproduced |
| Stress mean |jitter| (µs) | 0.879 | 0.879 | reproduced |
| Baseline latency mean ± SD; P95; P99 (µs) | 13.224 ± 1.268; 13.981; 21.094 | 13.224 ± 1.268; 13.981; 21.094 | reproduced |
| Stress latency mean ± SD; P95; P99 (µs) | 53.664 ± 33.237; 106.839; 113.169 | 53.664 ± 33.237; 106.839; 113.169 | reproduced |
| Stress events with latency > 50 µs | 53.33 % | 53.33 % | reproduced |
| Stress events with latency < 10 µs | 10.52 % | 10.52 % | reproduced |
| Next ISR before dispatch (stress) | 53.36 % | 53.37 % | reproduced (53.37) |
| Flash-work mean ± SD, warm / 2 / 8 / 16 lines (µs) | 0.999±0.268 / 3.414±0.456 / 10.968±1.897 / 23.371±3.737 | 0.999±0.268 / 3.414±0.456 / 10.968±1.897 / 23.371±3.737 | reproduced |
| Original mean |jitter|, 8-line / 16-line (µs) | 10.221 / 7.940 | 10.221 / 7.940 | reproduced |
| Diagnostic latency, baseline warm / stress warm (µs) | 13.414±1.264 / 56.231±35.265 | 13.414±1.264 / 56.231±35.265 | reproduced |
| Ring non-empty after pop, stress warm / cold | 54.4 % / 58.6 % | 54.4 % / 58.6 % | reproduced |
| Latency by depth 0..3, stress warm (µs) | 23.25 / 74.03 / 110.23 / 167.84 | 23.25 / 74.03 / 110.23 / 167.84 | reproduced |
| Flush ON/OFF mean |jitter|, 8-line (µs) | 9.281 / 0.769 | 9.281 / 0.769 | reproduced |
| Flush ON/OFF mean |jitter|, 16-line (µs) | 6.463 / 5.872 | 6.463 / 5.872 | reproduced |
| No-overlap load ON/OFF, 8-line (µs) | 10.647 / 10.692 | 10.647 / 10.692 | reproduced |
| No-overlap load ON/OFF, 16-line (µs) | 20.167 / 20.232 | 20.167 / 20.232 | reproduced |
| Flush time ON / OFF (µs) | ~4.23–4.25 / ~0.09 | 4.231, 4.246 / 0.094 | reproduced |
| Register cycles/iteration (on-chip) | 261 / 2116 / 621 | 261 / 2116 / 621 | reproduced |
| SPI preflight: first queue; later mean ± SD (µs) | 223.71; 83.33 ± 1.57 | 223.71; 83.33 ± 1.57 | reproduced |
| Preflight events / attempted trials | ~75,351 / 110 | 75351 / 110 | reproduced |
| Baseline latency ACF at lag 20 | 0.802 | 0.785 (mean of per-run ACFs; pooled 0.786) | close; definition differs |
| ANALYZER: A1 pulse, 16-line, no ISR / ISR inside (µs) | 15.26 / 27.12 | 20.07 / 27.34 | CORRECTED (run-length pairing) |
| ANALYZER: ISR-in-A1 overlap, 16-line / 8-line | 43.35 % / 3.67 % | 43.35 % / 3.67 % | reproduced |
| ANALYZER: Baseline_01 / Baseline_02 A1 median (µs) | 2.76 / 15.84 | 0.92 / 20.04 | CORRECTED (pairing); carry-over conclusion unchanged |
| ANALYZER: polling A1 / A0 (µs) | 5111.76 / 5123.28 | 5113.12 / 5114.40 | CORRECTED (pairing) |
| ANALYZER: polling bytes on the wire | 512 (assumed) | 511 (byte index 130 missing) | NEW FINDING |
| ANALYZER: UART refill entries 8/16/64/120 B | 96/48/12/8 ('896 B' inconsistency open) | 96/48/12/8 = 2 x ceil(384/b); 512/512 bytes decoded in each | RESOLVED |
| ANALYZER: SPI first queue marker; CS low (µs) | 226.6; 5121 | 226.60; 5121.24 | reproduced |
| ANALYZER: DAC step lags (µs) | 9767.04, 9763.40, 9763.00 | 9764.36, 9764.72, 9764.40 | CORRECTED (pairing) |
| ANALYZER: DAC stall marker (µs) | 20001.08 | 20000.16 | CORRECTED (pairing) |
| ANALYZER: register batches (ms) | 1.63440 / 13.22064 / 3.88180 | 1.63388 / 13.22552 / 3.88268 | CORRECTED (pairing) |
| ANALYZER: sample rate | 25 MHz assumed for all | read from header; 36 at 25 MHz, 1 at 1 MHz, 1 at 10 MHz | CORRECTED |

Every on-chip headline value in the handoff reproduces to the last printed digit. Every analyzer-derived
pulse width changes, for the reason in section 3.

Values quoted in the handoff that could not be traced to any file in the archive and are therefore NOT
used in the report: UART summed ISR time 108.86 / 71.09 / 42.72 / 39.68 µs (only the 16 B value, 70.91 µs,
exists in the archive, in S1); SPI "later PASS" serial values 226.62 / 84.36 / 82.26 µs. The report uses the
analyzer captures for the UART sweep and S1 plus the analyzer for SPI.

## 3. Corrections to the handoff's analysis

1. **Analyzer run-length pairing (affects every analyzer pulse width).** Each .alc record holds the new input
   state and the length of the run that just ended. `alc_to_csv_fixed.py` paired each length with the state in
   the same record. Evidence for the corrected pairing: all 512 payload bytes decode correctly in each of the
   four interrupt-mode UART captures (legacy pairing: 1 of 512, 91 framing errors); MOSI equals the computed
   payload and MISO equals MOSI in all four SPI captures; analyzer intervals agree with the on-chip counter
   to within 3 % above 1 µs (`alc_validation.json`, report Fig. 3.3, Table 3.3).
2. **Sample rate and trigger index are in the file header** (float64 at 0x12C, uint32 at 0x144). Two captures
   are not 25 MHz (`Dac_feeder_stall_02` 1 MHz, `DAC_stall_diag_lowres` 10 MHz). In 22 captures the records
   before the trigger index are not data and are dropped; in eight 12-Nov captures they are uninitialised
   memory. With that done the 12-Nov captures decode, their timebase checks against the 50.05 µs timer and
   they agree with the 12-Nov serial run cell by cell (report Table 7.2).
3. **UART "896 bytes" inconsistency: resolved.** 512 bytes are on the wire. The handler is entered twice per
   refill; the firmware counter increments on both. Count model 2*ceil(384/b) = 96/48/12/8 matches exactly.
4. **Polling loses data: new.** One capture, 511 frames, byte 130 missing; all ten S1 polling trials end
   4.3-59.2 µs short of 5120 µs. Cause not established.
5. **Lag-20 structure: resolved as to period.** The slow events drift one table position per ~49 ms in all
   ten baseline runs, giving an interferer period of 1000.02 µs; the 20-entry table (1001.02 µs) cannot drift.
6. **Fast dispatches under stress: explained in kind.** They are the newest event in the ring (depth 0, as
   the handoff found) and occur when the dispatcher is already running. Their frequency is not explained.
7. **Flush ON/OFF: replicated and reinterpreted.** The analyzer session (S3) reproduces the on-chip result
   (S4) in all four cells. Leading hypothesis for "no change in load time": the 64 KiB table exceeds the
   32 KiB two-way cache, so both arms are cold. Not tested.
8. **State carry-over, second instance.** 12-Nov captures `71` and `75` show a 0.40 µs GPIO26-to-GPIO22
   lead, i.e. invalidation was still switched off from the preceding capture.
9. **Runs are near-replays.** Median pair of baseline runs is 90 % identical event for event. Run-level
   intervals therefore describe repeatability within a session, and the report says so.

## 4. Guardrails from AGENTS.md / claims_registry.yaml

| Forbidden or gated claim | How the report handles it |
|---|---|
| Measured miss percentages | Patterns named warm / two- / eight- / sixteen-line; "no counter reports a miss" (Ch. 7) |
| Intrinsic miss penalty | 1.19 µs per line is labelled an inference from 16 events, tier "hypothesis" |
| Analog settling | Excluded explicitly (Sec. 6.3, Table 10.2) |
| Hardware underrun | "threshold crossings cease"; underrun flag not recorded (Sec. 6.4) |
| CPU utilisation | Marker time called handler/service time; disclaimer in Sec. 5.1 |
| Missed deadline | "period exceedance" defined in Sec. 2.2 and glossary |
| Hardware alarm jitter | T_i defined as handler-entry period; Fig. 3.2 |
| Spill handler latency | Declined in Sec. 8.3 |
| Pooling Baseline_01/02, HighStress_01/02 | Not pooled; Table 4.2 |
| Reg_overflow files as register data | Identified as timer captures; only regflow_1000x_comp_01 used |
| SPI PASS for S1 | Stated as failed; timings only (Sec. 5.6, Table 5.2) |
| Event-level p-values | None. One exact permutation bound over runs, with the replay caveat |
| Cross-session event matching | None; stated in Sec. 3.5 |

Text scan of the chapter sources for "miss rate", "underrun", "utilization", "deadline", "worst-case":
each occurrence is a negation or a definition.

## 5. Statements that rest on external documentation, not on the data

- Cache geometry (32 KB per CPU, two-way, 32-byte blocks): ESP32 Technical Reference Manual v5.9, Sec. 3.3.4
  (checked online on 12 Nov 2026).
- FreeRTOS tick of 1 kHz in the Arduino core: cited, not measured directly; the data give a 1000.02 µs period.
- IDF UART driver refilling before clearing the interrupt: cited from memory of the driver source; marked as
  part of a hypothesis. Worth checking against the IDF version actually used.
- Textbook section numbers and Definitions 36 and 84 were checked against `book/archbook.pdf`.

## 6. Not verified

Compiled binaries (not archived; the diagnostic binary retained 1024 events, its source says 2048); linker
placement of `flash_rodata_table`; emitted call instructions; cache replacement policy; identity of the
1 ms interferer; cause of the polling loss; cause of the first-SPI-transaction excess.
