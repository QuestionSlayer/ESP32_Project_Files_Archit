# Open issues

## Must be supplied by the author before submission
1. Author name, entry number, date: three `\newcommand` lines after the preamble.
2. Official IIT Delhi copyright-assignment text and signature (page 2).
3. Acknowledgments (page 3), and any AI-use statement the Institute requires. This report's prose, analysis
   and figures were produced with an AI system; disclose that as your course's rules require.
4. Turnitin report: save as `turnitin_report.pdf` beside the .tex and recompile.
5. Confirm whether Appendix B must use a prescribed reading-index tool.

## Decisions taken that you may want to reverse
- **Length.** Chapters 1-11 run to 43 pages against a 30-35 page target. The re-analysis added material
  (decoder correction, polling loss, double entry, tick test). Cheapest cuts, in order: Table 9.1 (replication
  design); Fig. 6.1 and Fig. 8.1 (conceptual); Sec. 3.6; Table 10.1 or 10.2; Sec. 5.5 merged into 5.4.
  Together about 3 pages. Reaching 35 would need whole results removed.
- **Fonts.** Libertinus / STIX Two / Inconsolata were not installed and could not be downloaded. The report
  uses Palatino (mathpazo), Helvetica and Latin Modern Mono under pdfLaTeX. Switching fonts changes line and
  page breaks, so every page would need re-inspection.
- **Diagnostic firmware as a diff** rather than a second 1500-line listing (`\fulldiagtrue` reverses it).
- **Fig. 9.2 (run-level dot plot) was dropped** to save space; Table 9.2 carries the same numbers.

## Scientific loose ends (none blocks submission)
- Handoff UART service times 108.86 / 42.72 / 39.68 µs have no source file in the archive; not used.
- "IDF driver refills before clearing the interrupt" (Sec. 5.3) should be checked against the IDF version used.
- The canonical ChatGPT "living Page" referenced by the handoff was not accessible and was not read.
- 12-Nov captures `71` and `75` were taken with invalidation off; they are used only in Table 4.2.
- claims_registry.yaml / figure_registry.yaml in the handoff are superseded by FIGURE_SOURCE_MAP.csv,
  claim_to_evidence.csv and report Table 10.2; the originals were left untouched.
