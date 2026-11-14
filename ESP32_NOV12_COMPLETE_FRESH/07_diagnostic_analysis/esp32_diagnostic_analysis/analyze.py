from pathlib import Path
import pandas as pd, numpy as np, json, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import zipfile
root=next(Path('/mnt/data/diag_audit/esp32_diag_results').iterdir())
out=Path('/mnt/data/esp32_diagnostic_analysis');out.mkdir(exist_ok=True)
names=['cache50_on','cache50_off','cache100_on','cache100_off','stress1_warm','stress1_cold','stress5_warm','stress5_cold']
D={k:pd.read_csv(root/f'{k}_r01_combined.csv') for k in names}
summary=[]
for k,d in D.items():
 r={'condition':k,'n':len(d),'period_mean_us':d.period_us.mean(),'period_sd_us':d.period_us.std(),'abs_jitter_mean_us':d.abs_jitter_us.mean(),'abs_jitter_p95_us':d.abs_jitter_us.quantile(.95),'dispatch_mean_us':d.dispatch_latency_us.mean(),'dispatch_sd_us':d.dispatch_latency_us.std(),'dispatch_p95_us':d.dispatch_latency_us.quantile(.95),'dispatch_gt50_pct':100*(d.dispatch_latency_us>50).mean(),'dispatch_lt10_pct':100*(d.dispatch_latency_us<10).mean(),'load_mean_us':d.load_work_us.mean(),'load_sd_us':d.load_work_us.std(),'flush_mean_us':d.cache_flush_us.mean(),'flush_p95_us':d.cache_flush_us.quantile(.95),'full_callback_mean_us':d.full_callback_us.mean(),'isr_during_flush_count':int(d.isr_during_flush.sum()),'isr_during_load_count':int(d.isr_during_load.sum()),'load_overlap_event_pct':100*(d.isr_during_load>0).mean(),'flush_overlap_event_pct':100*(d.isr_during_flush>0).mean(),'ring_nonzero_pct':100*(d.ring_depth_after_pop>0).mean(),'max_ring_depth':int(d.ring_depth_after_pop.max()),'index_contiguous':bool(np.all(np.diff(d['index'])==1))}
 summary.append(r)
pd.DataFrame(summary).to_csv(out/'condition_statistics.csv',index=False,float_format='%.6f')
loads=[]
for k,d in D.items():
 for n,g in d.groupby(d.isr_during_load>0):
  loads.append({'condition':k,'overlap':bool(n),'n':len(g),'mean_load_us':g.load_work_us.mean(),'median_load_us':g.load_work_us.median(),'p95_load_us':g.load_work_us.quantile(.95)})
pd.DataFrame(loads).to_csv(out/'load_isr_overlap.csv',index=False,float_format='%.6f')
ring=[]
for k in ['stress5_warm','stress5_cold']:
 d=D[k]
 for depth,g in d.groupby('ring_depth_after_pop'):
  ring.append({'condition':k,'depth_after_pop':depth,'n':len(g),'mean_dispatch_us':g.dispatch_latency_us.mean(),'median_dispatch_us':g.dispatch_latency_us.median(),'fast_lt10_count':int((g.dispatch_latency_us<10).sum()),'fast_lt10_pct':100*(g.dispatch_latency_us<10).mean()})
pd.DataFrame(ring).to_csv(out/'ring_depth_dispatch.csv',index=False,float_format='%.6f')
# simple longitudinal marker
phase=[]
for k,d in D.items():
 x=d.dispatch_latency_us.to_numpy(dtype=float)
 for lag in [1,19,20,21,40]:
  phase.append({'condition':k,'lag':lag,'autocorr_dispatch':float(np.corrcoef(x[:-lag],x[lag:])[0,1])})
