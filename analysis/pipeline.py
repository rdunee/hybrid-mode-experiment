"""Run-level analysis; never bootstrap packets as experimental replicates."""
import argparse,itertools,json
from pathlib import Path
import numpy as np,pandas as pd
from scipy.stats import norm
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def pareto(values):
    a=np.asarray(values,float)
    return np.array([not any(np.all(b<=v) and np.any(b<v) for j,b in enumerate(a) if j!=i) for i,v in enumerate(a)])
def bootstrap(x,seed=1,n=5000):
    x=np.asarray(x,float);x=x[np.isfinite(x)]
    if len(x)<2:return (np.nan,np.nan)
    rng=np.random.default_rng(seed);return tuple(np.quantile(np.mean(rng.choice(x,(n,len(x))),axis=1),[.025,.975]))
def paired_test(d):
    d=np.asarray(d,float)
    if len(d)<=16:
        dist=np.array([abs(np.mean(d*np.array(s))) for s in itertools.product([-1,1],repeat=len(d))]);return np.mean(dist>=abs(d.mean())-1e-12)
    rng=np.random.default_rng(19);dist=abs((rng.choice([-1,1],(20000,len(d)))*d).mean(axis=1));return (1+(dist>=abs(d.mean())).sum())/20001

def summarize(folder,deadline):
    m=json.loads((folder/'metadata.json').read_text())
    if not m['valid']:return None,None
    tx=pd.read_csv(folder/'tx.csv');rx=pd.read_csv(folder/'rx.csv');wire=pd.read_csv(folder/'wire.csv');tx=tx[tx.phase=='measure'];first=rx.sort_values('rx_ns').drop_duplicates('seq');d=tx.merge(first,on='seq',how='left',suffixes=('_source',''));d['latency_ms']=(d.rx_ns-d.tx_ns_source)/1e6;d['lost']=d.rx_ns.isna();d['miss']=d.lost|(d.latency_ms>deadline)
    useful=d.loc[~d['miss'],'payload_bytes_source'].sum();all_useful=d.loc[~d['lost'],'payload_bytes_source'].sum();duration=m['config']['measurement_s'];ids=set(tx.seq)
    # Parity assigned to block base; warmup boundary must align with k to isolate measurement wire bytes.
    w=wire[wire.seq.isin(ids)];network=w.bytes.sum();overhead=network/useful-1 if useful else np.nan
    result={k:m[k] for k in ('id','block','rep','loss_pct','mode')};result['delta_rtt_ms']=m['config']['paths'][1]['rtt_ms']-m['config']['paths'][0]['rtt_ms'];result['state']=m.get('state',f"L{m['loss_pct']:g}")
    result.update(dict(p50_ms=d.latency_ms.quantile(.5),p95_ms=d.latency_ms.quantile(.95),p99_ms=d.latency_ms.quantile(.99),loss=d.lost.mean(),deadline_miss=d['miss'].mean(),goodput_mbps=useful*8/duration/1e6,delivered_mbps=all_useful*8/duration/1e6,overhead=overhead,wire_bytes=network,useful_bytes=useful,reordering=rx.loc[rx.seq.isin(ids),'reordered'].mean(),fec_recovered=rx.loc[rx.seq.isin(ids),'fec_recovered'].sum(),fec_recovery_fraction=rx.loc[rx.seq.isin(ids),'fec_recovered'].sum()/len(tx),duplicate_count=rx.loc[rx.seq.isin(ids),'duplicate'].sum(),max_delivery_gap_ms=first[first.seq.isin(ids)].rx_ns.sort_values().diff().max()/1e6))
    consecutive=[];count=0
    for lost in d.sort_values('seq').lost:
        if lost:count+=1
        elif count:consecutive.append(count);count=0
    if count:consecutive.append(count)
    losses=d.sort_values('seq').lost.to_numpy();result['max_loss_burst']=max(consecutive,default=0);result['p_loss_after_loss']=np.mean(losses[1:][losses[:-1]]) if losses[:-1].sum() else np.nan
    d['mode']=m['mode'];d['state']=result['state'];d['run']=m['id'];return result,d

