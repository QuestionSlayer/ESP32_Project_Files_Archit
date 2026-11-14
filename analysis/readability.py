"""Reading indices for the main text (Appendix B).

Input : report/ch01.tex ... ch11.tex with value macros expanded.
Output: build/results/readability.json  (keys ri.* in numbers.tex)

Only running prose is counted.  Figures, tables, listings, displayed
equations, captions, headings and comments are removed before counting.
Sentences end at . ! or ? followed by whitespace and a capital or the end of
a paragraph.  Syllables are counted by vowel groups with the usual silent-e
and -le/-ed/-es adjustments; a "complex" word has three or more syllables.
The syllable counter is a heuristic and is the main source of error.
"""
import re, json, sys
from common import *

REPORT = WORK / "report"
vals = dict(l.split(" = ", 1) for l in (BUILD / "numbers_all.txt").read_text().splitlines() if " = " in l)


def strip_tex(t):
    t = re.sub(r"(?<!\\)%.*", "", t)
    for env in ("figure", "table", "align", "equation", "tabular", "tabularx", "lstlisting", "itemize"):
        if env == "itemize":
            continue                                   # list items are prose
        t = re.sub(r"\\begin\{%s\*?\}.*?\\end\{%s\*?\}" % (env, env), " ", t, flags=re.S)
    t = re.sub(r"\\(chapter|section|subsection|paragraph)\*?\{[^}]*\}", " ", t)
    t = re.sub(r"\\(input|label|index|fw|fwd)\{[^}]*\}(\{[^}]*\})?", " ", t)
    t = re.sub(r"\\(cref|Cref|ref|cite)\{[^}]*\}", "X", t)
    t = re.sub(r"\\(?:us|ms|pct|cyc|Vn|V)(?:\[[^\]]*\])?\{([^}]*)\}", lambda m: "5", t)
    t = re.sub(r"\\(SI|SIrange|SIlist|num|usn|msn)(\[[^\]]*\])?(\{[^}]*\})+", "5", t)
    t = re.sub(r"\\(code|cmd|pin|texttt)\{[^}]*\}", "code", t)
    t = re.sub(r"\$[^$]*\$", "x", t)
    t = re.sub(r"\\(emph|textbf|textit|textsf)\{([^}]*)\}", r"\2", t)
    t = re.sub(r"\\(begin|end)\{[^}]*\}", " ", t)
    t = re.sub(r"\\item\b", " ", t)
    t = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", t)
    t = re.sub(r"[{}~]", " ", t)
    t = t.replace("``", '"').replace("''", '"').replace("\\", " ")
    return t


def syllables(w):
    w = re.sub(r"[^a-z]", "", w.lower())
    if not w:
        return 0
    if len(w) <= 3:
        return 1
    n = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and not w.endswith(("le", "ee", "ie")):
        n -= 1
    if w.endswith(("ed", "es")) and not w.endswith(("ted", "ded", "ses", "ces", "zes", "ges", "xes", "ies")):
        n -= 1
    return max(n, 1)


def measure(text):
    paras = [p for p in re.split(r"\n\s*\n", text) if re.search(r"[a-zA-Z]{3}", p)]
    sents = 0; words = []
    for p in paras:
        p = " ".join(p.split())
        s = [x for x in re.split(r"(?<=[.!?])[\"')\]]*\s+(?=[A-Z\"(])", p) if re.search(r"[a-zA-Z]", x)]
        sents += len(s)
        words += re.findall(r"[A-Za-z][A-Za-z'\-]*", p)
    W = len(words); S = max(sents, 1)
    syl = [syllables(w) for w in words]; Sy = sum(syl)
    cx = sum(1 for w, k in zip(words, syl) if k >= 3)
    return {"words": W, "sentences": S, "syllables": Sy, "complex_words": cx,
            "words_per_sentence": W / S, "syllables_per_word": Sy / W,
            "flesch_reading_ease": 206.835 - 1.015 * W / S - 84.6 * Sy / W,
            "flesch_kincaid_grade": 0.39 * W / S + 11.8 * Sy / W - 15.59,
            "gunning_fog": 0.4 * (W / S + 100.0 * cx / W)}


R = {"chapters": {}}
alltext = ""
for i in range(1, 12):
    t = strip_tex((REPORT / f"ch{i:02d}.tex").read_text())
    alltext += "\n\n" + t
    R["chapters"][str(i)] = measure(t)
R["all"] = measure(alltext)
raw = (REPORT / "ch01.tex").read_text()
m = re.search(r"\\section\{Significance of the Project\}(.*?)\\section\{", raw, flags=re.S)
R["sec12_words"] = measure(strip_tex(m.group(1)))["words"]
save_results("readability", R)
a = R["all"]
print(f"words {a['words']} sentences {a['sentences']} w/s {a['words_per_sentence']:.1f} syl/w {a['syllables_per_word']:.2f} FRE {a['flesch_reading_ease']:.1f} FKGL {a['flesch_kincaid_grade']:.1f} Fog {a['gunning_fog']:.1f} | sec 1.2 words {R['sec12_words']}")
