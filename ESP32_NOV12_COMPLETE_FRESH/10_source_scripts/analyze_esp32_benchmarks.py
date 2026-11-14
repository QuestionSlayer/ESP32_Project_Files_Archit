#!/usr/bin/env python3
"""Summarize ESP32 bench logs and optional external logic-analyzer CSV edges.
Install: python -m pip install matplotlib
Usage: python analyze_esp32_benchmarks.py bench_results/20261110_220000
       python analyze_esp32_benchmarks.py bench_results/20261110_220000 --edges capture.csv

Analyzer edge CSV format (preferred): time_s,channel,edge (rising/falling)
or time_s,channel,level (0/1 after edge). Generic analyzer sampled digital
CSV can also be read when headers include "Time [s]", "Channel 0", etc.
Channel mapping supplied with --channel-map "0=GPIO25,1=GPIO22,2=GPIO19".
"""
import argparse
import csv
import json
from pathlib import Path
from collections import defaultdict
import math
import re
import statistics

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
except ImportError:
    raise SystemExit('Install matplotlib: python -m pip install matplotlib')

FIELDS = ('period_us','signed_jitter_us','abs_jitter_us','dispatch_latency_us','flash_work_us')

def number(x):
    try:
        v=float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None

def describe(values):
    vals=sorted(x for x in (number(y) for y in values) if x is not None)
    if not vals:return None
    def pct(p):
        pos=(len(vals)-1)*p; i=int(pos); frac=pos-i
        return vals[i]*(1-frac)+vals[min(i+1,len(vals)-1)]*frac
    return {'n':len(vals),'mean':statistics.mean(vals),
            'std_dev_sample': statistics.stdev(vals) if len(vals)>1 else None,
            'min':vals[0],'median':pct(.5),'p95':pct(.95),'p99':pct(.99),'max':vals[-1]}

def load_csv(path):
    with path.open(newline='',encoding='utf-8-sig') as f: return list(csv.DictReader(f))

def save_csv(path, rows):
    if not rows:return
    with path.open('w',newline='') as f:
        wr=csv.DictWriter(f, fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)

def plot_hist(v, title, dest, unit='us'):
    nums=[x for x in (number(y) for y in v) if x is not None]
    if not nums:return
    fig,ax=plt.subplots(figsize=(8,4.5))
    ax.hist(nums,bins=min(55,max(8,int(len(nums)**.5))))
    d=describe(nums)
    ax.set(title=title,xlabel=f'Time ({unit})',ylabel='Count')
    ax.axvline(d['mean'],linestyle='--',label=f'Mean={d["mean"]:.3f} {unit}')
    ax.legend();fig.tight_layout();fig.savefig(dest,dpi=160);plt.close(fig)

def plot_timeline(rows,dest):
    fig,ax=plt.subplots(figsize=(10,4))
    t=[number(r['isr_time_relative_us']) for r in rows]
    y=[number(r['dispatch_latency_us']) for r in rows]
    ax.plot(t,y,marker='.',markersize=2,linewidth=.7)
    ax.set(xlabel='Time since first retained ISR (us)',ylabel='ISR-to-dispatch latency (us)',title='Measured latency over time')
    fig.tight_layout();fig.savefig(dest,dpi=160);plt.close(fig)

def normalize_edges(rows, channel_map):
    if not rows:return []
    col={k.lower().strip():k for k in rows[0]}
    explicit_time=next((col[k] for k in ('time_s','timestamp_s','time [s]','time') if k in col),None)
    if explicit_time is None:raise ValueError('Edge CSV needs a time_s / Time [s] column')
    t_unit=1.0
    if 'us' in explicit_time.lower() or 'µs' in explicit_time.lower():t_unit=1e-6
    if 'ms' in explicit_time.lower():t_unit=1e-3
    events=[]
    if 'channel' in col and ('edge' in col or 'level' in col):
        chcol=col['channel'];ecol=col.get('edge') or col['level']
        for r in rows:
            t=number(r.get(explicit_time))
            if t is None:continue
            raw=r[chcol].strip();ch=channel_map.get(raw,raw)
            edge=r[ecol].strip().lower()
            if edge in ('1','high','rise','rising','up'):lev=1
            elif edge in ('0','low','fall','falling','down'):lev=0
            else:continue
            events.append({'time_s':t*t_unit,'channel':ch,'level':lev})
    else:
        # For sampled digital exports: each sampled row gives current pin level.
        # Keep only changes; first row establishes initial level, not a true edge.
        chcols=[k for k in rows[0] if k != explicit_time and
                (k.lower().startswith('channel') or re.match(r'^ch\d+$',k,re.I))]
        prev={}
        for r in rows:
            t=number(r.get(explicit_time))
            if t is None:continue
            for c in chcols:
                ch_id=re.search(r'(\d+)',c)
                name=channel_map.get(ch_id.group(1) if ch_id else c,c)
                val=str(r[c]).strip()
                if val not in ('0','1'):continue
                lev=int(val)
                if name in prev and lev != prev[name]:
                    events.append({'time_s':t*t_unit,'channel':name,'level':lev})
                prev[name]=lev
    return sorted(events,key=lambda x:x['time_s'])

