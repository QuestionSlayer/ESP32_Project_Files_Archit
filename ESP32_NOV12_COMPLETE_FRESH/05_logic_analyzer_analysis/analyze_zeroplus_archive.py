from pathlib import Path
import json,zipfile,statistics
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path('/mnt/data/zeroplus_processed/zeroplus_11nov'); OUT=Path('/mnt/data/zeroplus_analysis'); OUT.mkdir(exist_ok=True)
rows=[]; pulse_dfs=[]; period_dfs=[]
for sf in sorted(ROOT.rglob('summary.json')):
 folder=sf.parent; s=json.loads(sf.read_text()); name=str(folder.relative_to(ROOT));
 p=pd.read_csv(folder/'high_pulses.csv'); q=pd.read_csv(folder/'rising_periods.csv')
 p['capture']=name;q['capture']=name; pulse_dfs.append(p);period_dfs.append(q)
 entry={'capture':name,'duration_ms':s['capture_duration_ms'],'compressed_records':s['compressed_records']}
 for c in range(8):
  sub=p[p.channel==f'A{c}']; per=q[q.channel==f'A{c}']
  entry[f'A{c}_pulses']=len(sub)
  if len(sub):
   entry[f'A{c}_width_median_us']=sub.width_us.median();entry[f'A{c}_width_mean_us']=sub.width_us.mean();entry[f'A{c}_width_p95_us']=sub.width_us.quantile(.95);entry[f'A{c}_width_max_us']=sub.width_us.max()
  if len(per):entry[f'A{c}_period_median_us']=per.period_us.median();entry[f'A{c}_period_mean_us']=per.period_us.mean();entry[f'A{c}_period_sd_us']=per.period_us.std()
 entry['spi_bytes']=s['spi_full_bytes'];entry['spi_mismatch']=s['spi_mismatched_bytes'];entry['spi_cs_low_us']=s['spi_cs_low_intervals_us'][0] if s['spi_cs_low_intervals_us'] else np.nan
 rows.append(entry)
summary=pd.DataFrame(rows); summary.to_csv(OUT/'capture_inventory_statistics.csv',index=False)
pulses=pd.concat(pulse_dfs,ignore_index=True); periods=pd.concat(period_dfs,ignore_index=True)
# Focus on timer periods and LUT output period: don't include implausible edge fragments
st=periods[(periods.capture.str.contains('02_Stress|03_Cache|Reg_overflow|regoverflow'))&(periods.channel=='A2')].copy()
st['signed_jitter_us']=st.period_us-50;st['abs_jitter_us']=st.signed_jitter_us.abs()
def stats(a):
 a=np.asarray(a,dtype=float); a=a[np.isfinite(a)]
 if not len(a):return {'n':0}
 return {'n':len(a),'mean':a.mean(),'sd':a.std(ddof=1) if len(a)>1 else np.nan,'median':np.median(a),'p05':np.quantile(a,.05),'p95':np.quantile(a,.95),'p99':np.quantile(a,.99),'min':a.min(),'max':a.max()}
st_rows=[]
for name,g in st.groupby('capture'):
 for met in ['period_us','signed_jitter_us','abs_jitter_us']:
  st_rows.append({'capture':name,'channel':'A2','metric':met,**stats(g[met])})
for name,g in periods[(periods.capture.str.contains('02_Stress|03_Cache|Reg_overflow|regoverflow')) & (periods.channel=='A0')].groupby('capture'):
 st_rows.append({'capture':name,'channel':'A0','metric':'lut_period_us',**stats(g.period_us)})
pd.DataFrame(st_rows).to_csv(OUT/'timer_and_lut_period_statistics.csv',index=False)
# cache pulse widths / A1, marker includes overhead
cache=[]
for name,g in pulses[(pulses.capture.str.contains('03_Cache')) & (pulses.channel=='A1')].groupby('capture'):
 cache.append({'capture':name,**stats(g.width_us)})
pd.DataFrame(cache).to_csv(OUT/'cache_gpio22_pulse_statistics.csv',index=False)
# UART interrupts, exclude first and last special pulse(s) for regular cadence and highlight paired events
uart=[]
for name,g in summary[summary.capture.str.contains('01_Transfer')].iterrows():
 row=g.to_dict();nm=row['capture'];a=periods[(periods.capture==nm)&(periods.channel=='A2')].period_us.values
 big=a[(a>=20)&(a<1250)];short=a[(a<20)]; last=a[a>=1250]
 uart.append({'capture':nm,'frame_gpio25_max_us':row.get('A0_width_max_us',np.nan), 'gpio19_ISR_pulses':row.get('A2_pulses',0),
 'gpio19_short_gap_count':len(short),'gpio19_short_gap_median_us':np.median(short) if len(short) else np.nan,
 'gpio19_long_gap_count':len(big),'gpio19_long_gap_median_us':np.median(big) if len(big) else np.nan,
 'gpio19_terminal_gap_us':last.max() if len(last) else np.nan,'gpio22_service_high_width_median_us':row.get('A1_width_median_us',np.nan),
 'gpio22_service_high_width_max_us':row.get('A1_width_max_us',np.nan), 'spi_bytes':row['spi_bytes'], 'spi_cs_low_us':row['spi_cs_low_us']})
pd.DataFrame(uart).to_csv(OUT/'uart_and_spi_timing.csv',index=False)
# DAC pulse distribution, exclude long gaps from pulse counting but keep maxima
DAC=[]
for name,g in pulses[pulses.capture.str.contains('SetupB')].groupby('capture'):
 for ch in ['A0','A1']:
  h=g[g.channel==ch]
  DAC.append({'capture':name,'channel':ch,**stats(h.width_us),'long_gt_1ms':int((h.width_us>1000).sum()),'long_gt_10ms':int((h.width_us>10000).sum())})
