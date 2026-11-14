#!/usr/bin/env python3
"""Experimental ZEROPLUS .alc waveform recovery for files with a compatible packed zlib sample stream.
Exports *sample indices*, not absolute times, until the file's timebase is verified.
Usage: python alc_to_csv.py capture.alc -o outdir
"""
import argparse, csv, pathlib, struct, zlib

def extract(path):
    raw = pathlib.Path(path).read_bytes()
    # Locate a zlib stream whose output is packed 4-byte capture words.
    candidates = []
    for pos in range(min(len(raw)-2, 4096)):
        if raw[pos] != 0x78 or raw[pos+1] not in (0x01,0x5e,0x9c,0xda):
            continue
        try:
            decompressor = zlib.decompressobj()
            payload = decompressor.decompress(raw[pos:]) + decompressor.flush()
            if decompressor.eof and len(payload) >= 4096 and len(payload)%4 == 0:
                candidates.append((pos, payload))
        except zlib.error:
            pass
    if len(candidates) != 1:
        raise ValueError(f'Expected exactly one compatible zlib sample stream; found {len(candidates)}')
    pos, blob = candidates[0]
    if any(blob[i] != 0 or blob[i+1] != 0 for i in range(1,len(blob),4)):
        raise ValueError('Unrecognized capture word structure; refusing unvalidated decode')
    return pos, blob[0::4]

def main():
    p=argparse.ArgumentParser();p.add_argument('alc');p.add_argument('-o','--output',default='alc_recovered'); args=p.parse_args()
    out=pathlib.Path(args.output);out.mkdir(parents=True,exist_ok=True)
    offset,states=extract(args.alc)
    with (out/'digital_samples.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['sample_index']+[f'A{i}' for i in range(8)])
        for i,v in enumerate(states): w.writerow([i]+[(v>>j)&1 for j in range(8)])
    counts=[0]*8
    with (out/'digital_edges.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['sample_index','channel','edge','new_level'])
        for i in range(1,len(states)):
            diff=states[i]^states[i-1]
            for j in range(8):
                if diff&(1<<j):
                    new=(states[i]>>j)&1
                    w.writerow([i,f'A{j}','rising' if new else 'falling',new]);counts[j]+=1
    # SPI mode 0, sample MOSI/MISO at SCLK rising edge, if all expected channel bits exist.
    rising=[i for i in range(1,len(states)) if not(states[i-1]&16) and states[i]&16]
    if rising:
        with (out/'spi_decoded_bytes.csv').open('w',newline='') as f:
            w=csv.writer(f);w.writerow(['byte_index','first_rising_edge_sample_index','mosi_hex','miso_hex','match'])
            for k in range(0,len(rising)//8*8,8):
                indexes=rising[k:k+8]
                def decode(pin):
                    x=0
                    for ix in indexes: x=(x<<1)|((states[ix]>>pin)&1)
                    return x
                tx,rx=decode(5),decode(6)
                w.writerow([k//8,indexes[0],f'{tx:02X}',f'{rx:02X}',int(tx==rx)])
    with (out/'DECODE_NOTES.txt').open('w') as f:
        f.write(f'Source: {args.alc}\nZlib data offset: {offset}\nSamples: {len(states)}\n')
        f.write('Channel states use bit j of first byte of a 4-byte sample word for Aj.\n')
        f.write('Absolute sample timebase NOT VERIFIED. Sample-index positions are trustworthy; do NOT report timing from these CSVs without calibration or official export.\n')
        f.write('SPI decoding assumes A4 clock A5 MOSI A6 MISO, mode 0 MSB first. No independent guarantee that firmware SPI configuration matched those settings.\n')
        f.write('Edge counts: '+str(dict(enumerate(counts)))+'\n')
        f.write(f'SPI rising SCLK edges: {len(rising)}; decoded bytes: {len(rising)//8}.\n')
    print(f'Extracted {len(states)} samples, {sum(counts)} channel edges and {len(rising)//8} SPI bytes to {out}')

if __name__=='__main__':main()
