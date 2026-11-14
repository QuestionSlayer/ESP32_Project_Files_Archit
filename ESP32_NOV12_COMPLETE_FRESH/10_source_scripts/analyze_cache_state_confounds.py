from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import wasserstein_distance, ks_2samp
import matplotlib.pyplot as plt
base=Path('/mnt/data/zeroplus_analysis')
d=pd.read_csv(base/'all_high_pulses.csv'); d=d[d.channel=='A1']
refs={'Warm':'03_Cache/Warm_01','12.5%':'03_Cache/cache125_01','50%':'03_Cache/cache50_01','100%':'03_Cache/coldlinemax_01'}
rows=[]
for name,g in d.groupby('capture'):
 if not (name.startswith(('02_Stress/','03_Cache/')) or name in ('Reg_overflow_01','regoverflow_02')):continue
 a=g.width_us.to_numpy();row={'capture':name,'n':len(a),'mean_us':a.mean(),'median_us':np.median(a),'sd_us':np.std(a,ddof=1),'p10_us':np.quantile(a,.1),'p90_us':np.quantile(a,.9),'fraction_gt10us':(a>10).mean(),'fraction_gt25us':(a>25).mean()}
 for key,rn in refs.items():
  b=d[d.capture==rn].width_us.to_numpy()
  row['wasserstein_to_'+key.replace('%','pct')+'_us']=wasserstein_distance(a,b)
  row['KS_to_'+key.replace('%','pct')]=ks_2samp(a,b).statistic
 scores={key:row['wasserstein_to_'+key.replace('%','pct')+'_us'] for key in refs}
 row['nearest_cache_signature']=min(scores,key=scores.get)
 row['signature_distance_us']=min(scores.values())
 rows.append(row)
out=pd.DataFrame(rows).sort_values('capture');out.to_csv('/mnt/data/cache_state_confound_audit.csv',index=False)
select=out[out.capture.str.contains('Stress|Baseline|overflow',case=False)].copy()
fig,ax=plt.subplots(figsize=(11,5.5))
all_names=list(select.capture)
for i,name in enumerate(all_names):
 a=d[d.capture==name].width_us.to_numpy()
 ax.boxplot([a],positions=[i],vert=False,showfliers=False,widths=.65)
ax.set_yticks(range(len(all_names)),[n.replace('02_Stress/','').replace('_01',' #1').replace('_02',' #2') for n in all_names]);ax.set_xlabel('GPIO22 HIGH pulse width (µs)'); ax.set_title('Stress capture A1 widths — cache-state fingerprint (whiskers exclude outliers)');ax.grid(axis='x',alpha=.25);fig.tight_layout();fig.savefig('/mnt/data/cache_state_confound_comparison.png',dpi=170);plt.close(fig)
print(out[['capture','n','mean_us','median_us','sd_us','fraction_gt10us','fraction_gt25us','nearest_cache_signature','signature_distance_us']].to_string(index=False))
