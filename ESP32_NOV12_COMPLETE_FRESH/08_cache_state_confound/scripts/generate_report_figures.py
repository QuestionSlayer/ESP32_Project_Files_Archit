#!/usr/bin/env python3
"""Reproducible ESP32 report illustrations from CSV measurements.

Requires: pip install numpy pandas matplotlib

Examples:
  python scripts/generate_report_figures.py --edges data/processed/converted_edges/01_Transfer/SPI_DMA_01/digital_edges.csv --channels A0,A1,A2,A4,A7 --start-us 67000 --duration-us 6500 --output figures/spi_dma_timeline.pdf
  python scripts/generate_report_figures.py --samples path/to/all_timer_samples.csv --output figures/stress_latency.png
  python scripts/generate_report_figures.py --pulse-csv data/processed/zeroplus_analysis/all_high_pulses.csv --capture 03_Cache/cache50_01 --channel A1 --output figures/cache_pulse_hist.pdf

Original .alc capture files are preserved separately; scripts never edit raw data.
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

LABELS={'A0':'GPIO25 · transfer/LUT/DAC','A1':'GPIO22 · service/work','A2':'GPIO19 · ISR','A3':'GPIO21 · UART TX','A4':'GPIO18 · SPI SCLK','A5':'GPIO23 · MOSI','A6':'GPIO27 · MISO','A7':'GPIO5 · SPI CS'}

def waveform(csv_path, channels, start_us, duration_us, out):
    df=pd.read_csv(csv_path)
    required={'channel','time_us','edge'}
    if not required.issubset(df): raise ValueError(f'Edges CSV missing {required-set(df.columns)}')
    df=df.sort_values('time_us')
    a=float(start_us) if start_us is not None else float(df.time_us.min())
    b=a+float(duration_us) if duration_us is not None else float(df.time_us.max())
    if b<=a: raise ValueError('Invalid time window')
    fig,axes=plt.subplots(len(channels),1,figsize=(11,max(2.1,len(channels)*1.15)),sharex=True,squeeze=False)
    for ax,ch in zip(axes[:,0],channels):
        sub=df[df.channel.eq(ch)]
        before=sub[sub.time_us.lt(a)]
        # first known state is inferred from immediately preceding transition only
        level=int(before.iloc[-1].new_level) if len(before) and 'new_level' in before else (int(before.iloc[-1].edge=='rising') if len(before) else None)
        active=sub[sub.time_us.ge(a)&sub.time_us.le(b)]
        if level is None:
            # No known starting state: label rather than assume
            if len(active): level=0 if active.iloc[0].edge=='rising' else 1
            else: level=0
            ax.text(.99,.8,'initial state inferred',ha='right',transform=ax.transAxes,fontsize=7,alpha=.7)
        xs=[a]; ys=[level]
        for r in active.itertuples():
            level=int(getattr(r,'new_level',1 if r.edge=='rising' else 0))
            xs.append(float(r.time_us));ys.append(level)
        xs.append(b);ys.append(level)
        ax.step(xs,ys,where='post',linewidth=1.1)
        ax.set_yticks([0,1]);ax.set_ylim(-.2,1.2)
        ax.set_ylabel(ch,rotation=0,labelpad=15,fontweight='bold')
        ax.grid(alpha=.2)
        ax.text(.01,.82,LABELS.get(ch,ch),transform=ax.transAxes,fontsize=8,alpha=.7)
    axes[-1,0].set_xlabel('Capture-relative timestamp (µs); shared file timebase')
    fig.tight_layout();out.parent.mkdir(parents=True,exist_ok=True);fig.savefig(out,bbox_inches='tight');plt.close(fig)

def latency(csv_path,out):
    df=pd.read_csv(csv_path)
    if not {'test','dispatch_latency_us'}.issubset(df): raise ValueError('Expected test,dispatch_latency_us')
    fig,ax=plt.subplots(figsize=(8,5))
    for group in ['stress1','stress3','stress5']:
        x=pd.to_numeric(df.loc[df.test.eq(group),'dispatch_latency_us'],errors='coerce').dropna().to_numpy()
        if len(x):
            x=np.sort(x); ax.plot(x,np.arange(1,len(x)+1)/len(x),label=f'{group} n={len(x)}')
    ax.set_xlabel('ISR-entry to dispatcher latency (µs)');ax.set_ylabel('Empirical cumulative probability');ax.grid(alpha=.25);ax.legend()
    fig.tight_layout();out.parent.mkdir(parents=True,exist_ok=True);fig.savefig(out,bbox_inches='tight');plt.close(fig)

def pulse_hist(csv_path,capture,channel,out):
    df=pd.read_csv(csv_path)
    if not {'capture','channel','width_us'}.issubset(df): raise ValueError('Expected capture,channel,width_us')
    df=df[df.capture.astype(str).str.contains(capture,regex=False)&df.channel.eq(channel)]
    x=pd.to_numeric(df.width_us,errors='coerce').dropna().to_numpy()
    if not len(x): raise ValueError('No matching pulses; check capture string and channel')
    fig,ax=plt.subplots(figsize=(8,5));ax.hist(x,bins=min(100,max(10,int(np.sqrt(len(x))))))
    ax.axvline(np.mean(x),linestyle='--',label=f'mean {np.mean(x):.3f} µs');ax.axvline(np.median(x),linestyle=':',label=f'median {np.median(x):.3f} µs')
    ax.set_title(f'{capture} | {channel} | {len(x)} complete HIGH pulses')
    ax.set_xlabel('HIGH width (µs)');ax.set_ylabel('Count');ax.legend();ax.grid(alpha=.2)
    fig.tight_layout();out.parent.mkdir(parents=True,exist_ok=True);fig.savefig(out,bbox_inches='tight');plt.close(fig)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawTextHelpFormatter)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--edges');group.add_argument('--samples');group.add_argument('--pulse-csv')
    p.add_argument('--channels',default='A0,A1,A2,A4,A7');p.add_argument('--channel',default='A1')
    p.add_argument('--start-us',type=float);p.add_argument('--duration-us',type=float)
    p.add_argument('--capture',default='');p.add_argument('--output',required=True)
    a=p.parse_args();out=Path(a.output)
    if a.edges: waveform(a.edges,[s.strip() for s in a.channels.split(',')],a.start_us,a.duration_us,out)
    elif a.samples: latency(a.samples,out)
    else: pulse_hist(a.pulse_csv,a.capture,a.channel,out)
    print(f'Created {out}')