def main():
    p=argparse.ArgumentParser();p.add_argument('--raw',required=True);p.add_argument('--output',required=True);p.add_argument('--deadline-ms',type=float,default=100);p.add_argument('--weights',help='JSON: metric -> {weight,scale}; no implicit objective');a=p.parse_args();raw=Path(a.raw);out=Path(a.output);out.mkdir(parents=True,exist_ok=True);results=[];packets=[];invalid=[]
    (out/'analysis_config.json').write_text(json.dumps({'deadline_ms':a.deadline_ms,'weights':json.loads(Path(a.weights).read_text()) if a.weights else None,'bootstrap_samples':5000,'bootstrap_seed':1,'unit':'run','multiplicity':'Holm over all generated comparisons'},indent=2))
    for f in sorted(raw.glob('*/metadata.json')):
        try:
            m=json.loads(f.read_text())
            if not m['valid']:invalid.append({'id':m['id'],'reasons':m['failures']});continue
            r,d=summarize(f.parent,a.deadline_ms);results.append(r);packets.append(d)
        except Exception as e:invalid.append({'id':f.parent.name,'reasons':[str(e)]})
    matrix_path=raw/'matrix.csv'
    if matrix_path.exists():
        expected=pd.read_csv(matrix_path);present={f.parent.name for f in raw.glob('*/metadata.json')}
        invalid.extend({'id':name,'reasons':['missing metadata or scheduled run not executed']} for name in expected.id if name not in present)
    (out/'invalid.json').write_text(json.dumps(invalid,indent=2))
    if not results:raise SystemExit('No valid runs; no results or winner plots generated.')
    df=pd.DataFrame(results);df.to_csv(out/'runs.csv',index=False);metrics=['p50_ms','p95_ms','p99_ms','loss','deadline_miss','goodput_mbps','overhead'];summary=[];tests=[]
    for (state,mode),g in df.groupby(['state','mode']):
        for metric in metrics:
            lo,hi=bootstrap(g[metric]);summary.append(dict(state=state,mode=mode,metric=metric,n=len(g),mean=g[metric].mean(),ci_low=lo,ci_high=hi))
    s=pd.DataFrame(summary);s.to_csv(out/'summary.csv',index=False)
    for state,g in df.groupby('state'):
        for metric in metrics:
            pivot=g.pivot(index='block',columns='mode',values=metric)
            for x,y in itertools.combinations(pivot.columns,2):
                d=(pivot[x]-pivot[y]).dropna().to_numpy()
                if len(d)<2:continue
                lo,hi=bootstrap(d);tests.append(dict(state=state,metric=metric,a=x,b=y,n=len(d),effect=d.mean(),ci_low=lo,ci_high=hi,p=paired_test(d)))
    if tests:
        t=pd.DataFrame(tests);ix=t.p.argsort().to_numpy();adjusted=np.maximum.accumulate(np.minimum(1,t.p.iloc[ix].to_numpy()*np.arange(len(t),0,-1)));t['holm_p']=np.nan;t.loc[t.index[ix],'holm_p']=adjusted;t.to_csv(out/'paired_comparisons.csv',index=False)
    means=df.groupby(['state','mode'])[metrics+['loss_pct','delta_rtt_ms']].mean().reset_index();means['pareto_point_estimate']=False;means['confidence_dominated']=False
    dims=['p95_ms','deadline_miss','overhead']
    for state,g in means.groupby('state'):
        finite=np.isfinite(g[dims]).all(axis=1);means.loc[g.index[finite],'pareto_point_estimate']=pareto(g.loc[finite,dims])
        # Conservative marginal-CI criterion; exploratory, no family-wise confidence guarantee.
        for idx,b in g.iterrows():
            for _,candidate in g.iterrows():
                if candidate['mode']==b['mode']:continue
                better=[]
                for metric in dims:
                    ci_a=s[(s.state==state)&(s['mode']==candidate['mode'])&(s.metric==metric)].iloc[0]
                    ci_b=s[(s.state==state)&(s['mode']==b['mode'])&(s.metric==metric)].iloc[0]
                    better.append(ci_a.ci_high<ci_b.ci_low)
                if all(better):means.loc[idx,'confidence_dominated']=True
    means.to_csv(out/'pareto.csv',index=False)
    plt.rcParams.update({'font.size':8,'figure.figsize':(3.35,2.5),'pdf.fonttype':42,'ps.fonttype':42})
    styles=['o-','s--','^:','D-.','v-']
    for metric in metrics+['reordering','fec_recovery_fraction','max_delivery_gap_ms']:
        fig,ax=plt.subplots()
        for (mode,g),style in zip(df.groupby('mode'),styles):
            gg=g.groupby('loss_pct')[metric];mu=gg.mean();ax.plot(mu.index,mu.values,style,label=mode)
        ax.set(xlabel='Configured forward loss on A (%)',ylabel=metric);ax.legend(fontsize=6);fig.tight_layout();fig.savefig(out/f'{metric}.pdf');plt.close(fig)
    pd.concat(packets).to_csv(out/'packet_metrics.csv',index=False)
    for state in means.state.unique():
        fig,ax=plt.subplots()
        for (mode,g),style in zip(pd.concat(packets).query('state == @state').groupby('mode'),styles):
            v=np.sort(g.latency_ms.dropna());ax.plot(v,np.arange(1,len(v)+1)/len(v),style[1:],label=mode)
        ax.set(xlabel='Delivered latency (ms)',ylabel='Delivered-packet CDF');ax.legend(fontsize=6);fig.tight_layout();fig.savefig(out/f'cdf-{state}.pdf');plt.close(fig)
        fig,ax=plt.subplots();g=means[means.state==state]
        for (_,r),style in zip(g.iterrows(),styles):ax.plot(r.overhead,r.deadline_miss,style[0],label=r['mode'])
        ax.set(xlabel='IPv4 bytes / deadline-useful bytes - 1',ylabel='Deadline miss fraction');ax.legend(fontsize=6);fig.tight_layout();fig.savefig(out/f'pareto-{state}.pdf');plt.close(fig)
    first_arrivals=[]
    for folder in raw.glob('*/metadata.json'):
        m=json.loads(folder.read_text())
        if m['valid'] and m['mode']=='replication':
            rx=pd.read_csv(folder.parent/'rx.csv');rx=rx.sort_values('rx_ns').drop_duplicates('seq');first_arrivals.extend(rx.path.tolist())
    if first_arrivals:
        fig,ax=plt.subplots();counts=pd.Series(first_arrivals).value_counts(normalize=True).reindex([0,1],fill_value=0);ax.bar(['A','B'],counts,hatch='//',color='white',edgecolor='black');ax.set_ylabel('First-arrival fraction (includes warmup)');fig.tight_layout();fig.savefig(out/'replication_first_arrival.pdf');plt.close(fig)
    if a.weights:
        spec=json.loads(Path(a.weights).read_text());df['objective']=0.;means['objective']=0.
        for metric,item in spec.items():
            if metric not in dims+['p99_ms','loss']:raise ValueError('Only lower-is-better objective metrics supported')
            if item['scale']<=0 or item['weight']<0:raise ValueError('invalid objective scaling')
            for table in (df,means):table['objective']+=item['weight']*table[metric]/item['scale']
        # Cross-validated held-out blocks: removes the most direct winner-selection bias.
        oracle=[]
        for state,g in df.groupby('state'):
            for block in g.block.unique():
                rep=g[g.block==block].rep.iloc[0];train=g[g.rep!=rep].groupby('mode').objective.mean();test=g[g.block==block].set_index('mode')
                static_train=df[df.rep!=rep].groupby('mode').objective.mean();static_mode=static_train.idxmin()
                if len(train)==0:continue
                chosen=train.idxmin();oracle.append(dict(state=state,block=block,rep=rep,selected=chosen,static_mode=static_mode,static_objective=test.loc[static_mode,'objective'],heldout_static_minus_selected=test.loc[static_mode,'objective']-test.loc[chosen,'objective'],heldout_objective=test.loc[chosen,'objective'],hindsight_min=test.objective.min(),optimistic_hindsight_gap=test.loc[chosen,'objective']-test.objective.min()))
        oracle_df=pd.DataFrame(oracle);oracle_df.to_csv(out/'oracle_cross_validation.csv',index=False)
        gains=oracle_df.groupby('rep').heldout_static_minus_selected.mean();lo,hi=bootstrap(gains)
        (out/'oracle_gain_exploratory.json').write_text(json.dumps({'mean_static_minus_state':gains.mean(),'ci_low':lo,'ci_high':hi,'note':'Exploratory CV folds share training data; confirm in new held-out experiments.'},indent=2))
        winners=means.loc[means.groupby('state').objective.idxmin()];winners.to_csv(out/'objective_winners.csv',index=False)
        fig,ax=plt.subplots();labels=sorted(means['mode'].unique());grid=winners.assign(code=lambda x:x['mode'].map({v:i for i,v in enumerate(labels)})).pivot_table(index='loss_pct',columns='delta_rtt_ms',values='code',aggfunc='first');ax.imshow(grid,aspect='auto',cmap='Greys',vmin=0,vmax=max(1,len(labels)-1));ax.set_xticks(range(len(grid.columns)),grid.columns);ax.set_yticks(range(len(grid.index)),grid.index);ax.set(xlabel='RTT B - A (ms)',ylabel='Loss A (%)')
        for i in range(len(grid.index)):
            for j in range(len(grid.columns)):
                if pd.notna(grid.iloc[i,j]):ax.text(j,i,labels[int(grid.iloc[i,j])],ha='center',va='center',fontsize=6,bbox={'facecolor':'white','alpha':.8,'edgecolor':'none'})
        fig.tight_layout();fig.savefig(out/'preferred_mode_heatmap.pdf');plt.close(fig)
        for field in ('loss_pct','delta_rtt_ms'):
            winners[['state',field,'mode','objective']].to_csv(out/f'preferred_mode_vs_{field}.csv',index=False)
    print(f'{len(df)} valid runs; {len(invalid)} excluded. Outputs: {out}')
if __name__=='__main__':main()
