"""Approximate paired-run power planning; final nonlinear endpoints need simulation."""
import argparse,json,math
import pandas as pd
from scipy.stats import norm

def main():
    p=argparse.ArgumentParser();p.add_argument('--runs',required=True);p.add_argument('--state',required=True);p.add_argument('--metric',required=True);p.add_argument('--a',required=True);p.add_argument('--b',required=True);p.add_argument('--delta',type=float,required=True);p.add_argument('--alpha',type=float,default=.05);p.add_argument('--power',type=float,default=.8);p.add_argument('--comparisons',type=int,default=1);a=p.parse_args()
    if a.delta<=0 or not 0<a.alpha<1 or not 0<a.power<1 or a.comparisons<1:p.error('invalid power parameters')
    df=pd.read_csv(a.runs);q=df[df.state==a.state].pivot(index='block',columns='mode',values=a.metric);d=(q[a.a]-q[a.b]).dropna()
    if len(d)<3:p.error('at least three pilot pairs required')
    sd=d.std(ddof=1);n=math.ceil(((norm.ppf(1-a.alpha/a.comparisons/2)+norm.ppf(a.power))*sd/a.delta)**2)
    print(json.dumps({'pilot_pairs':len(d),'paired_sd':sd,'delta':a.delta,'normal_approximation_pairs':max(2,n),'note':'Planning estimate only; include SD uncertainty, autocorrelation and simulation for final sample size.'},indent=2))
if __name__=='__main__':main()
