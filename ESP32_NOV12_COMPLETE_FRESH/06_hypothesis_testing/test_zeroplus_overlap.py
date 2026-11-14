import pandas as pd,numpy as np
from pathlib import Path
p=Path('/mnt/data/esp32_hypothesis_tests')
h=pd.read_csv('/mnt/data/zeroplus_analysis/all_high_pulses.csv')
r=pd.read_csv('/mnt/data/zeroplus_analysis/all_rising_periods.csv')
rows=[]
for cap in sorted(h.capture.unique()):
 if not any(z in cap.lower() for z in ['stress/','cache/']):continue
 a=h[(h.capture==cap)&(h.channel=='A1')].sort_values('rise_us')
 b=h[(h.capture==cap)&(h.channel=='A2')].sort_values('rise_us')
 if len(a)<5 or len(b)<5:continue
 aa=a.rise_us.to_numpy();af=a.fall_us.to_numpy(); bt=b.rise_us.to_numpy();
 # Fraction ISR entry marker rises during observed GPIO22 HIGH
 in_pulse=np.zeros(len(bt),bool)
 for st,en in zip(aa,af):in_pulse|=(bt>=st)&(bt<en)
 idx=np.searchsorted(bt,aa,side='right')
 # For each A1 work pulse, check whether an A2 ISR marker rise falls during it
 rises_in_work=np.searchsorted(bt,af,side='left')-idx
 # Period by previous A1 pulse status: if ISR pulse in A1 workload during previous ISR interval
 intervals=np.diff(bt)
 rsec=r[(r.capture==cap)&(r.channel=='A2')].period_us
 rows.append(dict(capture=cap,n_a1=len(aa),n_isr=len(bt),pct_A2_rises_while_A1_high=100*in_pulse.mean(),pct_A1_pulses_with_A2_rise=100*np.mean(rises_in_work>0),A1_width_mean_us=a.width_us.mean(),A2_period_sd_us=np.std(intervals,ddof=1),A2_abs_jitter_mean_us=np.mean(abs(intervals-50)),A1_width_p90_us=a.width_us.quantile(.9)))
d=pd.DataFrame(rows);d.to_csv(p/'external_work_isr_overlap.csv',index=False);print(d.to_string(index=False, float_format=lambda x:f'{x:.2f}'))
extra=[]
for cap in d.capture:
 a=h[(h.capture==cap)&(h.channel=='A1')].sort_values('rise_us'); b=h[(h.capture==cap)&(h.channel=='A2')].sort_values('rise_us')
 aa=a.rise_us.to_numpy();af=a.fall_us.to_numpy();bt=b.rise_us.to_numpy()
 num=np.searchsorted(bt,af,side='left')-np.searchsorted(bt,aa,side='right'); mask=num>0
 if mask.any() and (~mask).any():
  extra.append(dict(capture=cap,pct_overlap=100*mask.mean(),width_overlap_mean=float(np.mean(a.width_us.to_numpy()[mask])),width_no_overlap_mean=float(np.mean(a.width_us.to_numpy()[~mask])),difference=float(np.mean(a.width_us.to_numpy()[mask])-np.mean(a.width_us.to_numpy()[~mask]))))
E=pd.DataFrame(extra); E.to_csv(p/'external_overlap_width_comparison.csv',index=False); print('\nWIDTH WHEN ISR EDGE COINCIDES',E.to_string(index=False,float_format=lambda x:f'{x:.2f}'))
