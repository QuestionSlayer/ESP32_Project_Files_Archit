# Format audit against PROFESSOR_REQUIREMENTS.md

| Requirement | Status | Evidence |
|---|---|---|
| One readable .tex source, one author | Met | `output/ESP32_Project_Report.tex` (13,100 lines; prose, then 71 embedded data/source files via filecontents*). Author fields are placeholders to fill |
| Compiles cleanly | Met | Clean directory, `pdflatex` x3 only: exit 0, 122 pages, 0 undefined references, 0 undefined value keys; same text on every page as the multi-file build (the delivered PDF is the one built from the single file) |
| A4, 12 pt, 1 in margins, single spacing, two-sided | Met | `\documentclass[12pt,a4paper,twoside,openany]{report}`, `geometry` margin=1in, `\linespread{1.0}`; PDF page size 595.28 x 841.89 pt |
| Page 1 title, one author | Met (placeholders) | `\authorname`, `\entrynumber`, `\submissiondate` in the first lines after the preamble |
| Page 2 copyright assignment | **Blocked** | Labelled placeholder box; official IITD wording not supplied, none invented |
| Page 3 acknowledgments, Dept. of EE and IIT Delhi | **Partly blocked** | Institutional sentence present; names to be written by the author |
| Generated ToC, LoF, LoT, index, glossary | Met | 25 figures, 21 tables, 20 acronyms, 15 glossary terms, 2-column index; all non-empty |
| Sec. 1.1 relevance to ELL305, textbook cited | Met | Sec. 1.1, Table 1.1; section numbers checked against the supplied PDF |
| Sec. 1.2 significance, at least 300 words | Met | 488 words of prose, counted by `readability.py` |
| Appendix A Turnitin report | **Blocked** | Placeholder; `turnitin_report.pdf` is included automatically when placed beside the source |
| Appendix B reading indices with calculation and values | Met, to confirm | Formulae and values computed from the final prose; confirm whether the course prescribes a specific tool |
| Full firmware and all Python in appendices | Met, one choice to confirm | Original firmware in full; diagnostic firmware as a complete unified diff (set `\fulldiagtrue` to print it in full, about 27 more pages); nine analysis programs and the two host loggers in full |
| 5-12 line excerpts beside the prose | Met | 14 excerpts read from the archived files by line range (never retyped); one is 13 lines |
| Diagrams from text | Met | TikZ / CircuiTikZ / PGFPlots only; `pdfimages` finds 0 bitmaps |
| Code via listings or minted | Met for excerpts | Excerpts use `listings`. Full-file appendix listings use `fvextra` (the verbatim engine underneath minted) because `listings` with line breaking exceeded TeX's default memory |
| Main text 30-35 pages | **Over** | 43 pages (Chapters 1-11). See OPEN_ISSUES.md |
| No undefined references, no clipped figures | Met | Every page of Chapters 1-11 rendered and inspected; remaining overfull boxes are under 2.2 pt |

Fonts embedded: URW Palladio (Palatino), Pazo Math, Nimbus Sans (Helvetica), Latin Modern Mono, CM/AMS symbols.
