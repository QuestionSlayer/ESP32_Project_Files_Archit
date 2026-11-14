#!/usr/bin/env python3
"""Render all .mmd diagrams with Mermaid CLI (`npm i -g @mermaid-js/mermaid-cli`).
Usage: python scripts/render_mermaid.py diagrams/mermaid figures/diagrams
"""
import subprocess,sys,shutil
from pathlib import Path
source=Path(sys.argv[1]) if len(sys.argv)>1 else Path('diagrams/mermaid')
target=Path(sys.argv[2]) if len(sys.argv)>2 else Path('figures/diagrams')
if not shutil.which('mmdc'): raise SystemExit('Mermaid CLI not installed: npm install -g @mermaid-js/mermaid-cli')
target.mkdir(parents=True,exist_ok=True)
files=list(source.glob('*.mmd'))
if not files: raise SystemExit(f'No diagrams in {source}')
for f in files:
    out=target/(f.stem+'.svg')
    subprocess.run(['mmdc','-i',str(f),'-o',str(out),'-b','transparent'],check=True)
    print('Created',out)
