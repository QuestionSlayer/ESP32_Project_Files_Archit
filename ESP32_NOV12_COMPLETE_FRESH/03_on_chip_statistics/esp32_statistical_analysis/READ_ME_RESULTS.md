# ESP32 preflight: statistical reanalysis

Source: user-supplied `esp32_preflight_results.zip` (2026-11-10, run folder `20261110_221648`). The analysis uses only existing CSV exports and does not include ZEROPLUS `.alc` captures.

## Samples and availability
- 75,351 exported raw timer samples across 59 valid timer/cache runs (10 baseline, 10 high stress, 9 warm cache, and 10 each of 12.5%, 50%, and 100% targeted cold-line conditions).
- 50 transfer/register trial records: 20 SPI DMA, 10 UART polling, 10 UART IRQ, and 10 register-spill.
- `cache_warm_005` had a one-row mismatch and its entire sample file was omitted from the combined raw CSV; review the original serial log before claiming 10 valid warm runs.
- All 20 original preflight SPI DMA trials reported payload mismatch; do **not** use them as passing integrity tests. Later 3 PASS runs were given as Serial text in the conversation; their exact data are not in the preflight ZIP.
- This dataset does not include intermediate stress level `3`, UART burst-size sweep, DAC experiments, hardware edge traces, or true CPU utilization.

## Principal results
- Baseline ISR period: mean 50.051 µs, event SD 0.670 µs, mean absolute jitter 0.173 µs, P99 absolute jitter 3.950 µs.
- High-stress ISR period: mean 50.052 µs, event SD 1.706 µs, mean absolute jitter 0.879 µs, P99 absolute jitter 5.913 µs.
- Baseline dispatcher latency: mean 13.224 µs, SD 1.268 µs, P95 13.981 µs, P99 21.094 µs.
- High-stress latency: mean 53.664 µs, SD 33.237 µs, P95 106.839 µs, P99 113.169 µs.
- High-stress latency exceeded the nominal 50 µs event interval in 7,314/13,715 observations (53.33%), compared with zero baseline observations. This is not automatically a deadline miss rate.
- Run-level mean difference in dispatcher latency (high - baseline) 40.426 µs; illustrative 95% bootstrap CI 40.213 to 40.643 µs, resampling ten runs per condition. Interpret cautiously if runs were performed sequentially or instrument settings changed.
- Cache workload event means: warm 0.999, targeted 2 lines 3.414, 8 lines 10.968, 16 lines 23.371 µs. Linear descriptive fit across **four condition means**: intercept 0.604 µs, slope 1.398 µs / targeted cold line, R² 0.9967. This is not a measured hardware cache miss rate, and four design points cannot validate the model broadly.
- Original preflight DMA queue interval first run 223.71 µs, trials 2–20 average 83.333 µs, SD 1.573 µs. Wall time first run 5347.71 µs, trials 2–20 mean 5210.384 µs, SD 1.494 µs. The first run has a repeatable-seeming warm-up effect, but the preflight series has failed loopback payloads.
- UART 16B interrupt results from preflight: 48 interrupts, reported 70.91 µs ISR service time; 10 repeated outputs were **identical** for these service measurements. Likewise, each of 10 register-spill reports was identical (261/621/2116 cycles). Their zero observed SD is an instrumentation/aggregation issue or precision limitation, not evidence of zero true variability.

## Adjacent-jitter caution
Runwise correlation between signed successive ISR-period errors: average -0.518 baseline, -0.473 high stress. A negative correlation is **expected mathematically** when each measured period is a difference between successive event timestamps, even if independent timestamp delays cause no physical compensation (the shared middle timestamp contributes with opposite signs). Do not attribute negative correlation directly to a catch-up mechanism without further tests.

## Major limitations
- Repeated timer samples from one run are autocorrelated. Do not use pooled event N as independent run N for statistical inference. The bootstrap is based on run means and should still be treated as conditional on the actual run design.
- Timer reports measure **software ISR-entry timestamps**, not the precise hardware timer alarm edge.
- `flash_work_us` measures the coded load loop, with possible confounding by cache-controller operations, Flash execution, interrupts and measurement overhead. Cold-line target percentages are not measured miss rates.
- Queue CPU intervals and ISR service intervals are instrumented intervals, not actual CPU utilization.
- `wall_us` for UART and SPI reflect different peripherals, so direct throughput comparisons are not controlled.
- Strong quantization and perfectly repeated numbers in transfer and register experiments limit uncertainty claims.
- DAC outputs are analog; digital thresholds alone don't establish waveform amplitude or full settling time.

## ZEROPLUS exports needed
1. Stress (`1`,`3`,`5`): GPIO19 rising-edge timestamps for period/jitter; GPIO22 work pulses and GPIO25 digital-LUT transition timestamps to check output jitter. Repeated waveform captures can validate mean/SD/tails and long-short patterns. Exact ISR→dispatcher delay requires a marker specifically at dispatcher entry or matching internal per-event timestamps.
2. Cache (`u`,`m`,`t`,`7`): GPIO22 high-pulse widths, one or more captures for each, to compare against `flash_work_us`.
3. UART (`p`,`i` all bursts): GPIO25 transfer window; GPIO22 service high times; GPIO19 ISR rising-edge timestamps and widths; GPIO21 UART data bits/decoder. Last ISR relative to UART last bit can help investigate terminal gap.
4. SPI DMA (`d`): GPIO22 queue pulse; GPIO25 transaction; GPIO19 callback; GPIO18 SCLK; GPIO5 CS; GPIO23/27 MOSI/MISO. Measure first/last SCLK, CS timing, service versus on-wire duration; decode payload. A single successful run does not establish first-run cold-start effect. For that, correlate captures with trial sequence or serial run logs.
5. DAC (`v`,`w`,`f`,`x`,`y`,`z`): GPIO22 feeder timestamps/pulse widths, GPIO25 threshold transitions, compare equal-duration feeder event rates and output-step delay, and examine continuity around the long `z` stall. It remains digital-threshold evidence, not analog amplitude measurement.
6. Register spilling (`r`): GPIO22 interval durations for each of the three 1,000-iteration blocks, across independent `r` executions if available, to estimate variation. No channel identifies an isolated actual register overflow handler.

## Contents
- `plots/`: analysis graphs
- `pooled_event_statistics.csv`: pooled event distributions (descriptive only)
- `run_level_distribution_statistics.csv`: independent-run summaries
- `between_run_means.csv`: variations of run means
- `adjacent_jitter_analysis.csv`: runwise lag-1 correlation and long-short tests
- `latency_threshold_exceedance.csv`: >50 µs counts
- `transfer_statistics.csv`, `dma_trial_statistics.csv`, `measurement_resolution_audit.csv`
- `summary.json`: machine-readable summary
- `analyze.py`: reproducible calculation source
