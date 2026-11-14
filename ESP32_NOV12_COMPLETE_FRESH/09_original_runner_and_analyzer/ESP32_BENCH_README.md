# ESP32 benchmark logging toolkit

## Files
- `esp32_benchmark_logged.ino`: updated Arduino firmware with `g` (dump raw timer samples **after stopping**) and `q` (automation acknowledgement).
- `run_esp32_benchmarks.py`: opens USB serial, runs named test commands, captures raw serial logs, makes one sample CSV per timed run and a transfer trial CSV, then exits.
- `analyze_esp32_benchmarks.py`: statistics, histograms, time-series latency plots, and optionally physical logic-analyzer edge waveforms.

## Install

```bash
python -m pip install pyserial matplotlib
```

Upload `esp32_benchmark_logged.ino` to your ESP32 using Arduino IDE, **close Arduino Serial Monitor**, and use a PC terminal:

```bash
# Windows example: change COM5 to your board's port
python run_esp32_benchmarks.py --port COM5 --repeats 20 --duration 0.10 \
  --tests poll,interrupt,dma,stress1,stress2,stress3,stress4,stress5,stress23,cache_warm,cache12,cache50,cache100,spill

# Linux example
python run_esp32_benchmarks.py --port /dev/ttyUSB0 --repeats 20 --duration 0.10

# macOS example
python run_esp32_benchmarks.py --port /dev/cu.usbserial-0001 --repeats 20
```

**Don't run Arduino Serial Monitor concurrently:** only one process should own the port. Opening the port may reset the board; the script waits briefly after opening. The ESP32 transmits no sample data during active acquisition: it holds a rolling 2048-sample buffer in SRAM and exports it after the timer and stress workers stop. Default acquisition window is 0.10s (2000 ideal timer ticks at 50µs); longer runs retain just the last 2048 samples. All individual runs are kept as separately numbered files. A 20-run trial has about 40,000 timer samples per test, but with pauses between repetitions.

## Analyze

```bash
python analyze_esp32_benchmarks.py bench_results/20261110_220000
```

The resulting `analysis/` folder contains `timer_statistics.csv`, `pooled_timer_statistics.csv`, `transfer_statistics.csv`, histograms, and the measured timer latency-versus-time plot. Sample standard deviation is used; the scripts preserve per-run distributions as well as pooled results. The `_samples.csv` files are real recorded ESP32 timestamp-derived values; the plots are not physical digital waveforms.

## Digital edge traces from your external logic analyzer

**Use the analyzer to record actual transitions.** Attach analyzer ground and probes to ESP32 GPIO25 (frame), GPIO22 (instrumented CPU service), GPIO19 (ISR), GPIO23 (MOSI), GPIO27 (MISO), GPIO18 (SCLK), and GPIO5 (CS). Connect a **single physical jumper GPIO23 -> GPIO27** for SPI loopback; the analyzer inputs do not drive signals. Both the board and analyzer must use compatible 3.3V levels. Keep probes short and common-grounded.

Export your logic-analyzer capture as CSV, in either:
1. Edge events: `time_s,channel,edge` where `edge` is rising/falling, or `time_s,channel,level` with new 0/1 level after each transition.
2. Sampled digital format: `Time [s],Channel 0,Channel 1,...` with 0/1 levels; the analysis script detects changes.

Then run:

```bash
python analyze_esp32_benchmarks.py bench_results/20261110_220000 --edges your_analyzer_export.csv \
   --channel-map "0=GPIO25,1=GPIO22,2=GPIO19,3=MOSI,4=MISO,5=SCLK,6=CS"
```

The analyzer produces `logic_edges_normalized.csv`, `logic_edge_statistics.csv`, `logic_waveform.png`. The script does not communicate with the ZEROPLUS software or automatically arm/start the analyzer. Export each analyzer capture separately and run analysis with each capture; manually label runs and ensure the command/test mapping matches the hardware capture. A generic sampled CSV often omits intermediate transitions if its sampling rate is too low. Edge timestamps have the logic analyzer's timebase; the ESP32's CPU timestamps are a separate timebase and cannot be precisely aligned without a shared synchronization edge.

## Interference and limitations

- There is **no Serial print and no GPIO transition logging within the periodic ISR** beyond its preexisting marker and timestamp ring writes. The dispatcher already wrote three measurements per sample; firmware adds **one SRAM write per sample** for the ISR entry timestamp. That does add a small deterministic overhead, so compare runs on the **same firmware** and measure baseline overhead.
- No exact GPIO edge list is collected on-chip. Polling or interrupting per edge would perturb the experiment. The external analyzer is preferred.
- Physical logic analyzer edge timing and ISR/dispatcher CPU-cycle timing are different observations. The onboard `isr_time_relative_us` is reconstructed from wrapping 32-bit CPU cycle counts and is valid across the short retained window, not as an absolute timestamp.
- The 0%, 12.5%, 50%, and 100% cache names are **target access patterns**, not measured miss rates.
- CPU service/wall is **not OS-wide CPU utilization**. DMA mode blocks instead of spinning, but FreeRTOS runtime accounting is required for a real utilization percentage.
- SPI DMA payload verification requires the GPIO23→GPIO27 jumper. A PASS requires exact 512-byte RX/TX equality and driver completion; it doesn't establish link quality with an external SPI slave.
- The forced spill benchmark measures explicit `xthal_window_spill()` overhead, not an isolated and guaranteed ISR-to-dispatcher effect.
- These files have been syntax-checked as Python and the analysis script exercised with **synthetic test CSVs**. **ESP32 firmware has not been compiled or validated on hardware**, and the serial runner has not been tested against your specific USB device/ZeroPlus analyzer.

## Preflight fix (November 10)
The timer-mode runner now sends a bare start byte and **no `q` acknowledgment during acquisition**. It waits, sends `0q` to stop and acknowledge, then requests `g` for a post-stop raw dump. This avoids Serial ACK interference while sampling. The firmware already flushes configuration text before the GPTimer begins.
