import zipfile, numpy as np, pandas as pd, matplotlib.pyplot as plt
from pathlib import Path
z=zipfile.ZipFile('/mnt/data/esp32_preflight_results.zip')
d=pd.read_csv(z.open(next(x for x in z.namelist() if x.endswith('all_timer_samples.csv'))))
out=Path('/mnt/data/preflight_deep_audit');out.mkdir(exist_ok=True)
summary=[]
for mode,g in d.groupby('test'):
    q=g.dropna(subset=['period_us'])
    summary.append(dict(mode=mode,events=len(g),runs=g.repeat.nunique(),period_mean=g.period_us.mean(),period_sd=g.period_us.std(),abs_jitter_mean=g.abs_jitter_us.mean(),jitter_over_5_pct=100*np.mean(q.abs_jitter_us>5),jitter_over_10_pct=100*np.mean(q.abs_jitter_us>10),latency_mean=g.dispatch_latency_us.mean(),latency_sd=g.dispatch_latency_us.std(),latency_p95=g.dispatch_latency_us.quantile(.95),latency_p99=g.dispatch_latency_us.quantile(.99),latency_over_50_pct=100*np.mean(g.dispatch_latency_us>50),work_mean=g.flash_work_us.mean(),work_sd=g.flash_work_us.std()))
s=pd.DataFrame(summary);s.to_csv(out/'by_condition_summary.csv',index=False)
# median per run, consistency, periodic signatures
rows=[]
for (mode,run),g in d.groupby(['test','repeat']):
    g=g.sort_values('sample_index'); j=g.signed_jitter_us.dropna().to_numpy();l=g.dispatch_latency_us.to_numpy();w=g.flash_work_us.to_numpy();
    def ac(arr,k):return float(np.corrcoef(arr[k:],arr[:-k])[0,1]) if len(arr)>k and arr.std()>1e-9 else np.nan
    rows.append(dict(mode=mode,run=int(run),n=len(g),period_sd=g.period_us.std(),jitter_lag1=ac(j,1),jitter_lag20=ac(j,20),latency_lag20=ac(l,20),work_lag1=ac(w,1),work_lag20=ac(w,20),latency_mean=l.mean(),work_mean=w.mean(),period_gt5_pct=100*np.nanmean(g.abs_jitter_us>5)))
a=pd.DataFrame(rows);a.to_csv(out/'per_run_patterns.csv',index=False)
# correlations of current and following event jitter with work
cross=[]
for mode,g in d.groupby('test'):
    co=[]
    for run,x in g.groupby('repeat'):
        x=x.sort_values('sample_index');y=x.signed_jitter_us.to_numpy();w=x.flash_work_us.to_numpy()
        # work[i] measured after isr[i]; compare next isr interval period[i+1]
        good=np.isfinite(y[1:]);
        if good.sum()>100: co.append(np.corrcoef(w[:-1][good],y[1:][good])[0,1])
    cross.append(dict(mode=mode,work_vs_next_signed_jitter_corr_mean=np.nanmean(co),range_min=np.nanmin(co),range_max=np.nanmax(co)))
pd.DataFrame(cross).to_csv(out/'work_next_period_correlations.csv',index=False)
# graphics
fig,ax=plt.subplots(figsize=(10,5)); t=s.sort_values('abs_jitter_mean');ax.bar(t['mode'],t['abs_jitter_mean']);ax.set_ylabel('Mean |period - 50 µs| (µs)');ax.set_title('More timer ISR-entry jitter in cold-cache modes than high-priority stress');ax.tick_params(axis='x',rotation=30);fig.tight_layout();fig.savefig(out/'jitter_by_condition.png',dpi=180);plt.close(fig)
fig,ax=plt.subplots(figsize=(9,5));
for mode in ['stress1','stress5','cache50','cache100']:
    q=d.loc[d.test==mode,'dispatch_latency_us'].dropna().to_numpy();q.sort();ax.step(q,np.arange(1,len(q)+1)/len(q),label=mode)
ax.set_xlim(0,180);ax.set_xlabel('ISR entry to dispatcher start (µs)');ax.set_ylabel('Empirical CDF');ax.set_title('Latency distributions are not ranked by flash-work duration');ax.legend();fig.tight_layout();fig.savefig(out/'latency_ecdf_extended.png',dpi=180);plt.close(fig)
fig,ax=plt.subplots(figsize=(10,5));
for mode in ['cache_warm','cache12','cache50','cache100']:
 q=d[d.test==mode].flash_work_us.dropna();ax.hist(q,bins=np.linspace(0,42,141),histtype='step',density=True,label=mode,linewidth=1.3)
ax.set_xlim(0,42);ax.set_xlabel('Flash-work duration (µs)');ax.set_ylabel('Normalized density');ax.set_title('Multimodal timing, especially cold-target access');ax.legend();fig.tight_layout();fig.savefig(out/'cache_work_multimodal.png',dpi=180);plt.close(fig)
# warmup plot from existing transfer CSV
with z.open(next(x for x in z.namelist() if x.endswith('transfer_trials.csv'))) as f:trans=pd.read_csv(f)
print('transfer columns',trans.columns.tolist()); print(trans.head(3).to_string(index=False))
print(s.round(3).to_string(index=False));print('\nlag20\n',a.groupby('mode')[['jitter_lag20','latency_lag20','work_lag1','work_lag20']].mean().round(3).to_string());print('\nwork vs next period\n',pd.DataFrame(cross).round(3).to_string(index=False))
