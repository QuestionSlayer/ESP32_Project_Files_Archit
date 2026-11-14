# ZEROPLUS `.alc` batch analysis — ESP32 project

**Source:** `zeroplus_11nov.zip` (24 `.alc` files), acquired at user-reported 25 MHz, 32K record depth, compression enabled. **Method:** experimental reverse-engineered ALC parser (`alc_to_csv_fixed.py`), extracting 4-byte packed channel states and elapsed tick counts. Timebase 40 ns/tick; all reported intervals quantized to that resolution. Converter validated against the SPI CS duration and clocks for one capture, **not** independently validated for each channel and file in the archive. The parser produced digital sample edges for all 24 captures. Interpret the following as provisional until a representative non-SPI ZEROPLUS-exported CSV confirms timing on another capture.

## Major findings

### UART transfers: instrumented external signals

| Mode | GPIO25 longest HIGH (µs) | GPIO19 HIGH pulses | Typical *long* gap between A2 pulses (µs) | Short inter-pulse gaps |
|---|---:|---:|---:|---|
| Polling | 5123.28 | 0 | — | none |
| IRQ 8 B | 5132.96 | 97 | 77.44 | near 2.56 µs |
| IRQ 16 B | 5124.76 | 49 | 156.84 | near 3.16 µs |
| IRQ 64 B | 5128.80 | 13 | 633.74 | near 6.76 µs |
| IRQ 120 B | 5127.96 | 9 | 1193.04 | near 14.96 µs |

**Important:** A2 interrupt-related GPIO pulses come in close pairs (long gap then a short gap). Don't naïvely average all rising-edge gaps to estimate the refill cadence. The captured marker-pulse counts are generally **one more** than firmware-reported interrupt counts (96,48,12,8), probably an additional event/marker, but the causal identification needs source-level matching. The terminal gap was ~1,272–1,275 µs in 8/16/64 byte captures, while the 120-byte pattern has a different terminal gap. Identifying completion versus FIFO threshold status requires correlating code and trace; do not claim it is definitively a TX-done interrupt.

### SPI DMA

- 512 complete SPI bytes reconstructed, 4,096 rising SCLK edges while CS active, MOSI and MISO decoded identical. CS LOW interval 5,121.00 µs; SPI clock median period ~1.24 µs (~806 kHz).
- GPIO25 longest HIGH: **5,357.52 µs** from this parser; ZEROPLUS UI screenshot previously showed ~5,352 µs (difference ~5.5 µs). GPIO22 submission HIGH: **226.12 µs** parser versus ~226.6 µs in UI. **Do not silently substitute the internal Serial values** (5353.84 µs and 226.62 µs), as timestamp boundaries may differ and a few microseconds of deviation remain.
- Only one SPI DMA hardware waveform in archive. First-versus-subsequent DMA warm-up effect is supported primarily by separate repeated ESP32 serial logs, not an external two-run comparison.
- Firmware loopback PASS for later separate runs is functional validation, but identical MOSI/MISO electrical traces from a connected jumper are expected and not independently a transfer-integrity test.

### Timer, stress, and software LUT GPIO25

A2 = GPIO19 ISR marker. A0 = GPIO25 LUT-threshold output (NOT CPU workload, NOT analog DAC in these modes). Sample interval 40 ns.

| Capture | A2 period mean (µs) | A2 period SD (µs) | A2 periods counted |
|---|---:|---:|---:|
| Baseline_01 | 50.049 | 1.656 | 3,240 |
| Baseline_02 | 50.063 | 12.636 | 3,648 |
| HighStress_01 | 50.052 | 4.698 | 3,315 |
| Highstress_02 | 50.064 | 5.355 | 3,663 |

Mean ISR-entry period stays ~50 µs, but individual-edge variability differs markedly **even between the two baseline recordings**. Do not automatically attribute all larger jitter to FreeRTOS stress; investigate sampling settings, firmware modes, marker boundaries and capture-to-capture differences. The archive has no clearly labelled independent medium-stress file; `Reg_overflow_01` and `regoverflow_02` were previously identified by the user as command `3` captures, so their filenames are misleading. Their A2 period SDs are ~12.73 and 13.05 µs, respectively.

GPIO25 LUT rising period is ordinarily near 1 ms; some distributions have missed/skipped transitions creating large outliers. Do not interpret a ~550 µs HIGH duration as the whole sine-LUT output period. GPIO25's thresholded digital output duration is affected by dispatcher timing, not analog-to-digital conversion.

### Cache marker (A1 GPIO22)

| Condition | A1 pulse mean (µs) | Median (µs) | P95 (µs) | Pulses |
|---|---:|---:|---:|---:|
| Warm | 2.802 | 2.76 | 2.80 | 3,240 |
| Target 2 cold lines | 6.752 | 6.88 | 7.00 | 3,657 |
| Target 8 lines | 15.773 | 15.84 | 18.16 | 3,408 |
| Target 16 lines | 20.400 | 15.84 | 28.92 | 3,654 |

