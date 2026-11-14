#!/usr/bin/env python3
"""Collect diagnostic ESP32 measurements over USB Serial into real CSV files.

Usage:
    pip install pyserial
    python esp32_diag_serial_logger.py --port COM5
    python esp32_diag_serial_logger.py --port COM5 --repeats 3 --duration 0.08
    python esp32_diag_serial_logger.py --port COM5 --tests cache50_on,cache100_on,stress5_warm
    python esp32_diag_serial_logger.py --list-ports

This script targets the diagnostic .ino with F (flush toggle) and G (two CSV exports).
Do not keep Arduino Serial Monitor open while using this script.
"""
from __future__ import annotations
import argparse
import csv
import io
import json
import math
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    print('Missing pyserial. Install with: python -m pip install pyserial', file=sys.stderr)
    raise SystemExit(2)

TESTS = {
    'cache50_on': ('t', '8-line target, explicit cache flush ON'),
    'cache100_on': ('7', '16-line target, explicit cache flush ON'),
    'cache50_off': ('t', '8-line target, explicit cache flush OFF'),
    'cache100_off': ('7', '16-line target, explicit cache flush OFF'),
    'stress1_warm': ('u1', 'baseline, warm cache'),
    'stress1_cold': ('71', 'baseline, 16-line cold target'),
    'stress5_warm': ('u5', 'highest stress, warm cache'),
    'stress5_cold': ('75', 'highest stress, 16-line cold target'),
}
DEFAULT = list(TESTS)


def ports():
    return list(list_ports.comports())


def choose_port(arg):
    if arg:
        return arg
    ps = ports()
    if not ps:
        raise RuntimeError('No serial ports found. Connect ESP32 and run --list-ports.')
    if len(ps) == 1:
        print(f'Using detected port {ps[0].device} ({ps[0].description})')
        return ps[0].device
    print('Detected serial ports:')
    for i, p in enumerate(ps, 1):
        print(f'  {i}. {p.device} - {p.description}')
    n = input('Enter port number: ').strip()
    if not n.isdigit() or not 1 <= int(n) <= len(ps):
        raise RuntimeError('Invalid serial port selection')
    return ps[int(n) - 1].device


def read_available(conn, window=0.15):
    """Read all lines arriving for a short window, for command acknowledgments."""
    end = time.monotonic() + window
    lines = []
    while time.monotonic() < end:
        b = conn.readline()
        if b:
            lines.append(b.decode('utf-8', errors='replace').rstrip('\r\n'))
    return lines


def send(conn, char):
    assert len(char) == 1
    conn.write(char.encode('ascii'))
    conn.flush()


def set_flush(conn, desired, current, log):
    if current == desired:
        return current
    send(conn, 'F')
    responses = read_available(conn, 0.4)
    log.extend(responses)
    report = '\n'.join(responses).lower()
    expected = 'on' if desired else 'off'
    if f'diagnostic explicit cache flush: {expected}' not in report:
        raise RuntimeError('Flush state not confirmed. Output: ' + repr(responses[-8:]))
    print(f'    Flush => {expected.upper()}')
    return desired


def collect_export(conn, timeout=90.0, idle_timeout=15.0):
    """Collect complete two-section output; stop only at END_DIAG."""
    lines = []
    started = time.monotonic()
    last = started
    have_samples = False
    have_diag = False
    end_samples = False
    end_diag = False
    while time.monotonic() - started < timeout:
        b = conn.readline()
        if not b:
            if time.monotonic() - last > idle_timeout:
                break
            continue
        last = time.monotonic()
        line = b.decode('utf-8', errors='replace').rstrip('\r\n')
        lines.append(line)
        if line.startswith('BEGIN_SAMPLES'):
            have_samples = True
        elif line == 'END_SAMPLES':
            end_samples = True
        elif line.startswith('BEGIN_DIAG'):
            have_diag = True
        elif line == 'END_DIAG':
            end_diag = True
            # Allow remaining buffered bytes to arrive without starting next acquisition.
            lines.extend(read_available(conn, .15))
            break
    complete = have_samples and end_samples and have_diag and end_diag
    return '\n'.join(lines) + '\n', complete


