#!/usr/bin/env python3
"""Experimental ZEROPLUS LAP-C .alc -> timestamped CSV converter.

Validated for ONE user-provided LAP-C 16032 capture at 25 MHz,
32K *compressed records*. This is reverse-engineering, not an official
ZEROPLUS format reader. Revalidate if acquisition settings differ.

Capture word layout found in this .alc:
    [8-bit channel state, 0, 0, unsigned 8-bit elapsed_count_minus_one]
Decoded record duration = (last_byte + 1) ticks, 40 ns/tick at 25 MHz.
The state in record i takes effect at the cumulative timestamp BEFORE
its duration. We export record transitions, not falsely uniform indices.

Examples:
    python alc_to_csv_fixed.py SPI_DMA_01.alc -o SPI_DMA_csv
    python alc_to_csv_fixed.py capture_dir --out-root converted
    python alc_to_csv_fixed.py captures.zip --out-root converted
"""
import argparse
import csv
import io
import json
import pathlib
import struct
import sys
import zipfile
import zlib
from collections import Counter

DEFAULT_RATE = 25_000_000
CHANNEL_NAMES = ['A0_GPIO25', 'A1_GPIO22', 'A2_GPIO19', 'A3_GPIO21',
                 'A4_GPIO18_SCLK', 'A5_GPIO23_MOSI', 'A6_GPIO27_MISO', 'A7_GPIO5_CS']


def find_stream(raw):
    candidates=[]
    for off in range(min(len(raw)-2, 8192)):
        if raw[off] != 0x78 or raw[off+1] not in (0x01,0x5e,0x9c,0xda):
            continue
        try:
            d=zlib.decompressobj()
            payload=d.decompress(raw[off:]) + d.flush()
            if not d.eof or len(payload)<4096 or len(payload)%4: continue
            if any(payload[i] or payload[i+1] for i in range(1,len(payload),4)):
                continue
            candidates.append((off,payload))
        except zlib.error:
            continue
    if len(candidates)!=1:
        raise ValueError(f'Expected exactly one compatible zlib capture stream, got {len(candidates)}')
    return candidates[0]


def decode(raw, sample_rate):
    off,blob=find_stream(raw)
    records=len(blob)//4
    if records>20_000_000: raise ValueError('Unexpectedly large capture')
    states=blob[0::4]
    durations=[int(x)+1 for x in blob[3::4]]
    ticks=[0]
    for d in durations:
        ticks.append(ticks[-1]+d)
    channel_edges={i:[] for i in range(8)}
    edges=[]
    for i in range(1, records):
        diff=states[i-1]^states[i]
        if not diff: continue
        for ch in range(8):
            if diff&(1<<ch):
                level=(states[i]>>ch)&1
                e=(i, ticks[i],ch,'rising' if level else 'falling',level)
                edges.append(e)
                channel_edges[ch].append(e)
    return off,states,durations,ticks,edges,channel_edges


