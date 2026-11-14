#!/usr/bin/env python3
"""Automate instrumented ESP32 tests over USB serial.

Install: python -m pip install pyserial
Example:
  python run_esp32_benchmarks.py --port COM5 --repeats 12 --duration 0.15
  python run_esp32_benchmarks.py --port /dev/ttyUSB0 --tests dma,stress1,cache_warm

Requires esp32_benchmark_logged.ino, providing 'q' ACK and 'g' CSV dump.
Captures serial output after each acquisition; does not obtain physical GPIO edges.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("Install pyserial: python -m pip install pyserial")

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

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', required=True, help='COM5, /dev/ttyUSB0, or /dev/cu.usbserial-*')
    ap.add_argument('--baud', type=int, default=115200)
    ap.add_argument('--tests', default='poll,interrupt,dma,stress1,stress3,cache_warm,cache12,cache50,cache100')
    ap.add_argument('--repeats', type=int, default=8)
    ap.add_argument('--duration', type=float, default=0.12, help='Seconds for each timer/stress/cache acquisition; 0.12 retains <=2048 samples')
    ap.add_argument('--out', default='bench_results')
    ap.add_argument('--timeout', type=float, default=25)
    args = ap.parse_args()
    selected = [x.strip() for x in args.tests.split(',') if x.strip()]
    unknown = set(selected)-set(TESTS)
    if unknown: ap.error(f'Unknown tests {sorted(unknown)}; options {sorted(TESTS)}')
    if args.repeats < 1 or args.duration <= 0: ap.error('repeats and duration must be positive')
    dest = Path(args.out) / datetime.now().strftime('%Y%m%d_%H%M%S')
    dest.mkdir(parents=True, exist_ok=True)
    manifest = vars(args).copy()
    manifest['started_utc'] = datetime.now(timezone.utc).isoformat()
    (dest/'manifest.json').write_text(json.dumps(manifest, indent=2))
    rows_all = []
    transfer_all = []
    with serial.Serial(args.port, args.baud, timeout=0.15, write_timeout=4) as ser:
        # Opening serial often resets ESP32 (DTR/RTS); allow boot to finish.
        time.sleep(2.5)
        ser.reset_input_buffer()
        command(ser, '0', args.timeout)
        for test in selected:
            letter, kind = TESTS[test]
            for rep in range(1, args.repeats+1):
                prefix = f'{test}_{rep:03d}'
                print(f'{prefix}...', flush=True)
                try:
                    if kind == 'timer':
                        # Do NOT append 'q' to the start command: that would print BENCH_ACK
                        # while the timer is actively measuring, perturbing the test.
                        # Firmware flushes mode-selection output before enabling GPTimer.
                        ser.write(letter.encode('ascii'))
                        ser.flush()
                        time.sleep(args.duration)
                        # Stop before requesting any output/ACK from the device.
                        stop_lines = command(ser, '0', args.timeout)
                        start_lines = []
                        dump_lines = command(ser, 'g', max(args.timeout, 60))
                        meta, samples = parse_samples(dump_lines)
                        for row in samples:
                            row['test']=test; row['repeat']=rep
                        write_csv(dest/f'{prefix}_samples.csv', samples)
                        rows_all.extend(samples)
                        (dest/f'{prefix}_meta.json').write_text(json.dumps(meta, indent=2))
                        log = start_lines+stop_lines+dump_lines
                    else:
                        log = command(ser, letter, args.timeout)
                        result = extract_transfer('\n'.join(log), test)
                        result['repeat']=rep
                        transfer_all.append(result)
                        (dest/f'{prefix}_metrics.json').write_text(json.dumps(result, indent=2))
                    (dest/f'{prefix}_serial.txt').write_text('\n'.join(log)+'\n', encoding='utf-8')
                except Exception as ex:
                    (dest/f'{prefix}_error.txt').write_text(str(ex))
                    print(f'  ERROR {ex}', file=sys.stderr)
                    try: command(ser, '0', args.timeout)
                    except Exception: pass
        try: command(ser, '0', args.timeout)
        except Exception: pass
    write_csv(dest/'all_timer_samples.csv',rows_all)
    # Columns may vary between transfer test modes: normalize the union.
    if transfer_all:
        keys = ['test','repeat'] + sorted(set().union(*(x.keys() for x in transfer_all))-{'test','repeat'})
        with (dest/'transfer_trials.csv').open('w', newline='') as f:
            w = csv.DictWriter(f,fieldnames=keys); w.writeheader(); w.writerows(transfer_all)
    print(f'Done. Data in {dest}')

if __name__ == '__main__':main()