pd.DataFrame(DAC).to_csv(OUT/'dac_pulse_statistics.csv',index=False)
# Register three sections
reg=pulses[(pulses.capture.str.contains('regflow_1000x_comp'))&(pulses.channel=='A1')].sort_values('rise_us')
reg.assign(per_iteration_us=reg.width_us/1000).to_csv(OUT/'register_triplet.csv',index=False)
# Aggregate all edge measurements into useful compact zip direct
pulses.to_csv(OUT/'all_high_pulses.csv',index=False);periods.to_csv(OUT/'all_rising_periods.csv',index=False)
# plots
plt.figure(figsize=(10,5));
for name in ['02_Stress/Baseline_01','02_Stress/Baseline_02','02_Stress/HighStress_01','02_Stress/Highstress_02']:
 a=st[st.capture==name].period_us.values; a=a[(a>20)&(a<100)]
 plt.hist(a,bins=np.arange(25,80,1),density=True,histtype='step',linewidth=1.6,label=name.split('/')[-1]);
plt.axvline(50,linestyle='--',color='black',linewidth=.8);plt.xlabel('A2 ISR rising-edge period (µs)');plt.ylabel('Density');plt.title('External ISR-entry period distributions');plt.legend(fontsize=8);plt.tight_layout();plt.savefig(OUT/'isr_period_histograms.png',dpi=170);plt.close()
plt.figure(figsize=(10,5));
for name in ['02_Stress/Baseline_01','02_Stress/Baseline_02','02_Stress/HighStress_01','02_Stress/Highstress_02']:
 a=np.sort(st[st.capture==name].abs_jitter_us.values);plt.plot(a,np.arange(1,len(a)+1)/len(a),label=name.split('/')[-1]);
plt.xlim(0,50);plt.xlabel('Absolute period jitter (µs)');plt.ylabel('Empirical CDF');plt.title('External ISR-entry jitter ECDF');plt.legend(fontsize=8);plt.tight_layout();plt.savefig(OUT/'isr_jitter_ecdf.png',dpi=170);plt.close()
plt.figure(figsize=(10,5));
for name in ['03_Cache/Warm_01','03_Cache/cache125_01','03_Cache/cache50_01','03_Cache/coldlinemax_01']:
 a=pulses[(pulses.capture==name)&(pulses.channel=='A1')].width_us
 plt.hist(a,bins=np.arange(0,65,.5),density=True,histtype='step',linewidth=1.5,label=name.split('/')[-1]);
plt.xlabel('GPIO22 marked work HIGH duration (µs)');plt.ylabel('Density');plt.title('Cache workload external pulse-width distributions');plt.legend(fontsize=8);plt.tight_layout();plt.savefig(OUT/'cache_gpio22_widths.png',dpi=170);plt.close()
plt.figure(figsize=(9,5));modes=['Intr_8B_01','Intr_16B_01','Intr_64B_01','Intr_120B_01'];
for i,n in enumerate(modes):
 name='01_Transfer/'+n; a=periods[(periods.capture==name)&(periods.channel=='A2')].period_us.values
 plt.scatter(np.full(len(a),i)+np.random.default_rng(10).uniform(-.07,.07,len(a)),a,s=10,alpha=.55)
plt.yscale('symlog',linthresh=10);plt.xticks(range(4),['8B','16B','64B','120B']);plt.ylabel('Consecutive A2 rising-edge gap (µs), symlog');plt.title('UART IRQ marker pulses: alternating short and refill gaps');plt.tight_layout();plt.savefig(OUT/'uart_irq_gaps.png',dpi=170);plt.close()
plt.figure(figsize=(9,4));names=['Run_v_01','Run_w_01','Run_f_01','Run_x_01'];values=[]
for n in names:
 a=pulses[(pulses.capture=='SetupB/'+n)&(pulses.channel=='A1')];s=summary[summary.capture=='SetupB/'+n].iloc[0]; values.append(len(a)/(s.duration_ms/1000))
plt.bar(['8','64','256','1024'],values);plt.ylabel('Observed feeder GPIO22 pulses / captured second');plt.xlabel('Requested buffer samples');plt.title('DAC feeder-call marker density');plt.tight_layout();plt.savefig(OUT/'dac_feeder_pulse_density.png',dpi=170);plt.close()
plt.figure(figsize=(9,4));
if len(reg):
 plt.bar(['shallow','deep','forced spill'][:len(reg)],reg.width_us.values/1000)
plt.ylabel('Duration per iteration (µs)');plt.title('Register-window benchmark: 1,000-iteration windows');plt.tight_layout();plt.savefig(OUT/'register_benchmark.png',dpi=170);plt.close()
print('Captures',len(summary),'pulse rows',len(pulses),'period rows',len(periods))
print('timer',pd.DataFrame(st_rows).query("metric=='period_us'")[['capture','n','mean','sd','median','p95','max']].to_string(index=False))
print('cache',pd.DataFrame(cache)[['capture','n','mean','sd','median','p95']].to_string(index=False))
print('uart',pd.DataFrame(uart)[['capture','frame_gpio25_max_us','gpio19_ISR_pulses','gpio19_short_gap_median_us','gpio19_long_gap_median_us','gpio19_terminal_gap_us']].to_string(index=False))
print('dac',pd.DataFrame(DAC)[['capture','channel','n','median','max','long_gt_10ms']].to_string(index=False))
print('reg',reg[['rise_us','width_us']].to_string(index=False))