pd.DataFrame(phase).to_csv(out/'lag_autocorrelation.csv',index=False)
# plots
fig,ax=plt.subplots(figsize=(9,4.8))
xs=np.arange(4); means=[D[k].abs_jitter_us.mean() for k in names[:4]]
ax.bar(xs,means);ax.set_xticks(xs,['8-line ON','8-line OFF','16-line ON','16-line OFF']);ax.set_ylabel('Mean absolute ISR-period jitter (µs)');ax.set_title('Cache flush intervention: ISR-period jitter');fig.tight_layout();fig.savefig(out/'cache_jitter_flush.png',dpi=170);plt.close(fig)
fig,ax=plt.subplots(figsize=(9,4.8))
for k in names[:4]:
 x=np.sort(D[k].abs_jitter_us.to_numpy());y=np.arange(1,len(x)+1)/len(x);ax.plot(x,y,label=k)
ax.set_xlabel('Absolute ISR period jitter (µs)');ax.set_ylabel('ECDF');ax.legend();ax.set_title('Cache ISR jitter distributions');fig.tight_layout();fig.savefig(out/'cache_jitter_ecdf.png',dpi=170);plt.close(fig)
fig,ax=plt.subplots(figsize=(9,4.8))
for k in ['cache50_on','cache50_off','cache100_on','cache100_off']:
 x=np.sort(D[k].load_work_us.to_numpy());y=np.arange(1,len(x)+1)/len(x)
 ax.plot(x,y,label=k)
ax.set_xlabel('Marked load duration (µs)');ax.set_ylabel('ECDF');ax.legend();ax.set_title('Load durations with / without explicit cache flush');fig.tight_layout();fig.savefig(out/'load_duration_ecdf.png',dpi=170);plt.close(fig)
fig,ax=plt.subplots(figsize=(9,4.8))
for k in ['stress1_warm','stress5_warm','stress1_cold','stress5_cold']:
 x=np.sort(D[k].dispatch_latency_us.to_numpy());y=np.arange(1,len(x)+1)/len(x);ax.plot(x,y,label=k)
ax.set_xlabel('ISR-to-dispatch latency (µs)');ax.set_ylabel('ECDF');ax.legend();ax.set_title('Controlled warm/cold × stress comparisons');fig.tight_layout();fig.savefig(out/'stress_dispatch_ecdf.png',dpi=170);plt.close(fig)
fig,ax=plt.subplots(figsize=(9,4.8))
for k in ['stress5_warm','stress5_cold']:
 vals=D[k].groupby('ring_depth_after_pop').dispatch_latency_us.mean()
 ax.plot(vals.index,vals.to_numpy(),marker='o',label=k)
ax.set_xlabel('Ring entries pending after event is popped');ax.set_ylabel('Mean dispatch latency (µs)');ax.set_xticks([0,1,2,3]);ax.legend();ax.set_title('High-stress backlog and latency');fig.tight_layout();fig.savefig(out/'ring_depth_latency.png',dpi=170);plt.close(fig)
# quality
report=[]
report.append('# ESP32 diagnostic preflight: quantitative findings\n')
report.append('**Dataset:** 8 conditions, one sequential run per condition, each 1,024 retained events. All combined CSVs parse with contiguous indices and no NaN; `summary.json` labels every run PASS. These are the **last** 1,024 samples of acquisitions that processed approximately 14k events per condition, not full-session records. No simultaneous ZEROPLUS waveforms included in this ZIP.\n')
report.append('## Most important controlled observation\n')
report.append('| condition | abs ISR jitter mean | load duration mean | flush cost mean | full callback mean | ISR load-overlap |\n|---|---:|---:|---:|---:|---:|')
for k in names[:4]:
 d=D[k]; report.append(f'| {k} | {d.abs_jitter_us.mean():.3f} µs | {d.load_work_us.mean():.3f} µs | {d.cache_flush_us.mean():.3f} µs | {d.full_callback_us.mean():.3f} µs | {(d.isr_during_load>0).mean()*100:.1f}% |')
