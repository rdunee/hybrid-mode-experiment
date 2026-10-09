"""Loopback integration checks; these produce test fixtures, not network results."""
import json,socket,subprocess,sys,tempfile,time,unittest
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
class Integration(unittest.TestCase):
    def test_modes_and_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)/'raw';raw.mkdir()
            for rep in range(2):
                for mode in ('single','striping','replication','fec'):
                    out=raw/f'{mode}-{rep}';out.mkdir();holds=[];ports=[]
                    for _ in range(2):
                        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('127.0.0.1',0));ports.append(s.getsockname()[1]);holds.append(s)
                    for s in holds:s.close()
                    receiver=subprocess.Popen([sys.executable,str(ROOT/'dataplane/engine.py'),'recv','--out',str(out),'--ports',','.join(map(str,ports)),'--duration','.8'])
                    try:
                        for _ in range(100):
                            if (out/'ready').exists():break
                            time.sleep(.01)
                        subprocess.run([sys.executable,str(ROOT/'dataplane/engine.py'),'send','--out',str(out),'--targets',','.join(f'127.0.0.1:{p}' for p in ports),'--mode',mode,'--warmup','.2','--duration','.2'],check=True)
                        self.assertEqual(receiver.wait(timeout=3),0)
                    finally:
                        if receiver.poll() is None:receiver.kill();receiver.wait()
                    rx=pd.read_csv(out/'rx.csv');wire=pd.read_csv(out/'wire.csv')
                    self.assertEqual(rx.seq.nunique(),20)
                    self.assertEqual(len(wire),40 if mode=='replication' else 24 if mode=='fec' else 20)
                    if mode=='replication':self.assertEqual(rx.duplicate.sum(),20)
                    (out/'metadata.json').write_text(json.dumps({'valid':True,'failures':[],'id':out.name,'block':rep,'rep':rep,'loss_pct':0,'mode':mode,'state':'L0','config':{'measurement_s':.2,'paths':[{'rtt_ms':30},{'rtt_ms':50}]}}))
            output=Path(tmp)/'results'
            subprocess.run([sys.executable,'-m','analysis.pipeline','--raw',str(raw),'--output',str(output),'--weights',str(ROOT/'configs/stage1/objective-example.json')],cwd=ROOT,check=True)
            runs=pd.read_csv(output/'runs.csv');self.assertEqual(len(runs),8);self.assertEqual(runs.loss.sum(),0)
            self.assertTrue((output/'preferred_mode_heatmap.pdf').exists());self.assertTrue((output/'oracle_cross_validation.csv').exists());self.assertEqual(len(pd.read_csv(output/'paired_comparisons.csv')),42)
if __name__=='__main__':unittest.main()