def section_from_text(text, kind):
    """Return section metadata and rows from BEGIN_X header + CSV body + END_X."""
    begin, end = 'BEGIN_' + kind, 'END_' + kind
    raw = text.splitlines()
    starts = [i for i, s in enumerate(raw) if s.startswith(begin)]
    if len(starts) != 1:
        raise ValueError(f'Expected exactly one {begin}, found {len(starts)}')
    i = starts[0]
    finish = next((j for j in range(i + 1, len(raw)) if raw[j].strip() == end), None)
    if finish is None:
        raise ValueError(f'Missing {end}')
    meta = {}
    for item in raw[i].split(',')[1:]:
        if '=' in item:
            k, v = item.split('=', 1)
            meta[k.strip()] = v.strip()
    content = '\n'.join(raw[i + 1:finish])
    reader = csv.DictReader(io.StringIO(content))
    expected_columns = (['index','isr_entry_cycles','period_cycles','latency_cycles','flash_work_cycles'] if kind == 'SAMPLES'
                        else ['index','flush_cycles','full_callback_cycles','isr_during_flush','isr_during_load','ring_depth_after_pop'])
    if reader.fieldnames != expected_columns:
        raise ValueError(f'{kind}: unexpected header {reader.fieldnames!r}; expected {expected_columns!r}')
    rows = list(reader)
    for row in rows:
        if None in row or any(v is None for v in row.values()):
            raise ValueError(f'{kind}: malformed row {row!r}')
    indices = [int(row['index']) for row in rows]
    if any(y != x + 1 for x, y in zip(indices, indices[1:])):
        raise ValueError(f'{kind}: non-contiguous sample indices')
    if 'retained' in meta and len(rows) != int(meta['retained']):
        raise ValueError(f'{kind}: header retained={meta["retained"]} but actual CSV rows={len(rows)}')
    return meta, rows, expected_columns


def write_csv(path, columns, rows):
    with path.open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def derived_rows(original, meta, diag):
    speed = float(meta.get('cpu_mhz', 160))
    if len(original) != len(diag) or [x['index'] for x in original] != [x['index'] for x in diag]:
        raise ValueError('Original and diagnostic rows do not align (indices or row count)')
    fields = ['index', 'period_us', 'signed_jitter_us', 'abs_jitter_us', 'dispatch_latency_us',
              'load_work_us', 'cache_flush_us', 'full_callback_us', 'isr_during_flush',
              'isr_during_load', 'ring_depth_after_pop']
    out = []
    nominal = float(meta.get('nominal_us', 50))
    for s, d in zip(original, diag):
        period_cycles = int(s['period_cycles'])
        period = period_cycles / speed if period_cycles else None
        jitter = period - nominal if period is not None else None
        out.append({
            'index': int(s['index']),
            'period_us': '' if period is None else f'{period:.6f}',
            'signed_jitter_us': '' if jitter is None else f'{jitter:.6f}',
            'abs_jitter_us': '' if jitter is None else f'{abs(jitter):.6f}',
            'dispatch_latency_us': f'{int(s["latency_cycles"])/speed:.6f}',
            'load_work_us': f'{int(s["flash_work_cycles"])/speed:.6f}',
            'cache_flush_us': f'{int(d["flush_cycles"])/speed:.6f}',
            'full_callback_us': f'{int(d["full_callback_cycles"])/speed:.6f}',
            'isr_during_flush': int(d['isr_during_flush']),
            'isr_during_load': int(d['isr_during_load']),
            'ring_depth_after_pop': int(d['ring_depth_after_pop']),
        })
    return fields, out


def summary_stats(derived):
    result = {'samples': len(derived)}
    for k in ['period_us', 'abs_jitter_us', 'dispatch_latency_us', 'load_work_us',
              'cache_flush_us', 'full_callback_us']:
        vals = [float(r[k]) for r in derived if r[k] != '']
        result[k + '_mean'] = round(statistics.mean(vals), 5) if vals else None
        result[k + '_sd'] = round(statistics.stdev(vals), 5) if len(vals)>1 else None
    result['samples_with_isr_during_load'] = sum(int(r['isr_during_load'])>0 for r in derived)
    result['samples_with_isr_during_flush'] = sum(int(r['isr_during_flush'])>0 for r in derived)
    result['ring_depth_nonzero'] = sum(int(r['ring_depth_after_pop'])>0 for r in derived)
    result['latency_under_10us'] = sum(float(r['dispatch_latency_us'])<10 for r in derived)
    return result


