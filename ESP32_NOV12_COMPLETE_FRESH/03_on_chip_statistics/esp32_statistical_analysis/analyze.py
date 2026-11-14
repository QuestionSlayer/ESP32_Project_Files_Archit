import os,csv,math,json,collections,zipfile
import numpy as np
from scipy import stats
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path
p=Path('/mnt/data/esp32_statistical_analysis/source/esp32_preflight_results/20261110_221648')
out=Path('/mnt/data/esp32_statistical_analysis')
plots=out/'plots'; plots.mkdir(exist_ok=True)
def rows(file):return list(csv.DictReader(open(p/file,newline='',encoding='utf-8-sig')))
def num(x):
 try:return float(x) if x not in ('',None) else np.nan
 except:return np.nan
def vals(seq,col):return np.array([num(r.get(col)) for r in seq],float)
def desc(a):
 a=np.asarray(a,float);a=a[np.isfinite(a)]
 if not len(a):return {'n':0}
 return {'n':len(a),'mean':float(a.mean()),'sd':float(a.std(ddof=1)) if len(a)>1 else None,'median':float(np.median(a)),'min':float(a.min()),'p05':float(np.percentile(a,5)),'p95':float(np.percentile(a,95)),'p99':float(np.percentile(a,99)),'max':float(a.max())}
