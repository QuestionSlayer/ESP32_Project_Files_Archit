# ESP32 research report handoff — consolidated evidence package

Prepared from original project artifacts and existing analyses. The package does **not** constitute newly run hardware experiments.

## Where to start

1. `reports/ESP32_IEEE_Report_Writing_Blueprint.pdf` — chapter/subsection/figure plan.
2. `reports/RESEARCH_EVIDENCE_SUMMARY.md` — established findings, caveats and unresolved questions.
3. `data/raw/esp32_preflight_results.zip` — original device serial logs and timing CSVs.
4. `data/raw/zeroplus_11nov.zip` — all original logic-analyzer `.alc` captures.
5. `data/processed/` — preserved statistical and external wave analyses, with their own scripts.
6. `scripts/generate_report_figures.py` — redraw editable-equivalent plots from CSV.
7. `diagrams/mermaid/*.mmd` — software timing/control-flow diagrams.

## Regenerate a timing waveform figure

```
python -m pip install numpy pandas matplotlib
python scripts/generate_report_figures.py --edges data/processed/external_logic_analysis/converted_edges/01_Transfer/SPI_DMA_01/digital_edges.csv --channels A0,A1,A2,A4,A7 --start-us 67000 --duration-us 6000 --output figures/derived/spi_dma_timeline.pdf
```

## Generate a latency ECDF

Unpack `data/raw/esp32_preflight_results.zip` (into `data/raw/unpacked/`), then:
```
python scripts/generate_report_figures.py --samples data/raw/unpacked/esp32_preflight_results/20261110_221648/all_timer_samples.csv --output figures/derived/stress_latency_ecdf.pdf
```

## Generate pulse-width histograms

```
python scripts/generate_report_figures.py --pulse-csv data/processed/external_logic_analysis/zeroplus_analysis/all_high_pulses.csv --capture 03_Cache --channel A1 --output figures/derived/cache_width_hist.pdf
```

## Render editable Mermaid diagrams

```
npm install -g @mermaid-js/mermaid-cli
python scripts/render_mermaid.py diagrams/mermaid figures/diagrams
```

## Research integrity / critical caveats

- The `.alc` converter is a reverse-engineered **experimental** parser. It was spot-checked against SPI captures; check other sampling settings against native ZEROPLUS.
- Original 20 DMA automated preflight runs failed loopback checks; later **separate** three runs passed 512/512. Never combine integrity claims from the two series.
- Stress modes preserve prior cache mode; some baseline/high/medium external captures appear to have inherited cold-cache configuration. Treat as mixed conditions, not matched replicates.
- Cache patterns target 0/2/8/16 cache lines, **not directly measured hardware miss rates**. Whole-cache invalidation precedes measured GPIO22 span. ISR preemption can extend pulse widths.
- Hardware ISR GPIO markers are software ISR-entry markers, not timer alarm edges; dispatch latency is ISR entry to dispatcher timestamp, including scheduler and backlog.
- SPI and UART are separate peripherals and cannot support a same-peripheral throughput claim.
- Software service-time fractions are **not** full CPU utilization.
- DAC output threshold lag is not analog voltage settling; feeder stall is not independently verified hardware underrun.
- Register forced spill timings include call/recursion/instrumentation effects, not pure Xtensa exception handler latency.
- Original screenshot filenames come from this conversation and may not directly index unique ALC captures; use `data/raw/zeroplus_11nov.zip` for canonical capture source.

## Persistent live insights record

https://chatgpt.com/space/page_0cea1fd7efd081918aac0c985ad91044

This page may contain later discoveries and should be consulted before finalizing manuscript claims.

## Completeness check

See `MANIFEST.csv` for every packaged file, size, and SHA-256 digest. `PACKAGE_INDEX.json` lists categories and contents.