report.append('\n- Disabling flush reduces 8-line jitter 9.281→0.769 µs (~91.7%), but 16-line jitter only 6.463→5.872 µs (~9.1%). Thus flush ON/OFF has qualitatively different impacts on observed ISR timing under the two access patterns.\n- Crucially, **non-overlapped load duration is almost unchanged** across flush ON/OFF: cache50 10.647 µs (ON, no ISR in load) vs 10.692 µs (OFF, all); cache100 20.167 µs (ON, no ISR) vs 20.232 µs (OFF, no ISR). This challenges a claim that the mode separation directly measures first-touch cache misses after invalidation. Loop instruction/address sequence or flash-data placement may dominate. Disabling flush does not make the access pattern identical between 8 and 16 lines.\n- The flush API itself takes ~4.23–4.25 µs (ON), versus no-op diagnostic interval ~0.094 µs (OFF). Without full CPU/cache register verification, do not infer exactly which cache lines were invalidated or that misses were 50%/100%.\n')
report.append('## Interrupt overlap explains most of cache100 ON load-width bimodality\n')
for k in ['cache100_on','cache50_on','cache100_off','stress5_cold']:
 d=D[k]; g=d.groupby(d.isr_during_load>0).load_work_us.agg(['size','mean']);report.append(f'- {k}: '+', '.join(f'{"with ISR" if v else "without ISR"} n={int(row["size"])} mean={row["mean"]:.3f} µs' for v,row in g.iterrows())+'.')
report.append('\nThis directly supports ISR overlap extending the measured load interval; it does not explain a cache refill penalty independent of ISR, and the counter relies on ISR access to the diagnostic state.\n')
report.append('## Stress and ring depth\n')
for k in ['stress1_warm','stress5_warm','stress1_cold','stress5_cold']:
 d=D[k];report.append(f'- {k}: mean dispatch {d.dispatch_latency_us.mean():.3f} µs, SD {d.dispatch_latency_us.std():.3f} µs; depth>0 {(d.ring_depth_after_pop>0).mean()*100:.1f}%; latency<10 µs {(d.dispatch_latency_us<10).mean()*100:.1f}%.')
report.append('\n**Correction to earlier hypothesis:** In BOTH high-stress runs, every fast (<10 µs) event has `ring_depth_after_pop == 0`; none of the events with a nonzero ring depth are fast. Ring depth strongly tracks *large* latency instead: warm high stress mean latency by depths 0,1,2,3 is about 23,74,110,168 µs; cold high stress 22,74,119,169 µs. This conflicts with the earlier prediction that unusually fast events would coincide with nonempty ring depth, although ring depth measured after the pop cannot establish whether the task was already running.\n')
report.append('## Data caveats\n- Single recording per condition; 1,024 adjacent events are dependent, and there are no independent repetitions for variance across runs or confidence intervals.\n- Cache OFF may still incur cache misses through other mechanisms; cache ON invalidation also perturbs unrelated code/data residency. A source-level/ELF audit of `flash_rodata_table` placement and the generated loops is high priority.\n- `isr_during_flush` is zero in all four standalone cache conditions, but is nonzero in stress5_cold; zero cannot establish that interrupts were unaffected during flushing (interrupts could be deferred).\n- A few measurements show marked callback durations exceeding the 50 µs timer; ring-depth records and ISR counters must be checked before attributing such events to pure cache behavior.\n- The ZIP has no `d`, `y` or `z` trials, so it cannot diagnose first-run SPI DMA or DAC output timing. Use their separate lab `.alc`/serial logs.\n')
(out/'FINDINGS.md').write_text('\n'.join(report))
import shutil
shutil.copy('/mnt/data/diag_audit/analyze.py',out/'analyze.py')
zpath='/mnt/data/ESP32_diagnostic_results_analysis.zip'
with zipfile.ZipFile(zpath,'w',compression=zipfile.ZIP_DEFLATED) as z:
 for f in out.rglob('*'):
  if f.is_file():z.write(f, f.relative_to(out.parent))
print('created',zpath, 'files',len(list(out.glob('*'))))
print('\n'.join(report)[:7000])
