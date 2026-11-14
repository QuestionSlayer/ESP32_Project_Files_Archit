"""ZEROPLUS .alc decoder (independent re-implementation for the report pipeline).

Reverse-engineered layout, validated in p3_analyzer.py against crystal-derived
signals (UART bit time, SPI clock, GPTimer period, DAC byte clock):

  header (337 bytes)
    0x008  acquisition time  "hh:mm:ss"      0x012  acquisition date "mm/dd/yy"
    0x12C  float64  sample rate in Hz        0x134  uint32   memory depth (records)
    0x144  uint32   index of the trigger record (0 = no pre-trigger region)
  body: one zlib stream of 4-byte run-length records [state, 0, 0, count-1]

RUN-LENGTH SEMANTICS (the correction that matters).  A record is written when
the inputs change or when the 8-bit counter saturates; it stores the NEW state
together with the length of the run that has just ENDED.  The state of record
i therefore lasts count[i+1] ticks, not count[i].  The earlier project decoder
(alc_to_csv_fixed.py) paired state[i] with count[i]; periods of periodic
signals survive that mistake, pulse widths do not.  The corrected pairing is
verified by decoding all 512 UART payload bytes and by the agreement of marker
widths with the on-chip cycle counter (see validation/alc_validation.json).

Records before the trigger index are NOT valid run-length data: the vendor
header counts them as one tick each, and in the 12-Nov session they hold
uninitialised memory (non-zero bytes 1 and 2).  They are discarded; t = 0 is
the start of the trigger record.  Nothing is interpolated or synthesised.
"""
import zlib, pathlib, struct
import numpy as np

def find_streams(raw, limit=1 << 16):
    out = []
    for off in range(min(len(raw) - 2, limit)):
        if raw[off] != 0x78 or raw[off + 1] not in (0x01, 0x5E, 0x9C, 0xDA):
            continue
        try:
            d = zlib.decompressobj()
            payload = d.decompress(raw[off:]) + d.flush()
        except zlib.error:
            continue
        if d.eof and len(payload) >= 1024:
            out.append((off, payload, len(raw) - len(d.unused_data) - off))
    return out

class Capture:
    def __init__(self, path, rate=None, keep_pretrigger=False, legacy_pairing=False):
        self.path = pathlib.Path(path)
        raw = self.path.read_bytes()
        self.acq_time = raw[8:16].decode("ascii", "replace")
        self.acq_date = raw[18:26].decode("ascii", "replace")
        self.header_rate = struct.unpack("<d", raw[300:308])[0]
        self.depth = struct.unpack("<I", raw[308:312])[0]
        self.trig = struct.unpack("<I", raw[324:328])[0]
        if rate is None:
            rate = self.header_rate
        self.raw_len = len(raw)
        streams = [s for s in find_streams(raw) if len(s[1]) % 4 == 0]
        if not streams:
            raise ValueError(f"no zlib capture stream in {path}")
        # take the largest stream
        off, blob, clen = max(streams, key=lambda s: len(s[1]))
        self.header = raw[:off]
        self.stream_offset = off
        a = np.frombuffer(blob, dtype=np.uint8).reshape(-1, 4)
        self.n_total = len(a)
        self.pre_garbage = int(((a[:self.trig, 1] != 0) | (a[:self.trig, 2] != 0)).sum())
        self.pre_edges = int((np.diff(a[:self.trig, 0].astype(int)) != 0).sum()) if self.trig > 1 else 0
        if not keep_pretrigger:
            a = a[self.trig:]
        self.post_garbage = int(((a[:, 1] != 0) | (a[:, 2] != 0)).sum())
        self.b1 = a[:, 1]; self.b2 = a[:, 2]
        self.states = a[:, 0].copy()
        cnt = a[:, 3].astype(np.int64) + 1
        self.count_raw = cnt
        self.rate = rate
        self.tick_us = 1e6 / rate
        if legacy_pairing:      # state[i] lasts count[i]  (historical, wrong)
            self.dur = cnt
            self.t = np.concatenate([[0], np.cumsum(cnt)])
        else:                   # state[i] lasts count[i+1]; last run length unknown
            self.dur = np.concatenate([cnt[1:], [0]])
            self.t = np.concatenate([[0], np.cumsum(self.dur)])
        self.n = len(self.states)
        self.duration_us = self.t[-1] * self.tick_us

    def level(self, ch):
        return (self.states >> ch) & 1

    def edges(self, ch):
        """Return (time_us, new_level) arrays for transitions on channel ch."""
        lv = self.level(ch).astype(np.int8)
        idx = np.nonzero(np.diff(lv))[0] + 1
        return self.t[idx] * self.tick_us, lv[idx]

    def pulses(self, ch, high=True):
        """(start_us, end_us) of complete HIGH (or LOW) pulses."""
        t, lv = self.edges(ch)
        want = 1 if high else 0
        s = []; e = []
        for i in range(len(t) - 1):
            if lv[i] == want and lv[i + 1] != want:
                s.append(t[i]); e.append(t[i + 1])
        return np.array(s), np.array(e)

    def rises(self, ch):
        t, lv = self.edges(ch)
        return t[lv == 1]

    def falls(self, ch):
        t, lv = self.edges(ch)
        return t[lv == 0]

    def step_trace(self, ch, t0=None, t1=None):
        """Edge list suitable for a const-plot: (t_us, level) incl. window ends."""
        t, lv = self.edges(ch)
        l0 = int(self.level(ch)[0])
        ts = np.concatenate([[0.0], t]); ls = np.concatenate([[l0], lv])
        if t0 is None: t0 = 0.0
        if t1 is None: t1 = self.duration_us
        k0 = np.searchsorted(ts, t0, side="right") - 1
        k1 = np.searchsorted(ts, t1, side="left")
        tt = ts[k0:k1].copy(); ll = ls[k0:k1].copy()
        tt[0] = t0
        tt = np.concatenate([tt, [t1]]); ll = np.concatenate([ll, [ll[-1]]])
        return tt, ll