External pulse durations are **NOT** identical to internal `flash_work_us` values from preflight (roughly 0.999, 3.414, 10.968, 23.371 µs). Marker placement, workload timing/context, truncation and/or chip caching state may differ. The 16-line target shows a multimodal pulse-width distribution (median ~15.84 µs, upper tail >28 µs): do not claim a uniformly fixed 23 µs cost or verified cache miss rate. A1 captures support condition-dependent timing, not measured cache-miss percentages.

### DAC modes

- Four buffer modes `v/w/f/x`: A1 feeder pulse counts during their approximate 0.32-second captures: 320 / 41 / 11 / 3, respectively. Counts suggest fewer feeder operations for larger requested buffers; compare per-second rates only after checking capture conditions and sustained operation.
- DAC A0 output in v/w/f/x has ~200 µs rising-edge periods, and typical HIGH duration ~99.64 µs. This is digital threshold interpretation of an analog output, not a calibrated voltage waveform.
- `y` output step: A1 software step **rises at 67,092.48 µs**, A0 threshold **rises at 76,859.52 µs** (delay **9,767.04 µs**). Next rise A1 at 271,896.64 µs and A0 at 281,659.64 µs (delay **9,763.00 µs**); fall A1 at 169,496.20 µs, A0 at 179,259.60 µs (delay **9,763.40 µs**). Mean of these three transition delays approximately **9,764.48 µs**. The three transitions are serially related, not three independent runs; this measures threshold-crossing output lag, not analog settling time.
- `z` long A1 marker in `Dac_feeder_stall_01` from 118,156.76 to 138,157.84 µs: **20,001.08 µs**, confirms deliberate feeder stall visible. Other A1 durations around 53.29 ms and A0 long holds around 43.53 ms require separate interpretation. `stall_02` features a different DAC output period (~8 µs), suggesting a different output configuration; do not pool the two captures without checking.
- A visible stall plus output level disruption does not alone prove a particular DMA underrun flag/condition; logic analyzer only resolves digital thresholds.

### Register-window benchmark

Only `regflow_1000x_comp_01.alc` is clearly the command `r` three-stage benchmark; other `Reg_overflow*` names actually refer to medium stress in the conversation. A1 (GPIO22) HIGH windows in `regflow_1000x_comp_01` are **1,634.40 µs shallow**, **13,220.64 µs deep**, **3,881.80 µs forced spill**; each covers 1,000 iterations. Per-operation averages ~1.6344 / 13.2206 / 3.8818 µs, respectively. Forced-spill additional ~2.2474 µs per iteration and ~2.37× shallow. This includes calls/loop instrumentation; does not isolate Xtensa window-overflow exception latency.

## Data-quality and interpretive limitations

1. Proprietary `.alc` format; parser experimentally reverse engineered, and capture clock is assumed to be 25 MHz based on user-supplied settings. Validate at least one non-SPI waveform against native ZEROPLUS values before publication.
2. 32K **compressed-record** memory depth is NOT 32K uniform time samples. CSV exports reconstruct transition times via elapsed tick counts. Simple CSV sample indexes are wrong for timing.
3. First/last pulses can be clipped by capture boundaries. `high_pulses.csv` includes *fully observed rise/fall* intervals only; a starting HIGH state has no observed start. Period sequences can contain missing edges or marker transitions unrelated to the nominal periodic trigger.
4. A0/A1/A2 are software markers whose meanings differ between experiment modes; never treat raw channel traces as CPU utilization percentages.
5. Significant differences between Baseline_01 and Baseline_02; some captures are not directly exchangeable without recording configuration/firmware details. Different run sizes and compressed capture durations.
6. Single ALC recording for most configurations; events within a capture are serially dependent, not independent experimental repetitions; don't use per-edge sample count as replicate count in inferential tests.
7. The current `rising_periods.csv` includes close paired UART IRQ marker pulses and terminal events; filter/classify before interpreting steady-state interrupt cadence.
8. DAC analog voltage cannot be reconstructed from digital-only threshold crossing states.
9. External A1 cache pulse is NOT identical to internal flash-load-only measurement; reconciliation requires inspecting instrumented boundaries and ideally captures exported by ZEROPLUS.

## Included artifacts

- `capture_inventory_statistics.csv`: all 24 captures and per-channel pulse/period metrics
- `timer_and_lut_period_statistics.csv`, `cache_gpio22_pulse_statistics.csv`, `uart_and_spi_timing.csv`, `dac_pulse_statistics.csv`, `register_triplet.csv`
- `all_high_pulses.csv`, `all_rising_periods.csv`: consolidated per-event evidence (timestamps in µs)
- `plots/*.png`: report-ready *draft* visualizations, quantitative but dependent on converter validation
- `converted_edges/`: `digital_edges.csv` and `summary.json` for every original ALC capture
- `alc_to_csv_fixed.py`, `analyze_zeroplus_archive.py`: processing source

**Suggested next verification:** In ZEROPLUS, reopen `Baseline_02.alc` and measure 5–10 successive A2 rising-to-rising periods, and `Dac_output_latency_01.alc` step-to-step lag; confirm against converted CSV. If these agree, the cross-mode timebase and marker decoding are substantially better supported.