def writecsv(file, data):
 if not data:return
 keys=list(data[0]);
 with open(out/file,'w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(data)
samples=rows('all_timer_samples.csv');trans=rows('transfer_trials.csv');trial=rows('trial_status.csv');sumrows=rows('timer_trial_summary.csv')
group=collections.defaultdict(list); rgroup=collections.defaultdict(list)
for r in samples:group[r['test']].append(r);rgroup[(r['test'],int(r['repeat']))].append(r)
rawstats=[]
for mode,rr in sorted(group.items()):
 for metric in ['period_us','signed_jitter_us','abs_jitter_us','dispatch_latency_us','flash_work_us']:
  d=desc(vals(rr,metric));rawstats.append(dict(mode=mode,metric=metric,**d))
writecsv('pooled_event_statistics.csv',rawstats)
runstats=[]
for (mode,rep),rr in sorted(rgroup.items()):
 row={'mode':mode,'run':rep,'samples':len(rr)}
 for metric in ['period_us','abs_jitter_us','dispatch_latency_us','flash_work_us']:
  d=desc(vals(rr,metric));row.update({f'{metric}_{k}':d.get(k) for k in ['n','mean','sd','median','p95','p99','max']})
 runstats.append(row)
writecsv('run_level_distribution_statistics.csv',runstats)
bytest=collections.defaultdict(list)
for row in runstats:bytest[row['mode']].append(row)
between=[]
for mode,rr in sorted(bytest.items()):
 for metric in ['period_us','abs_jitter_us','dispatch_latency_us','flash_work_us']:
  d=desc(np.array([x[f'{metric}_mean'] for x in rr]));between.append(dict(mode=mode,metric=metric,**d))
writecsv('between_run_means.csv',between)
# thresholds: delay exceeding one nominal event period
threshold=[]
for mode,rr in sorted(group.items()):
 arr=vals(rr,'dispatch_latency_us');arr=arr[np.isfinite(arr)]
 threshold.append({'mode':mode,'n':len(arr),'latency_gt_50us_count':int((arr>50).sum()),'latency_gt_50us_fraction':float((arr>50).mean())})
writecsv('latency_threshold_exceedance.csv',threshold)
# adjacent jitter correlation per each run to avoid concatenation artifacts
lags=[]
for (mode,rep),rr in sorted(rgroup.items()):
 a=vals(rr,'signed_jitter_us');a=a[np.isfinite(a)]
 cor=float(np.corrcoef(a[:-1],a[1:])[0,1]) if len(a)>2 and np.std(a)>0 else np.nan
 long=a[:-1]>5; fraction=float((a[1:][long]<-5).mean()) if long.any() else np.nan
 lags.append({'mode':mode,'run':rep,'n_pairs':max(0,len(a)-1),'lag1_corr':cor,'long_gt5_count':int(long.sum()),'followed_by_short_lt_minus5_fraction':fraction})
writecsv('adjacent_jitter_analysis.csv',lags)
# Plot multi panel separate files
plt.rcParams.update({'font.size':10,'savefig.dpi':170})
colors={'stress1':'#2563eb','stress5':'#e76f51','cache_warm':'#2563eb','cache12':'#60a5fa','cache50':'#f59e0b','cache100':'#ef4444'}
for metric,xlabel,name,bins,lim in [('period_us','ISR-entry period (µs)','isr_period_hist',90,(25,75)),('abs_jitter_us','Absolute period jitter (µs)','absolute_jitter_hist',100,(0,25)),('dispatch_latency_us','ISR → dispatcher latency (µs)','dispatch_latency_hist',100,(0,170))]:
 fig,ax=plt.subplots(figsize=(8,4.5))
 for mode in ('stress1','stress5'):
  a=vals(group[mode],metric);a=a[np.isfinite(a)];ax.hist(a,bins=bins,range=lim,alpha=.45,density=True,label=mode,color=colors[mode])
 if metric=='period_us':ax.axvline(50,color='black',ls='--',lw=1,label='50 µs nominal')
 ax.set(xlabel=xlabel,ylabel='Density',title=f'{xlabel} — baseline vs high stress');ax.legend();fig.tight_layout();fig.savefig(plots/(name+'.png'));plt.close(fig)
fig,ax=plt.subplots(figsize=(8,4.5))
for mode in ['stress1','stress5']:
 a=vals(group[mode],'dispatch_latency_us');a=np.sort(a[np.isfinite(a)]);ax.plot(a,np.arange(1,len(a)+1)/len(a),label=mode,color=colors[mode])
ax.axvline(50,ls='--',lw=1,color='black',label='50 µs threshold')
ax.set(xlabel='ISR → dispatcher latency (µs)',ylabel='ECDF',title='Dispatch latency empirical CDF');ax.legend();fig.tight_layout();fig.savefig(plots/'latency_ecdf.png');plt.close(fig)
fig,ax=plt.subplots(figsize=(8,4.5))
for mode in ['stress1','stress5']:
 rr=rgroup[(mode,1)]; x=vals(rr,'isr_time_relative_us')/1000;y=vals(rr,'dispatch_latency_us');ax.plot(x,y,lw=.65,alpha=.85,label=mode,color=colors[mode])
ax.set(xlabel='Time within first run (ms)',ylabel='Dispatch latency (µs)',title='Dispatch latency versus time (first run)');ax.legend();fig.tight_layout();fig.savefig(plots/'latency_timeseries.png');plt.close(fig)
fig,ax=plt.subplots(figsize=(6,5))
for mode in ('stress1','stress5'):
 rr=rgroup[(mode,1)];a=vals(rr,'signed_jitter_us');a=a[np.isfinite(a)];ax.scatter(a[:-1],a[1:],s=8,alpha=.22,label=mode,color=colors[mode])
ax.set(xlabel='Jitter J(i) (µs)',ylabel='Next jitter J(i+1) (µs)',title='Consecutive-period jitter (first run)');ax.legend();fig.tight_layout();fig.savefig(plots/'adjacent_period_jitter.png');plt.close(fig)
fig,ax=plt.subplots(figsize=(8,4.5))
for mode in ('stress1','stress5'):
 d=[x['dispatch_latency_us_mean'] for x in bytest[mode]]
 ax.plot(range(1,len(d)+1),d,'o-',label=mode,color=colors[mode])
ax.set(xlabel='Independent run number',ylabel='Mean dispatch latency (µs)',title='Between-run repeatability');ax.legend();fig.tight_layout();fig.savefig(plots/'latency_by_run.png');plt.close(fig)
# Cache fit using run means, cluster SD and points
cache=['cache_warm','cache12','cache50','cache100'];nlines=np.array([0,2,8,16],float)
means=np.array([np.mean([r['flash_work_us_mean'] for r in bytest[m]]) for m in cache]);sds=np.array([np.std([r['flash_work_us_mean'] for r in bytest[m]],ddof=1) for m in cache]);fit=stats.linregress(nlines,means)
fig,ax=plt.subplots(figsize=(8,4.5));ax.errorbar(nlines,means,yerr=sds,fmt='o',capsize=4,label='Run-mean ± between-run SD');xx=np.linspace(0,16,100);ax.plot(xx,fit.intercept+fit.slope*xx,'--',label=f'Exploratory linear fit; slope {fit.slope:.3f} µs/line; R² {fit.rvalue**2:.4f}')
ax.set(xlabel='Targeted cold cache lines (not counted misses)',ylabel='Flash-work duration (µs)',title='Cache-access pattern scaling');ax.legend();fig.tight_layout();fig.savefig(plots/'cache_scaling.png');plt.close(fig)
fig,ax=plt.subplots(figsize=(8,4.5));arr=[vals(group[x],'flash_work_us') for x in cache];ax.boxplot(arr,tick_labels=['Warm','2 lines','8 lines','16 lines'],showfliers=False);ax.set(ylabel='Flash-work duration (µs)',title='Cache workload distributions (outliers hidden visually)');fig.tight_layout();fig.savefig(plots/'cache_boxplot.png');plt.close(fig)
# DMA
bytrans=collections.defaultdict(list)
for r in trans:bytrans[r['test']].append(r)
dma=sorted(bytrans['dma'],key=lambda x:int(x['repeat']));dma_summary=[]
for metric in ['wall_us','queue_cpu_us','isr_cpu_us','blocked_wait_us','mismatched_bytes']:
 a=vals(dma,metric);dma_summary.append(dict(segment='all_20',metric=metric,**desc(a)));dma_summary.append(dict(segment='steady_trials_2_20',metric=metric,**desc(a[1:])))
writecsv('dma_trial_statistics.csv',dma_summary)
fig,ax=plt.subplots(figsize=(8,4.5))
ax.plot(range(1,21),vals(dma,'queue_cpu_us'),marker='o',label='Queue-submission interval');ax.set(xlabel='Trial number',ylabel='Queue-submission interval (µs)',title='SPI DMA first-transaction effect — original failed-loopback series');ax.legend();fig.tight_layout();fig.savefig(plots/'dma_first_run.png');plt.close(fig)
transfer_stats=[]
for mode,rr in sorted(bytrans.items()):
 for metric in ['wall_us','poll_work_us','isr_work_us','queue_cpu_us','isr_cpu_us','interrupt_count','spill_resident_cycles','spill_forced_cycles','spill_deep_cycles']:
  d=desc(vals(rr,metric))
  if d['n']:transfer_stats.append(dict(mode=mode,metric=metric,**d))
writecsv('transfer_statistics.csv',transfer_stats)
# check repeated identical series and exact sample duplicate
ident=[]
for mode,rr in bytrans.items():
 for metric in ['wall_us','isr_work_us','spill_resident_cycles','spill_forced_cycles','spill_deep_cycles']:
  a=vals(rr,metric);a=a[np.isfinite(a)]
  if len(a):ident.append(dict(mode=mode,metric=metric,n=len(a),unique=len(np.unique(a)),all_identical=len(np.unique(a))==1))
writecsv('measurement_resolution_audit.csv',ident)
# summary JSON
res={'rows':len(samples),'conditions':{m:len(rr) for m,rr in group.items()},'runs':{m:len(bytest[m]) for m in bytest},'threshold':threshold,'lag1':{m:desc([r['lag1_corr'] for r in lags if r['mode']==m]) for m in ['stress1','stress5']},'cache_regression':{'intercept_us':fit.intercept,'slope_us_per_target_line':fit.slope,'R2':fit.rvalue**2,'p_value_not_credible_with_4_design_points':fit.pvalue},'dma':dma_summary,'transfer_stats':transfer_stats,'trial_status':{str(k):v for k,v in collections.Counter((r['test'],r['status']) for r in trial).items()}}
(out/'summary.json').write_text(json.dumps(res,indent=2))
for metric in ['period_us','abs_jitter_us','dispatch_latency_us','flash_work_us']:
 print('\n',metric)
 for mode in ['stress1','stress5','cache_warm','cache12','cache50','cache100']:
  d=desc(vals(group[mode],metric));print(mode,d['n'],*[round(d[k],3) for k in ['mean','sd','p95','p99','max']])
print('\nTHRESHOLD',threshold,'\nCORR',[r for r in lags if r['mode'] in ('stress1','stress5')][:4]);print('CACHE REG',fit)
print('DMA',[(x['segment'],x['metric'],x.get('mean'),x.get('sd')) for x in dma_summary]);print('transferstats',transfer_stats)
