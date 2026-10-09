import unittest,tempfile,subprocess,sys,time,socket
from pathlib import Path
from dataplane.engine import xor,schedule,H,T
from orchestrator.run_experiment import matrix
from analysis.pipeline import pareto,bootstrap,paired_test
import yaml,numpy as np
ROOT=Path(__file__).resolve().parents[1]
class Core(unittest.TestCase):
    def test_fec_every_single_erasure(self):
        data=[T.pack(i)+bytes([i])*200 for i in range(5)];parity=xor(data)
        for missing in range(5):self.assertEqual(xor([parity]+[d for i,d in enumerate(data) if i!=missing]),data[missing])
    def test_matrix(self):
        cfg=yaml.safe_load((ROOT/'configs/stage1/pilot.yaml').read_text());a=matrix(cfg);self.assertEqual(a,matrix(cfg));self.assertEqual(len(a),240);self.assertEqual(len({r['id'] for r in a}),240)
        for block in range(60):self.assertEqual({r['mode'] for r in a if r['block']==block},set(cfg['modes']))
    def test_pareto(self):self.assertEqual(pareto([[1,1],[2,2],[.5,2],[1,1]]).tolist(),[True,False,True,True])
    def test_flow_affinity(self):self.assertEqual(schedule('steering',1,7,[1,1],0),schedule('steering',99,7,[1,1],0))
    def test_statistics(self):self.assertEqual(bootstrap([1,1,1]),(1.,1.));self.assertEqual(paired_test([0,0]),1)
    def test_receiver_recovery_duplicates_reordering(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('127.0.0.1',0));port=s.getsockname()[1];s.close()
            p=subprocess.Popen([sys.executable,str(ROOT/'dataplane/engine.py'),'recv','--out',tmp,'--ports',str(port),'--duration','1'])
            try:
                for _ in range(100):
                    if (Path(tmp)/'ready').exists():break
                    time.sleep(.01)
                sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);data=[T.pack(time.monotonic_ns())+bytes([i])*20 for i in range(5)]
                for i in (1,0,3,4,1):sock.sendto(H.pack(b'HME1',1,0,i,time.monotonic_ns(),4,0,5,i)+data[i],('127.0.0.1',port))
                sock.sendto(H.pack(b'HME1',1,0,0,time.monotonic_ns(),4,0,5,5)+xor(data),('127.0.0.1',port));p.wait(timeout=3)
                import pandas as pd
                rx=pd.read_csv(Path(tmp)/'rx.csv');self.assertEqual(set(rx.seq),set(range(5)));self.assertEqual(rx.fec_recovered.sum(),1);self.assertEqual(rx.duplicate.sum(),1);self.assertGreater(rx.reordered.sum(),0);self.assertEqual(rx.loc[rx.seq==2,'tx_ns'].iloc[0],T.unpack(data[2][:8])[0]);sock.close()
            finally:
                if p.poll() is None:p.kill();p.wait()
if __name__=='__main__':unittest.main()