def edge_analysis(events, out):
    save_csv(out/'logic_edges_normalized.csv',events)
    group=defaultdict(list)
    for e in events:group[e['channel']].append(e)
    rows=[]
    for ch,seq in group.items():
        rises=[e['time_s'] for e in seq if e['level']==1]
        falling=[e['time_s'] for e in seq if e['level']==0]
        periods=[(b-a)*1e6 for a,b in zip(rises,rises[1:])]
        highs=[];last_rise=None
        for e in seq:
            if e['level']==1:last_rise=e['time_s']
            elif last_rise is not None:
                highs.append((e['time_s']-last_rise)*1e6);last_rise=None
        for metric,values in (('rise_to_rise_period_us',periods),('high_pulse_width_us',highs)):
            d=describe(values)
            if d:rows.append({'channel':ch,'metric':metric,**d})
    save_csv(out/'logic_edge_statistics.csv',rows)
    if not group:return
    t0=events[0]['time_s']; t1=events[-1]['time_s']
    fig,ax=plt.subplots(figsize=(12,max(3,1.0*len(group)+1)))
    for i,(ch,seq) in enumerate(sorted(group.items())):
        # Edges do not establish initial state: assume LOW before first known edge.
        times=[t0];states=[0]
        for e in seq:
            times.append(e['time_s']);states.append(e['level'])
        times.append(t1);states.append(states[-1])
        ax.step([(x-t0)*1e6 for x in times],[i+0.75*s for s in states],where='post',label=ch)
    ax.set_yticks(list(range(len(group))),labels=sorted(group))
    ax.set(xlabel='Time relative to capture start (us)',title='Logic analyzer edge waveform (exported transitions)')
    fig.tight_layout();fig.savefig(out/'logic_waveform.png',dpi=160);plt.close(fig)

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('folder',type=Path)
    p.add_argument('--edges',type=Path,help='Optional external logic-analyzer CSV')
    p.add_argument('--channel-map',default='0=GPIO25,1=GPIO22,2=GPIO19,3=MOSI,4=MISO,5=SCLK,6=CS')
    args=p.parse_args()
    folder=args.folder
    if not folder.is_dir():p.error('Folder does not exist')
    out=folder/'analysis';out.mkdir(exist_ok=True)
    timer_files=sorted(folder.glob('*_samples.csv'))
    all_stats=[]
    for fn in timer_files:
        rows=load_csv(fn)
        test=fn.name.rsplit('_',2)[0]
        repeat=fn.name.rsplit('_',2)[1]
        if not rows:continue
        for field in FIELDS:
            d=describe(r.get(field) for r in rows)
            if d:all_stats.append({'test':test,'repeat':repeat,'metric':field,**d})
            plot_hist((r.get(field) for r in rows),f'{test} run {repeat}: {field}',out/f'{fn.stem}_{field}_hist.png')
        plot_timeline(rows,out/f'{fn.stem}_latency_waveform.png')
    save_csv(out/'timer_statistics.csv',all_stats)
    # Pool raw samples by test (doesn't hide run-level summaries above).
    pooled=defaultdict(list)
    for fn in timer_files:
        test=fn.name.rsplit('_',2)[0]
        pooled[test].extend(load_csv(fn))
    pooled_stats=[]
    for test,rows in pooled.items():
        for field in FIELDS:
            d=describe(r.get(field) for r in rows)
            if d:pooled_stats.append({'test':test,'metric':field,**d})
    save_csv(out/'pooled_timer_statistics.csv',pooled_stats)
    transfer_path=folder/'transfer_trials.csv'
    if transfer_path.exists():
        trs=load_csv(transfer_path); grouped=defaultdict(list)
        for r in trs:grouped[r['test']].append(r)
        transfer_stats=[]
        for test, rr in grouped.items():
            for fld in ('wall_us','queue_cpu_us','isr_cpu_us','blocked_wait_us','isr_work_us','poll_work_us','mismatched_bytes','interrupt_count','spill_resident_cycles','spill_forced_cycles','spill_deep_cycles','spill_forced_minus_resident_cycles'):
                d=describe(r.get(fld) for r in rr)
                if d:
                    transfer_stats.append({'test':test,'metric':fld,**d})
                    plot_hist((r.get(fld) for r in rr),f'{test}: {fld}',out/f'transfer_{test}_{fld}_hist.png')
        save_csv(out/'transfer_statistics.csv',transfer_stats)
    if args.edges:
        mapping={}
        for token in args.channel_map.split(','):
            a,b=token.split('=',1);mapping[a.strip()]=b.strip()
        events=normalize_edges(load_csv(args.edges),mapping)
        if not events:print('Warning: no recognized edge transitions in provided analyzer CSV')
        edge_analysis(events,out)
    print(f'Analysis saved to {out}')

if __name__=='__main__':main()