def main():
    p = argparse.ArgumentParser(description='Run ESP32 diagnostic cache/stress tests and save real CSV files')
    p.add_argument('--port', help='Serial port, e.g. COM5 or /dev/ttyUSB0 (auto-select if omitted)')
    p.add_argument('--baud', type=int, default=115200)
    p.add_argument('--duration', type=float, default=0.08, help='Acquisition duration in seconds (default .08); rolling buffer usually stores latest ~51 ms')
    p.add_argument('--repeats', type=int, default=1)
    p.add_argument('--tests', default=','.join(DEFAULT), help='Comma-separated test names')
    p.add_argument('--out', default='esp32_diag_results', help='Parent output directory')
    p.add_argument('--export-timeout', type=float, default=90, help='Seconds allowed for G export')
    p.add_argument('--list-ports', action='store_true')
    args = p.parse_args()
    if args.list_ports:
        for port in ports():
            print(f'{port.device}: {port.description}')
        return
    selected = [t.strip() for t in args.tests.split(',') if t.strip()]
    unknown = set(selected) - TESTS.keys()
    if unknown:
        p.error(f'Unknown tests: {sorted(unknown)}. Available: {list(TESTS)}')
    if args.duration <= 0 or args.repeats <= 0:
        p.error('Duration and repeats must be positive')
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    root = Path(args.out).resolve() / stamp
    root.mkdir(parents=True, exist_ok=False)
    log_path = root/'session_log.txt'
    all_summary = []
    port = choose_port(args.port)
    print(f'Connecting to {port} @ {args.baud}. Arduino Serial Monitor must be CLOSED.')
    try:
        with serial.Serial(port, args.baud, timeout=.2, write_timeout=5) as conn:
            # Opening the port usually resets an ESP32. Wait for firmware setup.
            time.sleep(2.0)
            boot = read_available(conn, 1.0)
            log_path.write_text('\n'.join(boot)+'\n',encoding='utf-8')
            print('Board open. Initializing flush state by restarting the ESP32...')
            # Use a real reset via DTR/RTS only if serial open reset already happened;
            # instead require a user-confirmed fresh reset to know F starts ON.
            print('IMPORTANT: Press the ESP32 EN/RESET button ONCE now, then press Enter.')
            input()
            time.sleep(1.2)
            extra = read_available(conn, 1.0)
            with log_path.open('a',encoding='utf-8') as lg:
                lg.write('\n'.join(extra)+'\n')
            # Firmware initializes diag_do_cache_flush=true at boot.
            flush = True
            for repeat in range(1, args.repeats + 1):
                for name in selected:
                    command, description = TESTS[name]
                    desired_flush = not name.endswith('_off')
                    prefix = f'{name}_r{repeat:02}'
                    rawlog = []
                    print(f'[{repeat}/{args.repeats}] {name}: {description}')
                    try:
                        send(conn, '0')
                        rawlog.extend(read_available(conn, .2))
                        flush = set_flush(conn, desired_flush, flush, rawlog)
                        # Command sequences sent individually; no additional Serial during measurement.
                        for c in command:
                            send(conn, c)
                            # Read setup/ack messages before starting next command.
                            rawlog.extend(read_available(conn, .25))
                        # Flush incoming setup text, then let test run undisturbed.
                        read_available(conn, .1)
                        time.sleep(args.duration)
                        send(conn, 'G')  # G stops acquisition before streaming CSV.
                        stream, complete = collect_export(conn, timeout=args.export_timeout)
                        (root/(prefix+'_serial.txt')).write_text('\n'.join(rawlog)+'\n'+stream, encoding='utf-8')
                        if not complete:
                            raise ValueError('Incomplete G export (END_SAMPLES or END_DIAG missing)')
                        sample_meta, rows, sample_cols = section_from_text(stream, 'SAMPLES')
                        diag_meta, diag, diag_cols = section_from_text(stream, 'DIAG')
                        if diag_meta.get('flush_enabled') not in ('1' if flush else '0',):
                            raise ValueError('Firmware reported unexpected flush state '+str(diag_meta))
                        write_csv(root/(prefix+'_samples.csv'), sample_cols, rows)
                        write_csv(root/(prefix+'_diag.csv'), diag_cols, diag)
                        cols, joined = derived_rows(rows, sample_meta, diag)
                        write_csv(root/(prefix+'_combined.csv'), cols, joined)
                        stats = summary_stats(joined)
                        record = {'test':name, 'repeat':repeat,'status':'PASS', 'sample_meta':sample_meta,
                                  'diag_meta':diag_meta, 'stats':stats}
                        print(f'   PASS: {len(rows)} samples; mean latency={stats["dispatch_latency_us_mean"]} us; '
                              f'ISR overlap during loads={stats["samples_with_isr_during_load"]}')
                    except Exception as exc:
                        record = {'test':name, 'repeat':repeat,'status':'FAIL','reason':str(exc)}
                        (root/(prefix+'_error.txt')).write_text(str(exc)+'\n',encoding='utf-8')
                        print('   FAIL:',exc,file=sys.stderr)
                    all_summary.append(record)
                    (root/'summary.json').write_text(json.dumps(all_summary,indent=2), encoding='utf-8')
            send(conn, '0')
            print(f'Finished. Results folder: {root}')
    except (serial.SerialException, OSError) as e:
        print(f'Serial connection problem: {e}',file=sys.stderr)
        print(f'Any completed results are in {root}',file=sys.stderr)
        raise SystemExit(1)
    failed = sum(r['status'] != 'PASS' for r in all_summary)
    print(f'Completed {len(all_summary)-failed}/{len(all_summary)}; failed {failed}.')
    print('Send the entire timestamped results folder as a ZIP for analysis.')
    if failed:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
