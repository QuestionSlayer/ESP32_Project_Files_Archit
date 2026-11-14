#!/usr/bin/env python3
"""One-shot ESP32 benchmark preflight and data capture.

Firmware: esp32_benchmark_logged.ino (requires q ACK and g CSV commands).
Install: python -m pip install pyserial
Run: python esp32_one_click_preflight.py
     python esp32_one_click_preflight.py --port COM5

No logic analyzer necessary. Required for SPI integrity: unpowered-board
jumper GPIO23 (MOSI) -> GPIO27 (MISO). Leave GPIO19 as ISR marker.
Serial commands/CSV export occur only after timer measurements stop.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import statistics
import sys
import time
try:
    import serial
    from serial.tools import list_ports
except ImportError:
    sys.exit("Install dependency: python -m pip install pyserial")

TESTS = {
    'poll': ('p', 'transfer'), 'interrupt': ('i', 'transfer'), 'dma': ('d', 'transfer'),
    'spill': ('r', 'transfer'),
    'stress1': ('1', 'timer'), 'stress2': ('2', 'timer'),
    'stress3': ('3', 'timer'), 'stress4': ('4', 'timer'),
    'stress5': ('5', 'timer'), 'stress23': ('e', 'timer'),
    'cache_warm': ('u', 'timer'), 'cache12': ('m', 'timer'),
    'cache50': ('t', 'timer'), 'cache100': ('7', 'timer'),
}
TRANSFER_RE = {
    'wall_us': r'(?:transfer wall time\s*:|\[INTERRUPT\].*?wall|wire/transfer time\s*:)\s*([0-9.]+)',
    'queue_cpu_us': r'queue CPU time\s*:\s*([0-9.]+)',
    'isr_cpu_us': r'ISR CPU time\s*:\s*([0-9.]+)',
    'blocked_wait_us': r'blocked wait span\s*:\s*([0-9.]+)',
    'isr_work_us': r'CPU ISR workload\s*:\s*([0-9.]+)',
    'poll_work_us': r'CPU workload\s*:\s*([0-9.]+)',
    'mismatched_bytes': r'mismatched bytes=(\d+)/',
    'interrupt_count': r'IRQs\s+(\d+)',
    'status_dma': r'\[SPI DMA \+ loopback\]\s*(PASS|FAIL)',
    'status_interrupt': r'\[INTERRUPT\]\s*(done|TIMEOUT)',
    'spill_resident_cycles': r'Register-Resident.*?:\s*(\d+) cycles',
    'spill_forced_cycles': r'Shallow \+ explicit xthal_window_spill.*?:\s*(\d+) cycles',
    'spill_deep_cycles': r'Deep recursion.*?:\s*(\d+) cycles',
}

def read_until(ser, stop, timeout):
    lines, deadline = [], time.monotonic() + timeout
    while time.monotonic() < deadline:
        raw = ser.readline()
        if not raw:
            continue
        line = raw.decode('utf-8', errors='replace').rstrip('\r\n')
        lines.append(line)
        if stop(line):
            return lines
    raise TimeoutError(f'Timed out waiting for device response; tail: {lines[-8:]}')

def command(ser, letter, timeout=15):
    # Acknowledgment is sent as a separate command and processed after the first command.
    # This serial protocol is intentionally sequential, not clock-synchronized.
    ser.write((letter + 'q').encode('ascii'))
    ser.flush()
    return read_until(ser, lambda s: s.strip() == 'BENCH_ACK', timeout)

def parse_samples(lines):
    begin = next((s for s in lines if s.startswith('BEGIN_SAMPLES,')), None)
    if begin is None:
        raise ValueError('No sample frame: is esp32_benchmark_logged.ino uploaded?')
    meta = {}
    for x in begin.split(',')[1:]:
        k, v = x.split('=', 1)
        meta[k] = int(v)
    start = lines.index('index,isr_entry_cycles,period_cycles,latency_cycles,flash_work_cycles') + 1
    end = lines.index('END_SAMPLES')
    records = []
    for line in lines[start:end]:
        if re.fullmatch(r'\d+(,\d+){4}', line):
            a = [int(x) for x in line.split(',')]
            records.append(a)
    if len(records) != meta['retained']:
        raise ValueError(f'Incomplete CSV dump: got {len(records)} / {meta["retained"]}')
    mhz = meta['cpu_mhz']
    if mhz <= 0:
        raise ValueError('Invalid CPU frequency')
    # Absolute cycle timestamps wrap at 2^32. Relative values valid only for
    # the retained ~0.1 second window, and cannot recover gaps/earlier samples.
    first = records[0][1] if records else 0
    rows = []
    for idx, entry, period, lat, work in records:
        period_us = period / mhz if period else None
        rows.append({
            'sample_index': idx, 'isr_time_relative_us': ((entry-first) & 0xffffffff)/mhz,
            'isr_entry_cycles':entry,
            'period_us':period_us,
            'signed_jitter_us': period_us - meta['nominal_us'] if period_us is not None else None,
            'abs_jitter_us':abs(period_us-meta['nominal_us']) if period_us is not None else None,
            'dispatch_latency_us':lat/mhz, 'flash_work_us':work/mhz,
        })
    return meta, rows

def extract_transfer(log, test):
    d = {'test':test}
    for key, rx in TRANSFER_RE.items():
        match = re.search(rx, log, flags=re.I)
        if match:
            val = match.group(1)
            d[key] = float(val) if key not in ('status_dma','status_interrupt') else val
    if test == 'dma':
        d['pass'] = d.get('status_dma') == 'PASS'
    elif test == 'interrupt':
        d['pass'] = d.get('status_interrupt') == 'done'
    elif test == 'spill':
        d['pass'] = 'spill_forced_cycles' in d and 'spill_resident_cycles' in d
        if d['pass']:
            d['spill_forced_minus_resident_cycles'] = d['spill_forced_cycles'] - d['spill_resident_cycles']
    elif test == 'poll':
        d['pass'] = '[POLL] done' in log
    return d

def write_csv(path, rows):
    if not rows:
        return
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)


def pick_port(spec):
    if spec:
        return spec
    ports = list(list_ports.comports())
    candidates = [p for p in ports if any(s in ((p.description or '')+' '+(p.manufacturer or '')).lower()
                  for s in ('usb','serial','ch340','cp210','silicon labs','uart','wch'))]
    if len(candidates) == 1:
        print('Auto-selected serial port:', candidates[0].device)
        return candidates[0].device
    if len(ports) == 1:
        print('Auto-selected only serial port:', ports[0].device)
        return ports[0].device
    if not ports:
        sys.exit('No serial ports found. Connect ESP32 by data USB cable.')
    print('Select ESP32 serial port:')
    for i,p in enumerate(ports,1): print(f' {i}. {p.device} - {p.description}')
    while True:
        choice=input('Enter number: ').strip()
        if choice.isdigit() and 1 <= int(choice) <= len(ports):
            return ports[int(choice)-1].device

def write_table(path, rows):
    if not rows: return
    keys=list(dict.fromkeys(k for r in rows for k in r.keys()))
    with path.open('w',newline='',encoding='utf-8') as f:
        wr=csv.DictWriter(f,fieldnames=keys);wr.writeheader();wr.writerows(rows)

def summarize_samples(rows, meta):
    def summarize(key):
        v=[float(r[key]) for r in rows if r.get(key) is not None and math.isfinite(float(r[key]))]
        if not v: return {}
        return {f'{key}_mean':statistics.mean(v), f'{key}_std':statistics.stdev(v) if len(v)>1 else 0.0,
                f'{key}_min':min(v),f'{key}_max':max(v)}
    result={'retained':len(rows),'total':meta.get('total',0),'dropped':meta.get('dropped',0),
            'nominal_us':meta.get('nominal_us')}
    for key in ('period_us','signed_jitter_us','abs_jitter_us','dispatch_latency_us','flash_work_us'):
        result.update(summarize(key))
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port',help='COM5, /dev/ttyUSB0, /dev/cu.usbserial-*; auto-detect if omitted')
    ap.add_argument('--baud',type=int,default=115200)
    ap.add_argument('--out',default='esp32_preflight_results',help='Parent directory for all saved test evidence')
    ap.add_argument('--repeats',type=int,default=10,help='Repeats of each test (default 10)')
    ap.add_argument('--dma-repeats',type=int,default=20,help='DMA payload integrity trials (default 20)')
    ap.add_argument('--duration',type=float,default=0.075,help='Timer acquisition seconds (default 0.075, below rolling sample capacity)')
    ap.add_argument('--timeout',type=float,default=15.0,help='Per-command reply timeout')
    args=ap.parse_args()
    if args.repeats < 1 or args.dma_repeats < 1 or not (0.02 <= args.duration <= 0.095):
        ap.error('requires repeats >=1, dma-repeats >=1, and duration 0.02..0.095 sec')
    port=pick_port(args.port)
    dest=Path(args.out) / datetime.now().strftime('%Y%m%d_%H%M%S')
    dest.mkdir(parents=True,exist_ok=True)
    plan=[('dma',args.dma_repeats),('poll',args.repeats),('interrupt',args.repeats),
          ('stress1',args.repeats),('stress5',args.repeats),
          ('cache_warm',args.repeats),('cache12',args.repeats),('cache50',args.repeats),('cache100',args.repeats),
          ('spill',args.repeats)]
    total=sum(n for _,n in plan)
    info={'started_utc':datetime.now(timezone.utc).isoformat(),'port':port,
          'baud':args.baud,'repeats':args.repeats,'dma_repeats':args.dma_repeats,
          'duration_s':args.duration,'firmware_expected':'esp32_benchmark_logged.ino',
          'spi_loopback_jumper':'GPIO23 -> GPIO27', 'tests':plan,
          'note':'DMA loopback requires jumper; stress/cache effects are not predetermined; edge data requires logic analyzer.'}
    (dest/'manifest.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
    events=[]; samples_all=[]; transfer_rows=[]; timer_summaries=[]; failures=[]
    print('\nESP32 PRE-FLIGHT: no logic analyzer required')
    print('Power OFF when connecting GPIO23 -> GPIO27 jumper. Close Arduino Serial Monitor.')
    print('Saving evidence to:',dest.resolve())
    print('Opening:',port)
    try:
        ser=serial.Serial(port,args.baud,timeout=0.12,write_timeout=3)
    except Exception as e:
        (dest/'connection_error.txt').write_text(repr(e))
        sys.exit(f'Cannot open serial port: {e}')
    try:
        time.sleep(2.8)  # USB DTR commonly resets ESP32
        ser.reset_input_buffer()
        try:
            # Verify firmware's ACK protocol before proceeding. No tests active.
            greeting=command(ser,'0',args.timeout)
            (dest/'startup_serial.txt').write_text('\n'.join(greeting)+'\n')
        except Exception as e:
            (dest/'connection_error.txt').write_text(repr(e))
            sys.exit('Firmware communication failed. Check baud=115200, firmware version and q ACK support. '+repr(e))
        done=0
        for test,count in plan:
            letter,kind=TESTS[test]
            for rep in range(1,count+1):
                done+=1; prefix=f'{test}_{rep:03d}'
                print(f'[{done}/{total}] {prefix}',flush=True)
                t_host=time.monotonic()
                record={'test':test,'repeat':rep,'status':'FAIL','error':'',
                        'host_elapsed_s':None,'samples':None,'dropped':None,
                        'dma_mismatches':None}
                log=[]
                try:
                    # Stop any prior timer, never print data during acquisition.
                    if kind == 'timer':
                        # Firmware emits optional mode selection just before it starts.
                        ser.write(letter.encode('ascii'));ser.flush()
                        time.sleep(args.duration)
                        # Only after acquisition: stop, acknowledge, and export.
                        log += command(ser,'0',args.timeout)
                        dump=command(ser,'g',max(args.timeout,65))
                        log += dump
                        meta,rows=parse_samples(dump)
                        for row in rows: row['test']=test;row['repeat']=rep
                        write_table(dest/f'{prefix}_samples.csv',rows)
                        samples_all.extend(rows)
                        (dest/f'{prefix}_meta.json').write_text(json.dumps(meta,indent=2))
                        summary={'test':test,'repeat':rep,**summarize_samples(rows,meta)}
                        timer_summaries.append(summary)
                        record['samples']=len(rows);record['dropped']=meta.get('dropped',0)
                        record['period_mean_us']=summary.get('period_us_mean')
                        record['latency_mean_us']=summary.get('dispatch_latency_us_mean')
                        # Valid data check only, NOT an expectation that stress or cache must increase latency.
                        if len(rows)<20: raise ValueError('Too few timer samples: '+str(len(rows)))
                        p=summary.get('period_us_mean')
                        if p is None or not (40.0 <= p <= 60.0):
                            record['status']='WARN';record['error']=f'Period mean {p}, expected near 50 us'
                        elif meta.get('dropped',0)>0:
                            record['status']='WARN';record['error']='Dropped ISR ring events'
                        else: record['status']='PASS'
                    else:
                        log=command(ser,letter,max(args.timeout,20))
                        result=extract_transfer('\n'.join(log),test)
                        result['repeat']=rep
                        transfer_rows.append(result)
                        (dest/f'{prefix}_metrics.json').write_text(json.dumps(result,indent=2))
                        if test=='dma':
                            record['dma_mismatches']=result.get('mismatched_bytes')
                        if result.get('pass') is True: record['status']='PASS'
                        else:
                            record['status']='FAIL'
                            record['error']='Transfer not reported PASS; inspect serial transcript'
                except Exception as e:
                    record['status']='FAIL';record['error']=str(e)
                    failures.append({'test':test,'repeat':rep,'error':str(e)})
                    try:
                        # Safe recovery attempt; if firmware deadlocks on SPI result, this may time out.
                        log += command(ser,'0',min(args.timeout,4))
                    except Exception: pass
                record['host_elapsed_s']=round(time.monotonic()-t_host,3)
                events.append(record)
                (dest/f'{prefix}_serial.txt').write_text('\n'.join(log)+'\n',encoding='utf-8')
                if record['status']!='PASS':
                    (dest/f'{prefix}_issue.txt').write_text(record['error']+'\n',encoding='utf-8')
                    print('  '+record['status']+': '+record['error'])
                else: print('  PASS')
        try: command(ser,'0',min(args.timeout,5))
        except Exception: pass
    except KeyboardInterrupt:
        print('Interrupted. Saving partial data.');info['interrupted']=True
        try: command(ser,'0',3)
        except Exception: pass
    finally:
        ser.close()
        write_table(dest/'trial_status.csv',events)
        write_table(dest/'all_timer_samples.csv',samples_all)
        write_table(dest/'timer_trial_summary.csv',timer_summaries)
        write_table(dest/'transfer_trials.csv',transfer_rows)
        info['finished_utc']=datetime.now(timezone.utc).isoformat()
        info['completed_trials']=len(events)
        (dest/'manifest.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
        status_counts={s:sum(1 for r in events if r['status']==s) for s in ('PASS','WARN','FAIL')}
        dma=[r for r in events if r['test']=='dma']
        period=[r['period_us_mean'] for r in events if r.get('period_mean_us') is not None]
        summary={**status_counts,'total_trials':len(events),'dma_pass':sum(r['status']=='PASS' for r in dma),
                 'dma_trials':len(dma),'period_means_observed_us':period,
                 'hardware_verified':False,'notes':[
                  'No external edge timestamps were captured: logic analyzer required',
                  'Target cache misses are unverified; no hardware miss counter used',
                  'Register-spill causality not proven by this basic preflight',
                  'UART polling/interrupt and SPI DMA are different peripherals',
                  'No actual system-wide CPU utilization measurement is included',
                  'Serial ACKs and exports are after timer acquisition; firmware mode logging is its own responsibility']}
        (dest/'summary.json').write_text(json.dumps(summary,indent=2))
        lines=[f'ESP32 BENCH PREFLIGHT REPORT | {info["started_utc"]}',
               f'Port: {port}', f'Trials: {len(events)} | PASS {status_counts["PASS"]} | WARN {status_counts["WARN"]} | FAIL {status_counts["FAIL"]}',
               f'SPI DMA loopback passes: {summary["dma_pass"]}/{summary["dma_trials"]}',
               '', 'Per-test result:']
        for test,_ in plan:
            batch=[r for r in events if r['test']==test]
            lines.append(f'  {test}: '+', '.join(r['status'] for r in batch))
        if any(r['status']!='PASS' for r in events):
            lines += ['', 'Issues:']
            for r in events:
                if r['status']!='PASS':lines.append(f'  {r["test"]} #{r["repeat"]}: {r["status"]} {r["error"]}')
        lines+=['','Interpretation:',*('  - '+x for x in summary['notes']),
                '', 'Send the complete timestamped result folder as a ZIP for later analysis.']
        (dest/'REPORT.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        print('\n'+'\n'.join(lines[:5]))
        print('Saved:',dest.resolve())
        try:
            import zipfile
            zpath=dest.with_suffix('.zip')
            with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED) as z:
                for f in dest.rglob('*'):
                    if f.is_file():z.write(f,arcname=str(f.relative_to(dest.parent)))
            print('UPLOAD THIS ZIP LATER:',zpath.resolve())
        except Exception as exc: print('Could not zip results:',exc)

if __name__=='__main__': main()
