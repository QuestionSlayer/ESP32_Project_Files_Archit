# ESP32 diagnostic preflight: quantitative findings

**Dataset:** 8 conditions, one sequential run per condition, each 1,024 retained events. All combined CSVs parse with contiguous indices and no NaN; `summary.json` labels every run PASS. These are the **last** 1,024 samples of acquisitions that processed approximately 14k events per condition, not full-session records. No simultaneous ZEROPLUS waveforms included in this ZIP.

## Most important controlled observation

| condition | abs ISR jitter mean | load duration mean | flush cost mean | full callback mean | ISR load-overlap |
|---|---:|---:|---:|---:|---:|
| cache50_on | 9.281 µs | 10.941 µs | 4.231 µs | 16.159 µs | 3.6% |
| cache50_off | 0.769 µs | 10.692 µs | 0.094 µs | 11.700 µs | 0.0% |
| cache100_on | 6.463 µs | 23.308 µs | 4.246 µs | 28.634 µs | 41.1% |
| cache100_off | 5.872 µs | 20.574 µs | 0.094 µs | 21.667 µs | 3.3% |

- Disabling flush reduces 8-line jitter 9.281→0.769 µs (~91.7%), but 16-line jitter only 6.463→5.872 µs (~9.1%). Thus flush ON/OFF has qualitatively different impacts on observed ISR timing under the two access patterns.
- Crucially, **non-overlapped load duration is almost unchanged** across flush ON/OFF: cache50 10.647 µs (ON, no ISR in load) vs 10.692 µs (OFF, all); cache100 20.167 µs (ON, no ISR) vs 20.232 µs (OFF, no ISR). This challenges a claim that the mode separation directly measures first-touch cache misses after invalidation. Loop instruction/address sequence or flash-data placement may dominate. Disabling flush does not make the access pattern identical between 8 and 16 lines.
- The flush API itself takes ~4.23–4.25 µs (ON), versus no-op diagnostic interval ~0.094 µs (OFF). Without full CPU/cache register verification, do not infer exactly which cache lines were invalidated or that misses were 50%/100%.

## Interrupt overlap explains most of cache100 ON load-width bimodality

- cache100_on: without ISR n=603 mean=20.167 µs, with ISR n=421 mean=27.806 µs.
- cache50_on: without ISR n=987 mean=10.647 µs, with ISR n=37 mean=18.773 µs.
- cache100_off: without ISR n=990 mean=20.232 µs, with ISR n=34 mean=30.534 µs.
- stress5_cold: without ISR n=533 mean=20.171 µs, with ISR n=491 mean=31.227 µs.

This directly supports ISR overlap extending the measured load interval; it does not explain a cache refill penalty independent of ISR, and the counter relies on ISR access to the diagnostic state.

## Stress and ring depth

- stress1_warm: mean dispatch 13.414 µs, SD 1.264 µs; depth>0 0.0%; latency<10 µs 0.0%.
- stress5_warm: mean dispatch 56.231 µs, SD 35.265 µs; depth>0 54.4%; latency<10 µs 7.6%.
- stress1_cold: mean dispatch 14.177 µs, SD 5.838 µs; depth>0 0.0%; latency<10 µs 28.2%.
- stress5_cold: mean dispatch 63.568 µs, SD 42.085 µs; depth>0 58.6%; latency<10 µs 8.8%.

**Correction to earlier hypothesis:** In BOTH high-stress runs, every fast (<10 µs) event has `ring_depth_after_pop == 0`; none of the events with a nonzero ring depth are fast. Ring depth strongly tracks *large* latency instead: warm high stress mean latency by depths 0,1,2,3 is about 23,74,110,168 µs; cold high stress 22,74,119,169 µs. This conflicts with the earlier prediction that unusually fast events would coincide with nonempty ring depth, although ring depth measured after the pop cannot establish whether the task was already running.

## Data caveats
- Single recording per condition; 1,024 adjacent events are dependent, and there are no independent repetitions for variance across runs or confidence intervals.
- Cache OFF may still incur cache misses through other mechanisms; cache ON invalidation also perturbs unrelated code/data residency. A source-level/ELF audit of `flash_rodata_table` placement and the generated loops is high priority.
- `isr_during_flush` is zero in all four standalone cache conditions, but is nonzero in stress5_cold; zero cannot establish that interrupts were unaffected during flushing (interrupts could be deferred).
- A few measurements show marked callback durations exceeding the 50 µs timer; ring-depth records and ISR counters must be checked before attributing such events to pure cache behavior.
- The ZIP has no `d`, `y` or `z` trials, so it cannot diagnose first-run SPI DMA or DAC output timing. Use their separate lab `.alc`/serial logs.
