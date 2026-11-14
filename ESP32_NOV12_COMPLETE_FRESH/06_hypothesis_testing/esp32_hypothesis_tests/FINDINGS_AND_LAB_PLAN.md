# ESP32 hypothesis-driven follow-up — 11 Nov 2026

## Inputs
- Original `esp32_preflight_results.zip`: 75,351 timer/cache rows with per-event ISR entry, period, dispatch latency, work duration.
- `zeroplus_11nov.zip` reconstructed via 25 MSa/s, compressed 32K experimental `.alc` decoder; analyzed `all_high_pulses.csv` and `all_rising_periods.csv`. Timebase cross-checked on SPI. **External timings elsewhere remain provisional pending independent ZEROPLUS spot checks.**
- `esp32_benchmark_logged.ino` source; no code changes applied.
- These are separate acquisitions, not globally synchronized runs. We compare within each file and independent patterns, never pair per-event internal/external times across separate sessions.

## H1: High-stress dispatcher backlog — supported strongly, but not uniquely explained
Firmware: ISR timestamps enqueue events in ring and notifies dispatcher; P22 stress task competes with P22 dispatcher on core 0; dispatcher can drain ring without blocking between entries. For each on-chip event i, compare the next ISR entry time `t_ISR[i+1]` with `t_ISR[i] + dispatch_latency[i]`. If next ISR is earlier, the current event had NOT reached dispatch start before another interrupt. High-stress: **53.36%** of adjacent-event pairs; baseline/warm/cache-only: **0%**. This directly demonstrates temporal backlog under high stress. Some high-stress latencies are <10us (~10.5%) although baseline has 0%; consistent with already-running dispatcher/ring-drain but that mechanism is NOT directly tagged per event, so cannot prove it solely from these durations. Current event backlog and frequent high latencies are real.

## H2: 20-event recurrence — real, attribution unresolved
Autocorrelation of on-chip ISR-to-task latency at 19/20/21 events: baseline ~0.009/0.802/0.013; warm ~0.003/0.823/-0.020; high stress ~-0.128/0.174/-0.011. Strong, sharp lag-20 preference, repeated also at lag 40 (~0.73 baseline). Work durations have NO lag-20 recurrence under baseline/warm (work r20 approx 0), undermining the hypothesis that variable-duration flash loads alone drive the pattern. A 1 kHz FreeRTOS tick and a 20-entry output LUT both match 1ms at 50us events; cannot distinguish from existing fixed-LUT captures. Firmware's `j` toggles the output to fast GPIO25 level switching, without changing timer; an A/B comparison could challenge the LUT hypothesis. Need confirm actual FreeRTOS tick rate and timing phase.

## H3: Cache multimodality from ISR overlap — new independent electrical evidence
Use two same-capture signals: GPIO22 A1 HIGH brackets timed flash-work section; GPIO19 A2 HIGH marks ISR entry/body. In target-16-line capture, **43.35%** of A1 pulses include an A2 rising edge. A1 width mean is **27.12us** with overlap versus **15.26us** without, a difference of **11.86us**. Baseline_02 (cold-like) shows 43.15% and 27.47 vs 15.28us. Highstress_02 (cold-like) shows 48.06% and 32.21 vs 15.75us. Target-8-line captures show only **3.67%** overlap, 19.32 vs 15.64us. Warm and 2-line modes show **zero observed overlap**. This is a strong, observable explanation for (at least part of) the bimodal A1 pulse width distributions: when an ISR interrupts the running workload, the measured wall duration includes interrupt time. **But** an ISR may also be delayed until after memory/cache work; low observed overlap therefore does NOT prove no contention. Cache invalidation occurs *before* A1 HIGH and is omitted from flash_work timing; it may disturb interrupt delivery or create phase-locking. The external A1 pulse is not the same boundary as internal `flash_work_us`; do not numerically equate without matched event markers.

## H4: Cache work / interrupt period lead-lag association — supported, not causal
Across ten original target-16-line runs, current flash-work duration vs ISR period for same indexed event has correlation +0.759; vs next ISR period -0.760; vs period after next +0.650. Following mean period ~41.44us after preceding `flash_work_us >23us`, and ~56.96us after <=23us (example run). This strong alternating lag pattern indicates a phase-locked or timing-interference sequence, but neither causality nor specific DPORT operation is proven. On-chip timestamp order shows next ISR before estimated current callback finish in **at least 35.40%** of target-16-line samples using only dispatch time + measured work duration; actual including preceding cache invalidation may be more. For 8-line target this lower-bound overlap measure is 2.13%, warm ~0. (These are event-order proxies, not counts of hardware interrupt masking.)

