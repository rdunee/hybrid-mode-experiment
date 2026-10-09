import argparse,csv,hashlib,json,os,platform,random,signal,subprocess,sys,time
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));from orchestrator import netem

def matrix(cfg):
    rng=random.Random(cfg['seed']);rows=[]
    states=cfg.get('states') or [dict(name=f'L{l:g}',paths=[dict(cfg['paths'][0],loss_pct=l),cfg['paths'][1]]) for l in cfg['loss_pct']]
    blocks=[(r,i,state) for r in range(cfg['repetitions']) for i,state in enumerate(states)];rng.shuffle(blocks)
    for block,(rep,state_index,state) in enumerate(blocks):
        loss=state['paths'][0]['loss_pct']
        modes=list(cfg['modes']);rng.shuffle(modes)
        for order,mode in enumerate(modes):
            rows.append(dict(id=f"EXP-RTC-{state['name']}-{mode.upper()}-R{rep:02d}",block=block,order=order,rep=rep,loss_pct=loss,mode=mode,seed=cfg['seed']+rep*1000+state_index*10,experiment=len(rows)+1,state=state['name'],paths=state['paths'],events=state.get('events',cfg.get('events',[])),cross_traffic=state.get('cross_traffic')))
    return rows

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',default=str(ROOT/'configs/stage1/pilot.yaml'));p.add_argument('--matrix-only',action='store_true');p.add_argument('--limit',type=int);p.add_argument('--output',default=str(ROOT/'data/raw'));a=p.parse_args();cfg=yaml.safe_load(Path(a.config).read_text());rows=matrix(cfg);dest=Path(a.output).resolve();dest.mkdir(parents=True,exist_ok=True)
    with open(dest/'matrix.csv','w',newline='') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    if a.matrix_only:print(f'{len(rows)} runs -> {dest}/matrix.csv');return
    if os.geteuid()!=0:raise SystemExit('Run under sudo with the venv Python absolute path')
    signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    script=ROOT/'dataplane/engine.py'
    def proc(ns,args,log):return subprocess.Popen(['ip','netns','exec',ns,sys.executable,str(script),*map(str,args)],stdout=log,stderr=log)
    for row in rows[:a.limit]:
        out=dest/row['id']
        if out.exists():raise SystemExit(f'Refusing to overwrite {out}; choose a fresh output directory')
        out.mkdir();metadata=dict(row,config=cfg,kernel=platform.release(),python=sys.version,start_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),valid=False,failures=[]);children=[];netem.COMMANDS.clear()
        metadata['event_times']=[]
        metadata['tools']={name:subprocess.check_output(argv,text=True,stderr=subprocess.STDOUT).strip() for name,argv in [('ip',['ip','-V']),('tc',['tc','-V']),('ethtool',['ethtool','--version'])]}
        metadata['source_sha256']={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in ROOT.rglob('*.py') if '.venv' not in f.parts}
        try:metadata['git_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
        except subprocess.CalledProcessError:metadata['git_commit']=None
        try:
            subprocess.run([str(ROOT/'topology/namespaces.sh')],check=True,capture_output=True)
            paths=row['paths'];metadata['config']=dict(cfg,paths=paths)
            if int(cfg['warmup_s']*1000/cfg['interval_ms'])%cfg['fec_k']:raise ValueError('Warmup boundary must align with FEC block size')
            for i,path in enumerate(paths,1):netem.configure(i,path,row['seed'])
            (out/'initial_state.json').write_text(json.dumps(netem.state(),indent=2));time.sleep(cfg['stabilization_s'])
            duration=cfg['warmup_s']+cfg['measurement_s'];log=open(out/'process.log','w')
            if row['cross_traffic']:
                ct=row['cross_traffic'];path=ct['path']
                server=subprocess.Popen(['ip','netns','exec','hme-gateway','iperf3','-s','-1','-p','5201'],stdout=log,stderr=log);children.append(server);time.sleep(.5)
                load=subprocess.Popen(['ip','netns','exec','hme-edge','iperf3','-c',f'10.201.{path}.2','-p','5201','-u','-b',f"{ct['mbps']}M",'-t',str(int(duration+10)),'-J'],stdout=open(out/'cross_traffic.json','w'),stderr=log);children.append(load)
            rx=proc('hme-gateway',['recv','--out',out,'--experiment',row['experiment'],'--duration',duration+cfg['drain_s']+2,'--flows',cfg['flows']],log);children.append(rx)
            for _ in range(100):
                if (out/'ready').exists():break
                if rx.poll() is not None:raise RuntimeError('receiver failed before readiness')
                time.sleep(.02)
            else:raise RuntimeError('receiver readiness timeout')
            echo=proc('hme-gateway',['echo','--out',out,'--ports','9101,9102','--duration',duration+cfg['drain_s']+3],log);children.append(echo)
            probe=proc('hme-edge',['probe','--out',out/'path.csv','--targets','10.201.1.2:9101,10.201.2.2:9102','--duration',duration],log);children.append(probe)
            tx=proc('hme-edge',['send','--out',out,'--mode',row['mode'],'--experiment',row['experiment'],'--duration',cfg['measurement_s'],'--warmup',cfg['warmup_s'],'--interval',cfg['interval_ms'],'--size',cfg['payload_bytes'],'--flows',cfg['flows'],'--single',cfg.get('single_path',0),'--k',cfg['fec_k']],log);children.append(tx)
            begin=time.monotonic();events=sorted(row['events'],key=lambda x:x['at_s']);host=[]
            import psutil
            psutil.cpu_percent(None)
            while tx.poll() is None:
                elapsed=time.monotonic()-begin
                if row['cross_traffic'] and load.poll() is not None:raise RuntimeError('competing load exited before foreground workload')
                if elapsed>duration+10:raise RuntimeError('sender timeout')
                while events and elapsed>=events[0]['at_s']:
                    event=events.pop(0);netem.link(event['path'],event['up']);metadata['event_times'].append(dict(event,actual_elapsed_s=time.monotonic()-begin))
                host.append(dict(elapsed_s=elapsed,cpu_pct=psutil.cpu_percent(None),memory_pct=psutil.virtual_memory().percent,processes=[{'pid':c.pid,'cpu_s':sum(psutil.Process(c.pid).cpu_times()[:2]),'rss':psutil.Process(c.pid).memory_info().rss} for c in children if c.poll() is None],state=netem.state()));time.sleep(1)
            if tx.returncode:raise RuntimeError('sender nonzero exit')
            for c in (rx,probe,echo):
                if c.wait(timeout=cfg['drain_s']+10):raise RuntimeError('collector nonzero exit')
            (out/'host.json').write_text(json.dumps(host));(out/'final_state.json').write_text(json.dumps(netem.state(),indent=2))
            import pandas as pd
            sent=pd.read_csv(out/'tx.csv');received=pd.read_csv(out/'rx.csv');probes=pd.read_csv(out/'path.csv')
            expected=int(duration*1000/cfg['interval_ms'])
            if len(sent)!=expected:metadata['failures'].append('incorrect packet count')
            if sent.schedule_lag_ms.quantile(.99)>cfg['max_p99_schedule_lag_ms']:metadata['failures'].append('sender schedule lag')
            if any(h['cpu_pct']>cfg['max_host_cpu_pct'] for h in host):metadata['failures'].append('host CPU threshold exceeded')
            if any(c['cpu_s']/max(h['elapsed_s'],1)>cfg['max_process_core_fraction'] for h in host if h['elapsed_s']>5 for c in h['processes']):metadata['failures'].append('process CPU threshold exceeded')
            if (received.rx_ns<received.tx_ns).any():metadata['failures'].append('negative monotonic delay')
            for path in (0,1):
                pp=probes[probes.path==path]
                if pp.empty or (pp.lost.mean()>cfg['max_probe_loss'] and not any(e['path']==path+1 for e in row['events'])):metadata['failures'].append(f'path {path} probe incomplete or unexpectedly down')
            if abs(json.loads((out/'sender.json').read_text())['duration_s']-duration)>2:metadata['failures'].append('duration mismatch')
            metadata['valid']=not metadata['failures'];log.close()
        except Exception as e:
            metadata['failures'].append(str(e))
            if isinstance(e,subprocess.CalledProcessError):metadata['command_error']={'stdout':e.stdout,'stderr':e.stderr}
        finally:
            for c in children:
                if c.poll() is None:c.terminate()
            for c in children:
                try:c.wait(timeout=3)
                except subprocess.TimeoutExpired:c.kill();c.wait()
            metadata['end_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());metadata['commands']=netem.COMMANDS;(out/'metadata.json').write_text(json.dumps(metadata,indent=2));subprocess.run([str(ROOT/'topology/cleanup.sh')],check=True)
        print(row['id'], 'VALID' if metadata['valid'] else metadata['failures'],flush=True)
        time.sleep(cfg['cooldown_s'])
if __name__=='__main__':main()
