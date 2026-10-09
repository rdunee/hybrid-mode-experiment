"""Low-rate, same-host RTC reference data plane. No congestion-control claims."""
import argparse,csv,json,selectors,socket,struct,time,sys,errno
from pathlib import Path
H=struct.Struct('!4sQIIQBBBB') # magic, experiment, flow, seq, tx_ns, mode,path,k,symbol
T=struct.Struct('!Q')
MODES={'single':0,'steering':1,'striping':2,'replication':3,'fec':4}
def xor(symbols):
    out=bytearray(len(symbols[0]))
    for s in symbols:
        if len(s)!=len(out): raise ValueError('unequal FEC symbols')
        for i,b in enumerate(s): out[i]^=b
    return bytes(out)
def schedule(mode,seq,flow,weights,single):
    if mode in ('single','fec'): return [single]
    if mode=='replication': return [0,1]
    n=flow if mode=='steering' else seq
    return [0 if n%sum(weights)<weights[0] else 1]
def writer(path,fields):
    f=open(path,'w',newline=''); w=csv.DictWriter(f,fieldnames=fields);w.writeheader();return f,w

def sender(a):
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    con=[]
    for target in a.targets.split(','):
        host,port=target.rsplit(':',1);s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect((host,int(port)));con.append(s)
    f,w=writer(out/'tx.csv',['seq','flow','tx_ns','phase','payload_bytes','schedule_lag_ms'])
    fw,ww=writer(out/'wire.csv',['seq','path','symbol','tx_ns','bytes'])
    fe,we=writer(out/'send_errors.csv',['seq','path','errno','timestamp_ns'])
    fc,wc=writer(out/'coding.csv',['block_base','encode_ns','parity_tx_ns'])
    start=time.monotonic_ns();total=int((a.warmup+a.duration)*1000/a.interval);block=[];weights=list(map(int,a.weights.split(',')))
    if len(weights)!=2 or min(weights)<=0 or a.k not in range(2,255) or a.size>1300 or a.size<1: raise ValueError('invalid data-plane parameters')
    def send(seq,flow,tx,body,symbol,paths):
        for path in paths:
            packet=H.pack(b'HME1',a.experiment,flow,seq,tx,MODES[a.mode],path,a.k,symbol)+body
            try:
                if con[path].send(packet)!=len(packet): raise RuntimeError('short UDP send')
            except OSError as e:
                if e.errno not in (errno.ENETDOWN,errno.ENETUNREACH,errno.EHOSTUNREACH,errno.ENOBUFS,errno.ECONNREFUSED):raise
                we.writerow(dict(seq=seq,path=path,errno=e.errno,timestamp_ns=time.monotonic_ns()));continue
            ww.writerow(dict(seq=seq,path=path,symbol=symbol,tx_ns=tx,bytes=len(packet)+28)) # IPv4 + UDP
    for seq in range(total):
        target=start+int(seq*a.interval*1e6);lag=time.monotonic_ns()-target
        if lag<0: time.sleep(-lag/1e9)
        tx=time.monotonic_ns();flow=seq%a.flows;body=T.pack(tx)+bytes([seq%251])*a.size
        w.writerow(dict(seq=seq,flow=flow,tx_ns=tx,phase='warmup' if seq*a.interval<1000*a.warmup else 'measure',payload_bytes=a.size,schedule_lag_ms=max(0,(tx-target)/1e6)))
        send(seq,flow,tx,body,seq%a.k,schedule(a.mode,seq,flow,weights,a.single))
        if a.mode=='fec':
            block.append(body)
            if len(block)==a.k:
                t=time.monotonic_ns();parity=xor(block);encode=time.monotonic_ns()-t;parity_tx=time.monotonic_ns()
                wc.writerow(dict(block_base=seq//a.k*a.k,encode_ns=encode,parity_tx_ns=parity_tx))
                send(seq//a.k*a.k,flow,parity_tx,parity,a.k,[a.single]);block=[]
    f.close();fw.close();fe.close();fc.close()
    for s in con:s.close()
    (out/'sender.json').write_text(json.dumps({'packets':total,'duration_s':(time.monotonic_ns()-start)/1e9,'fec_partial_block':len(block)}))

def receiver(a):
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True);sel=selectors.DefaultSelector()
    for port in map(int,a.ports.split(',')):
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,4*1024*1024);s.bind(('0.0.0.0',port));sel.register(s,selectors.EVENT_READ)
    f,w=writer(out/'rx.csv',['seq','flow','tx_ns','rx_ns','path','symbol','duplicate','reordered','fec_recovered','decode_ns','payload_bytes'])
    seen=set();blocks={};highest=-1;end=time.monotonic()+a.duration
    (out/'ready').write_text('ready')
    def deliver(seq,flow,body,rx,path,symbol,recovered=0,decode=0):
        nonlocal highest
        duplicate=seq in seen;reordered=int(not duplicate and seq<highest)
        if not duplicate:seen.add(seq);highest=max(highest,seq)
        w.writerow(dict(seq=seq,flow=flow,tx_ns=T.unpack(body[:8])[0],rx_ns=rx,path=path,symbol=symbol,duplicate=int(duplicate),reordered=reordered,fec_recovered=recovered,decode_ns=decode,payload_bytes=len(body)-8))
    while time.monotonic()<end:
        for key,_ in sel.select(.1):
            packet,_=key.fileobj.recvfrom(2048);rx=time.monotonic_ns()
            if len(packet)<H.size+8:continue
            magic,exp,flow,seq,tx,mode,path,k,symbol=H.unpack(packet[:H.size]);body=packet[H.size:]
            if magic!=b'HME1' or exp!=a.experiment or path>1 or k<2 or symbol>k:continue
            if mode!=MODES['fec'] or symbol<k:deliver(seq,flow,body,rx,path,symbol)
            if mode==MODES['fec']:
                base=seq//k*k; b=blocks.setdefault(base,{'data':{},'parity':None,'last':rx})
                if symbol==k:b['parity']=body
                else:b['data'][symbol]=body
                if b['parity'] is not None and len(b['data'])==k-1:
                    missing=next(i for i in range(k) if i not in b['data']);t=time.monotonic_ns();recovered=xor([b['parity']]+list(b['data'].values()));decode=time.monotonic_ns()-t
                    deliver(base+missing,(base+missing)%a.flows,recovered,time.monotonic_ns(),path,missing,1,decode);b['data'][missing]=recovered
                if len(b['data'])==k:blocks.pop(base,None)
        now=time.monotonic_ns();blocks={b:v for b,v in blocks.items() if now-v['last']<5e9}
    f.close()
    for key in list(sel.get_map().values()):key.fileobj.close()

def echo(a):
    sel=selectors.DefaultSelector()
    for p in map(int,a.ports.split(',')):
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('0.0.0.0',p));sel.register(s,selectors.EVENT_READ)
    end=time.monotonic()+a.duration
    while time.monotonic()<end:
        for key,_ in sel.select(.1):
            data,peer=key.fileobj.recvfrom(512)
            try:key.fileobj.sendto(data,peer)
            except OSError:pass