## H5: stress + cache-state carryover — confirmed firmware confound, capture attribution inferred
Stress commands 1–5 do not reset `active_cache_mode`, whereas `u/m/t/7` assign it and start timer. A1 pulse distribution matches warm for Baseline_01, cold-max for Baseline_02; similar split between high-stress captures, medium stress both cold-like. Thus the six external stress captures are not replicated identical-cache runs. State should be set explicitly before every stress run. Their contrasts may be presented as exploratory combined conditions with inferred configuration, not as a prospective factorial randomized experiment.

## High-value LAB plan — priority order, no new firmware required
Keep original Setup A analyzer wiring: A0=GPIO25, A1=GPIO22, A2=GPIO19, A3=GPIO21, A4=GPIO18, A5=GPIO23, A6=GPIO27, A7=GPIO5; analyzer GND->ESP32 GND. 25 MSa/s, 32K compressed, one ~100–200ms stored trace each. Use A2 rising trigger for all 50us timer runs; 10–20% pretrigger. Save native ALC, screenshot of key overlap pulses, and after capture send `g` to STOP+export raw on-chip samples. Do not send `g`, `s`, or UART commands during capture. Reset/cold-stage with `u` or `7` explicitly before every stress command. For each run: send `0`; send cache choice (`u` or `7`); send stress choice (`1` or `5`); after 1s steady operation ARM and CAPTURE at A2; then send `g` and store on-chip CSV. Repeat each condition ideally 2–3 times. Randomize block order ABBA if practical; label/cache/stress and run order. Conditions:
1. `u` -> `1` (baseline + warm)
2. `7` -> `1` (baseline + cold-max)
3. `u` -> `5` (high stress + warm)
4. `7` -> `5` (high stress + cold-max)
This is the single most important revisit: tests stress/cache *interaction* while removing the persistent-setting ambiguity; also enables paired on-chip/external event timing within each run.

Then optionally:
5. Repeat standalone `t` and `7` (2 captures each) with A2 trigger; compare A1 work pulse widths with/without coincident A2 ISR, and times immediately *preceding* A1 when flush happens. Goal: separate real ISR preemption of marked work from delayed ISR until after unmarked flush. Optional source instrumentation would be needed to time `hw_invalidate_pro_cache` explicitly; do not change main benchmarking firmware merely for this without versioning/recompiling.
6. Test 1ms periodicity with `j` command toggling fast GPIO25 output; run warm baseline with LUT (`u` -> `1`) and with fast toggle (`0`, `j`, `u`, `1`). Preserve which output mode is active: `j` toggles; reset if unsure. Capture A2 and export `g` for both. If lag-20 latency recurrence persists unchanged, LUT *waveform selection* alone is unlikely cause. This does not exclude tick or shared driver phase.
7. Bonus: reset board then capture *first* `d` followed by second `d`, using A0 rising and 10ms capture; record corresponding Serial queue duration. Tests external steady-state first-use effect (~226us to ~83us); the first-run capture already exists, second missing.

Minimum commitment if short time: four controlled stress×cache combinations once each plus original and software cycle logs; do not prioritize medium stress P10 since dispatcher priority P22 and it cannot preempt dispatcher by normal priority scheduling. Repeat each condition if time permits. Avoid novelty claims until these confounds and parser uncertainty are addressed.

## Caveats and reproducibility
- External `.alc` decoding assumes a reverse-engineered compressed-record duration code; representative native ZEROPLUS spot checks outside SPI remain desirable.
- `A1` HIGH is a measured envelope, not isolated cache-miss time, and its value includes ISR preemption when a GPIO19 ISR occurs while HIGH.
- On-chip `work_us` includes GPIO22 writes but excludes cache invalidation and any setup before it.
- Correlations of consecutive ISR periods partly reflect differences of successive timestamp errors and temporal dependence.
- Same capture has many correlated events; the true experimental replicate is a separately started run.
