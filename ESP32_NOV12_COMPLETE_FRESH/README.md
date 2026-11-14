# ESP32 experiment evidence — data provenance and interpretation (updated 12 November 2026)

## IMPORTANT: original baseline/high-stress capture contamination

The original **ZEROPLUS baseline and high-stress files from 11 November** were not all comparable replicates. The benchmark firmware allows **the cache-access mode to persist when switching among stress commands** (`1` baseline, `3` medium, `5` high stress; the high-stress worker is at the dispatcher's priority 22 on core 0). Thus a test named `Baseline` or `HighStress` could have run with a *warm-like* or a *maximum cold-line-target* memory workload, depending on earlier serial commands. The capture filename alone does not uniquely specify its true condition.

Pulse-width signatures from GPIO22 (A1) found:

| Legacy 11 Nov analyzer capture | A1 HIGH median | Inferred access pattern | Treatment |
|---|---:|---|---|
| `Baseline_01.alc` | ~2.76 us | warm-like | Use only with cache context stated |
| `Baseline_02.alc` | ~15.84 us | max cold-line-target-like | **Do not pool** with `Baseline_01` as matched baseline |
| `HighStress_01.alc` | short, warm-like (mean ~3.25 us) | warm-like but stress-distorted | Do not pool with `Highstress_02` |
| `Highstress_02.alc` | ~18.60 us | cold-line-target-like | Do not pool with `HighStress_01` |
| `Reg_overflow_01.alc`, `regoverflow_02.alc` | ~15.84 us | medium-stress (`3`) + cold-like | **Not** register-spill captures |

These are *inferences from waveform signatures*, not verified command histories. The state-persistence behavior is supported by the firmware. **Do not call all original ISR logs corrupted**: the automated on-chip preflight collection logged its own test configuration and can still support its separately identified scheduling comparisons; its cache and startup limitations remain relevant.

## Use the newer diagnostic dataset for controlled stress/cache comparisons

The folder `02_diagnostic_raw/` contains eight tests from the later instrumented firmware, each with `*_samples.csv`, `*_diag.csv`, and `*_combined.csv` (1024 retained events per condition). These should be the **primary source for flush ON/OFF and explicitly selected warm/cold stress conditions**. Summary and statistical analysis: `07_diagnostic_analysis/`.

Controlled diagnostic observations:

| Quantity | 8-line, flush ON | 8-line, flush OFF | 16-line, flush ON | 16-line, flush OFF |
|---|---:|---:|---:|---:|
| Mean absolute ISR-period jitter (us) | 9.281 | 0.769 | 6.463 | 5.872 |
| Mean marked load duration, no recorded ISR overlap (us) | 10.647 | 10.692 | 20.167 | 20.232 |
| Mean explicit flush duration (us) | 4.23 | 0.09 | 4.25 | 0.09 |

The near-unchanged non-overlap load duration with flush disabled **undermines interpreting these timings as an isolated measured cache-miss penalty**. The modes target 2/8/16 distinct lines; actual hardware miss percentages were not measured. Full-cache invalidation in the original firmware happens *before* the marked load interval. Measured wall time can include preemption and different loop instructions.

For high stress, new ring-depth diagnostics support event backlog as a cause of large dispatch delays, **not** a complete explanation of the unusually fast dispatches. In the diagnostic CSV, events with dispatch latency below 10 us had *zero* ring depth **after pop**, so do not claim fast events were observed with pending entries after pop.

### Limits of the diagnostic CSV

- It was acquired in a **different, more heavily instrumented firmware build**, not synchronously with the logic analyzer. Do not match individual CSV events to individual `.alc` edges from separate runs.
- Each of eight conditions is **one recorded run, retaining its final 1024 samples**. Consecutive events are dependent; not 1024 independent replications.
- Use the original preflight CSV for separately controlled original-firmware comparisons; use the new diagnostic CSV for diagnostic interventions. Keep conditions/builds explicit in every figure caption.

## New ZEROPLUS archive: 12 November 2026

`12nov_native_zeroplus/zeroplus_12nov/` contains **14 original `.alc` captures** from the latest lab session, preserved byte-for-byte from the user upload `zeroplus_12nov.zip`. These are **native binary captures, not CSV exports**. No new edge conversion or statistical validation of their signals is implied by inclusion.

Recognizable filenames: `C50_flushON`, `C50_flushOFF`, `C100_flushON`, `C100_flushOFF`, `DAC_latency_diag`, `DAC_stall_diag_highres`, `DAC_stall_diag_lowres`, `run_d_1`, `run_d_2`, `run_d_3`, `u1`, `u5`, `71`, `75`. The last four short names may encode command sequences, but **verify command provenance before definitively assigning experimental labels**. See `12nov_capture_manifest.csv`.

Before publication: validate the experimental `.alc` decoder timebase and GPIO26 diagnostic signal against native ZEROPLUS displays at the new capture settings; establish capture identity; do not assume the 11 Nov timebase applies automatically. For the DAC, A0 GPIO25 is an analog signal thresholded by a digital analyzer; it is not analog settling or a directly verified underrun flag.

## How to navigate the package

- `01_original_preflight_raw/` — original automated firmware CSVs and logs.
- `02_diagnostic_raw/` — controlled later on-chip diagnostic samples, joined CSVs, logs.
- `03_on_chip_statistics/`, `04_preflight_deep_audit/`, `05_logic_analyzer_analysis/`, `06_hypothesis_testing/`, `07_diagnostic_analysis/`, `08_cache_state_confound/`, `09_original_runner_and_analyzer/`, `10_source_scripts/`, `11_standalone_results/` — preserved analyses, data and scripts; see their individual notes.
- `12nov_native_zeroplus/` — new untouched native `.alc` capture files (not yet converted).
- `MANIFEST.csv` — file SHA-256 / sizes / provenance.

## Report-generation integrity rules

1. Never overwrite raw capture/measurement files. Preserve experiment code version and acquisition session with every plot.
2. Do not pool warm-like and cold-like 11 Nov stress waveforms as clean repeats.
3. For controlled cache-state and stress contrasts, prioritize diagnostic results but acknowledge one run per condition and instrumentation overhead.
4. Don't claim verified 50%/100% cache misses; these were *targeted access patterns*.
5. Do not treat old failed SPI DMA payload checks as passing. The later independent loopback trials passed; physical external capture validation must be tied to its particular run.
6. Treat ZEROPLUS reconstructed edges as derived data requiring timebase spot checks.
7. For figures, cite original filename, firmware version, sample counts, units, uncertainty and interpretation boundary.
