import subprocess,json
COMMANDS=[]
def run(args):
    COMMANDS.append(args);return subprocess.run(args,check=True,text=True,capture_output=True).stdout

def configure(path,cfg,seed):
    # Limit on both ends makes requested RTT twice the one-way delay.
    for ns,prefix in [('hme-edge','e'),('hme-gateway','g')]:
        dev=f'hme-{prefix}{path}';cmd=['ip','netns','exec',ns,'tc','qdisc','replace','dev',dev,'root','handle','10:','netem','limit',str(cfg.get('queue_packets',1000)),'delay',f"{cfg['rtt_ms']/2}ms"]
        if cfg.get('jitter_ms',0):cmd += [f"{cfg['jitter_ms']}ms",'distribution','normal']
        # Forward loss only: requested percentage describes application forward packets, not RTT round-trip loss.
        if ns=='hme-edge':
            if cfg.get('burst'):
                mean=cfg['burst']['mean_length'];loss=cfg['loss_pct']/100;r=1/mean;p=loss*r/(1-loss)
                cmd += ['loss','gemodel',f'{100*p}%',f'{100*r}%','100%','0%']
            elif cfg.get('loss_pct',0):cmd += ['loss','random',f"{cfg['loss_pct']}%",f"{cfg.get('correlation_pct',0)}%"]
            for opt in ('reorder','duplicate'):
                if cfg.get(opt+'_pct',0):cmd += [opt,f"{cfg[opt+'_pct']}%"]
        cmd += ['rate',f"{cfg['mbps']}mbit",'seed',str((seed+path+(0 if ns=='hme-edge' else 100))%4294967295)]
        run(cmd)
        q=json.loads(run(['ip','netns','exec',ns,'tc','-j','qdisc','show','dev',dev]))
        if not any(x['kind']=='netem' for x in q):raise RuntimeError('netem absent')
def state():
    return {ns:{'interfaces':json.loads(run(['ip','-n',ns,'-j','-s','link'])), 'qdisc':json.loads(run(['ip','netns','exec',ns,'tc','-j','-s','qdisc','show']))} for ns in ('hme-edge','hme-gateway')}
def link(path,up):
    run(['ip','-n','hme-edge','link','set',f'hme-e{path}','up' if up else 'down'])
