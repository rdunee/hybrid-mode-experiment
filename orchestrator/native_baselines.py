"""Direct native baselines only; these do NOT traverse the UDP mode engine."""
import argparse,csv,subprocess,time,urllib.request
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('kind',choices=['http','bulk']);p.add_argument('--url');p.add_argument('--host');p.add_argument('--requests',type=int,default=100);p.add_argument('--interval-s',type=float,default=.2);p.add_argument('--seconds',type=int,default=30);p.add_argument('--out',required=True);a=p.parse_args();Path(a.out).parent.mkdir(parents=True,exist_ok=True)
    if a.kind=='bulk':
        if not a.host:p.error('--host required')
        with open(a.out,'w') as f:subprocess.run(['iperf3','-c',a.host,'-t',str(a.seconds),'-J'],check=True,stdout=f)
    else:
        if not a.url:p.error('--url required')
        with open(a.out,'w',newline='') as f:
            w=csv.writer(f);w.writerow(['request','start_ns','completion_ms','bytes','error'])
            for i in range(a.requests):
                t=time.monotonic_ns();error='';body=b''
                try:
                    with urllib.request.urlopen(a.url,timeout=5) as response:body=response.read()
                except Exception as e:error=str(e)
                w.writerow([i,t,(time.monotonic_ns()-t)/1e6,len(body),error]);time.sleep(a.interval_s)
if __name__=='__main__':main()