def write_csv(path,header,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(header);w.writerows(rows)


def extract_one(data, output, rate, name):
    offset,states,durations,ticks,edges,channels=decode(data,rate)
    output.mkdir(parents=True,exist_ok=True)
    tick_us=1e6/rate
    def to_us(t): return round(t*tick_us,6)
    # CSV with transitions, not every 40ns step: safe for long compressed captures.
    write_csv(output/'digital_edges.csv',
        ['record_index','tick','time_us','channel','gpio','edge','new_level'],
        ((i,t,to_us(t),f'A{ch}',CHANNEL_NAMES[ch],typ,level) for i,t,ch,typ,level in edges))
    write_csv(output/'compressed_records.csv',
        ['record_index','start_tick','start_us','duration_ticks','duration_us','state_hex']+[f'A{k}' for k in range(8)],
        ((i,ticks[i],to_us(ticks[i]),durations[i],to_us(durations[i]),f'{states[i]:02X}',
          *[(states[i]>>k)&1 for k in range(8)]) for i in range(len(states))))
    # CS-active SPI rising clocks only. Capture is SPI mode 0, MSB-first.
    clk=[]
    for i,t,ch,typ,_ in channels[4]:
        if typ=='rising' and ((states[i]>>7)&1)==0:
            clk.append((i,t,(states[i]>>5)&1,(states[i]>>6)&1))
    bytes_data=[]
    for j in range(0,len(clk)-7,8):
        group=clk[j:j+8]
        tx=rx=0
        for _,_,a,b in group:
            tx=(tx<<1)|a;rx=(rx<<1)|b
        bytes_data.append((j//8,to_us(group[0][1]),f'{tx:02X}',f'{rx:02X}',int(tx==rx)))
    write_csv(output/'spi_decoded_bytes.csv',
        ['byte_index','first_clock_rise_us','mosi_hex','miso_hex','match'],bytes_data)
    # Pulse width measurements for each channel and rising-to-rising periods.
    pulserows=[]
    periodrows=[]
    for ch in range(8):
        arr=channels[ch]
        pending=None;last_rise=None
        for _,tick,_,edge,lev in arr:
            if edge=='rising':
                if last_rise is not None:
                    periodrows.append((f'A{ch}', CHANNEL_NAMES[ch],to_us(last_rise),to_us(tick),to_us(tick-last_rise)))
                last_rise=tick
                pending=tick
            elif pending is not None:
                pulserows.append((f'A{ch}', CHANNEL_NAMES[ch],to_us(pending),to_us(tick),to_us(tick-pending)))
                pending=None
    write_csv(output/'high_pulses.csv', ['channel','gpio','rise_us','fall_us','width_us'],pulserows)
    write_csv(output/'rising_periods.csv', ['channel','gpio','first_rise_us','next_rise_us','period_us'],periodrows)
    def widths(ch, start):
        arr=channels[ch]
        for idx,e in enumerate(arr[:-1]):
            if e[3]==start:
                nxt=arr[idx+1]
                if nxt[3]!=start:
                    yield (e[1],nxt[1],to_us(nxt[1]-e[1]))
    a0=list(widths(0,'rising')); a1=list(widths(1,'rising')); cs=list(widths(7,'falling'))
    clk_times=[t for _,t,_,_ in clk]
    spi_periods=[to_us(clk_times[k+1]-clk_times[k]) for k in range(len(clk_times)-1)]
    normal=[p for p in spi_periods if p<5]
    from statistics import median
    summary={
        'source':name,'parser':'experimental zero-plus packed-duration v2',
        'compression':'zlib + four-byte compressed records',
        'sample_rate_hz_assumed':rate,'tick_ns':1e9/rate,
        'compressed_records':len(states),'capture_duration_ms':round(ticks[-1]/rate*1000,6),
        'zlib_stream_offset':offset,
        'channel_map':dict(enumerate(CHANNEL_NAMES)),
        'edges_by_channel':{f'A{k}':len(channels[k]) for k in range(8)},
        'spi_sclk_rising_edges_under_cs':len(clk),
        'spi_full_bytes':len(bytes_data),
        'spi_mismatched_bytes':sum(1 for x in bytes_data if x[4]==0),
        'spi_clock_period_median_us':round(median(normal),6) if normal else None,
        'gpio25_high_intervals_us':[x[2] for x in a0],
        'gpio22_high_intervals_us':[x[2] for x in a1],
        'spi_cs_low_intervals_us':[x[2] for x in cs],
        'warnings':['Acquisition rate is user-supplied, not independently parsed from .alc header.',
                    'File format reverse-engineered using one 25MHz/32K/compressed capture; other models/settings require validation.',
                    'Time stamps are quantized to 40ns. Input edges between clock samples are not recoverable.',
                    'GPIO25/22 timing may differ slightly from UI due to ZEROPLUS interpolation/measurement boundaries.'],
        'validation':{'spi_cs_expected_us':5120,'spi_cs_measured_us':cs[0][2] if cs else None,
                      'spi_expected_clocks':4096,'spi_actual_clocks':len(clk)}
    }
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    return summary


def main():
    a=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument('input',help='single .alc file, directory, or .zip containing .alc files')
    a.add_argument('-o','--output',help='output directory for single file')
    a.add_argument('--out-root',default='alc_converted',help='output root for directory or ZIP')
    a.add_argument('--sample-rate',type=float,default=DEFAULT_RATE,help='Hz (default 25000000)')
    x=a.parse_args()
    if x.sample_rate<=0: a.error('sample rate must be positive')
    path=pathlib.Path(x.input)
    jobs=[]
    if path.suffix.lower()=='.alc' and path.is_file():
        jobs=[(path.name,path.read_bytes(),pathlib.Path(x.output or (path.stem+'_csv')))]
    elif path.is_dir():
        for f in sorted(path.rglob('*.alc')):
            jobs.append((str(f.relative_to(path)),f.read_bytes(),pathlib.Path(x.out_root)/f.relative_to(path).with_suffix('')))
    elif path.suffix.lower()=='.zip':
        with zipfile.ZipFile(path) as z:
            for filename in z.namelist():
                if filename.lower().endswith('.alc') and not filename.startswith('__MACOSX'):
                    safe=pathlib.PurePosixPath(filename)
                    if safe.is_absolute() or '..' in safe.parts:continue
                    jobs.append((filename,z.read(filename),pathlib.Path(x.out_root).joinpath(*safe.with_suffix('').parts)))
    else: a.error('input must be an existing .alc, folder or .zip')
    if not jobs:a.error('no .alc files found')
    failures=0
    for filename,data,out in jobs:
        try:
            s=extract_one(data,out,x.sample_rate,filename)
            print(f'OK {filename}: {s["compressed_records"]} records, {s["capture_duration_ms"]:.3f} ms; '
                  f'SPI {s["spi_full_bytes"]} bytes, CS windows {s["spi_cs_low_intervals_us"][:2]} us -> {out}')
        except Exception as exc:
            failures+=1
            print(f'FAILED {filename}: {exc}',file=sys.stderr)
    if failures: sys.exit(1)

if __name__=='__main__': main()