def probe(a):
    sockets=[]
    for target in a.targets.split(','):
        h,p=target.rsplit(':',1);s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect((h,int(p)));s.settimeout(.4);sockets.append(s)
    f,w=writer(a.out,['timestamp_ns','seq','path','rtt_ms','lost']);end=time.monotonic()+a.duration;seq=0
    while time.monotonic()<end:
        for path,s in enumerate(sockets):
            t=time.monotonic_ns();token=T.pack(t)
            try:
                s.send(token)
                while s.recv(512)!=token:pass
                rtt=(time.monotonic_ns()-t)/1e6;lost=0
            except (socket.timeout,OSError):rtt='';lost=1
            w.writerow(dict(timestamp_ns=t,seq=seq,path=path,rtt_ms=rtt,lost=lost))
        seq+=1;time.sleep(.1)
    f.close()
def main():
    p=argparse.ArgumentParser();p.add_argument('role',choices=['send','recv','echo','probe']);p.add_argument('--out',required=True);p.add_argument('--mode',choices=MODES,default='single');p.add_argument('--targets',default='10.201.1.2:9001,10.201.2.2:9002');p.add_argument('--ports',default='9001,9002');p.add_argument('--duration',type=float,default=120);p.add_argument('--warmup',type=float,default=10);p.add_argument('--interval',type=float,default=20);p.add_argument('--size',type=int,default=200);p.add_argument('--k',type=int,default=5);p.add_argument('--single',type=int,choices=[0,1],default=0);p.add_argument('--weights',default='1,1');p.add_argument('--flows',type=int,default=1);p.add_argument('--experiment',type=int,default=1);a=p.parse_args();{'send':sender,'recv':receiver,'echo':echo,'probe':probe}[a.role](a)
if __name__=='__main__':main()
