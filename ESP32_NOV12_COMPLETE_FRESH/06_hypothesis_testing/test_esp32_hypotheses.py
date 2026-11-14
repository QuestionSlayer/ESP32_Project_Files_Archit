import zipfile,io,numpy as np,pandas as pd
from pathlib import Path
from scipy.stats import pearsonr
P=Path('/mnt/data/esp32_hypothesis_tests');P.mkdir(exist_ok=True)
z=zipfile.ZipFile('/mnt/data/esp32_preflight_results.zip'); name=next(s for s in z.namelist() if s.endswith('/all_timer_samples.csv'))
df=pd.read_csv(io.BytesIO(z.read(name)))
for c in ['period_us','dispatch_latency_us','flash_work_us','isr_time_relative_us','isr_entry_cycles']:
 df[c]=pd.to_numeric(df[c],errors='coerce')
print('dataset',len(df),df.test.value_counts().to_dict())
rows=[]; phase=[]; overlap=[]; acf=[]; nextw=[]
for (mode,run),g in df.groupby(['test','repeat']):
 g=g.sort_values('sample_index').reset_index(drop=True)
 x=g.dispatch_latency_us.to_numpy(float); w=g.flash_work_us.to_numpy(float); period=g.period_us.to_numpy(float); t=g.isr_time_relative_us.to_numpy(float)
 ok=np.isfinite(x)&np.isfinite(w)&np.isfinite(t)
 if ok.sum()<50:continue
 # Time relative to corresponding ISR entry: dispatcher starts at t + latency.
 # Next ISR can arrive during current callback if t_next - (t_i+latency_i) <= measured work duration, but this upper-bounds direct overlap since setup/flush prior to measured work.
 avail=t[1:]-t[:-1]-x[:-1]
 maybe=(w[:-1] >= avail)&np.isfinite(avail)
 already=(avail<=0)&np.isfinite(avail)
 valid=np.isfinite(avail)&np.isfinite(w[:-1]);
 overlap.append(dict(test=mode,repeat=run,n=int(valid.sum()),next_isr_before_dispatch_pct=float(100*np.mean(already[valid])),next_isr_before_work_end_upper_bound_pct=float(100*np.mean(maybe[valid])),slack_median_us=float(np.median(avail[valid]-w[:-1][valid]))))
 # Approx net period and phase based on sample_index modulo 20, with own run start phase arbitrary.
 for metric,vals in [('latency',x),('work',w),('signed_period',period-50)]:
  valids=np.isfinite(vals)
  a=np.arange(len(vals))[valids]%20; v=vals[valids]
  means=np.array([v[a==i].mean() for i in range(20)])
  between=np.mean((means-v.mean())**2)
  total=np.mean((v-v.mean())**2)
  eta=between/total if total else np.nan
  # Compute autocorrelation at lag 19,20,21; 40; with centered values
  def ac(k):
   aa=vals[:-k]; bb=vals[k:]; mask=np.isfinite(aa)&np.isfinite(bb)
   return float(np.corrcoef(aa[mask],bb[mask])[0,1]) if mask.sum()>10 else np.nan
  phase.append(dict(test=mode,repeat=run,metric=metric,phase20_eta2=eta,acf19=ac(19),acf20=ac(20),acf21=ac(21),acf40=ac(40),phase_max_minus_min=float(means.max()-means.min()),phase_peak_mod=int(means.argmax())))
 # Find relationship of work to next period - distinguish true adjacent work vs potentially backlog.
 for offset in [-2,-1,0,1,2,3]:
  # correlation w_i vs period_{i+offset}
  if offset>=0: aa=w[:len(w)-offset] if offset else w;bb=period[offset:]
  else: aa=w[-offset:];bb=period[:len(period)+offset]
  valid=np.isfinite(aa)&np.isfinite(bb)
  nextw.append(dict(test=mode,repeat=run,offset=offset,correlation=float(np.corrcoef(aa[valid],bb[valid])[0,1]) if valid.sum()>10 else np.nan))
 # latency clustering and predictive event backlog: 'dispatcher already active' heuristic negative slack
 immediate=(x<10)
 rows.append(dict(test=mode,repeat=run,n=len(g),under10_pct=100*np.nanmean(immediate),over50_pct=100*np.nanmean(x>50),cache_work_gt20_pct=100*np.nanmean(w>20),overlap_upperbound_pct=100*np.mean(maybe[np.isfinite(avail)&np.isfinite(w[:-1])])))
for filename,data in [('timing_overlap_proxies.csv',overlap),('phase20_per_run.csv',phase),('work_period_lag_scan.csv',nextw),('run_summaries.csv',rows)]: pd.DataFrame(data).to_csv(P/filename,index=False)
phase=pd.DataFrame(phase); o=pd.DataFrame(overlap); lag=pd.DataFrame(nextw);r=pd.DataFrame(rows)
print('\n20-phase summary')
print(phase.groupby(['test','metric'])[['phase20_eta2','acf19','acf20','acf21','acf40','phase_max_minus_min']].mean().round(3).to_string())
print('\nOverlap')
print(o.groupby('test')[['next_isr_before_dispatch_pct','next_isr_before_work_end_upper_bound_pct','slack_median_us']].mean().round(2).to_string())
print('\nwork->period lag correlations')
print(lag.groupby(['test','offset']).correlation.mean().unstack().round(3).to_string())
print('\nlow lat distribution')
print(r.groupby('test')[['under10_pct','over50_pct']].mean().round(3).to_string())
# distinct modes of work vs 20-phase
for mode in ['cache100','cache50','stress1','stress5']:
 g=df[(df.test==mode)&(df.repeat==2)].sort_values('sample_index')
 if len(g):
  a=g.flash_work_us.to_numpy(float);p=g.period_us.to_numpy(float);t=g.isr_time_relative_us.to_numpy(float);l=g.dispatch_latency_us.to_numpy(float)
  if mode=='cache100':
   # Compare measured next period by clustered work bin and by phase
   kk=np.arange(len(g))%20
   for v in [a<=23,a>23]:
    y=p[1:][v[:-1]];print('cache100 work cluster',int(v.sum()),'next period mean',np.nanmean(y),'SD',np.nanstd(y))
   pd.DataFrame({'phase':kk,'work':a,'period':p,'latency':l}).groupby('phase').agg(['mean','std']).to_csv(P/'cache100_phase20_example.csv')
# plot phase and acfs
import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
fig,axs=plt.subplots(2,1,figsize=(9,7),layout='constrained')
for mode in ['stress1','stress5','cache50','cache100']:
 sub=phase[(phase.test==mode)&(phase.metric=='latency')]
 if len(sub):axs[0].plot([19,20,21,40],[sub.acf19.mean(),sub.acf20.mean(),sub.acf21.mean(),sub.acf40.mean()],marker='o',label=mode)
axs[0].legend();axs[0].set(title='Autocorrelation versus lag (dispatch latency)',ylabel='Pearson correlation',xlabel='Lag (events)')
for mode in ['stress1','stress5','cache50','cache100']:
 sub=o[o.test==mode]
 if len(sub):axs[1].bar(mode,sub.next_isr_before_dispatch_pct.mean())
axs[1].set(ylabel='Percent',title='Next ISR timestamp preceding current dispatch timestamp (event-order proxy)')
fig.savefig(P/'phase_and_backlog.png',dpi=160)
