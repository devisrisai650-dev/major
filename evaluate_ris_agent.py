"""Reproducible multi-seed evaluation for the software-only virtual RIS-CNOMA backend."""
from __future__ import annotations
import argparse, csv, json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from ris_agent import QLearningRISAgent, train_agent
from ris_environment import PRIORITY_WEIGHT, RISEnvironment

SCENARIOS={"light":{"noise":0.75,"delay":0,"rain_mm":5.0,"flow_velocity_mps":0.5},"moderate":{"noise":1.5,"delay":1,"rain_mm":25.0,"flow_velocity_mps":1.0},"severe":{"noise":2.25,"delay":2,"rain_mm":60.0,"flow_velocity_mps":1.8}}
POLICIES=("agent","random","fixed","best_fixed","myopic_noisy","oracle")

def bootstrap_ci(values,seed=2026,samples=2000):
 values=np.asarray([v for v in values if v is not None and np.isfinite(v)],dtype=float)
 if values.size==0:return (None,None)
 rng=np.random.default_rng(seed);means=np.mean(rng.choice(values,(samples,values.size),replace=True),axis=1)
 return tuple(np.percentile(means,[2.5,97.5]))

def choose_action(env,observation,policy,rng,fixed_action=None):
 mask=env.action_mask(observation);valid=np.flatnonzero(mask)
 if policy=="agent":return env.agent.choose_action(observation,mask,explore=False)
 if policy in {"myopic_noisy","oracle"}:return env.greedy_baseline_action(observation)
 if policy=="random":return int(rng.choice(valid))
 if policy=="fixed":return 0 if mask[0] else int(valid[0])
 if policy=="best_fixed":
  if fixed_action is not None and mask[fixed_action]:return fixed_action
  return int(valid[0])
 raise ValueError(f"Unknown policy {policy}")

def run_episode(env,policy,episode_seed,priority,scenario,agent=None):
 from collections import deque
 env.reseed(episode_seed);env.observation_mode="oracle" if policy=="oracle" else "partial"
 env.snr_noise_std_db=SCENARIOS[scenario]["noise"];env.observation_delay=SCENARIOS[scenario]["delay"]
 env.channel_context={"rain_mm":SCENARIOS[scenario]["rain_mm"],"flow_velocity_mps":SCENARIOS[scenario]["flow_velocity_mps"]}
 env._history=deque(maxlen=max(2,env.observation_delay+1));observation=env.reset(priority=priority);env.agent=agent
 rng=np.random.default_rng(episode_seed+991);fixed_action=env.greedy_baseline_action(observation) if policy=="best_fixed" else None
 delivered=critical_delivered=0;weighted_delivered=0.0;latency=[];snr=[];aoi=0.0;aoi_samples=[];reconfigs=0;rewards=[];sic_successes=[]
 for _ in range(env.max_steps):
  action=choose_action(env,observation,policy,rng,fixed_action);observation,reward,done,info=env.step(action)
  rewards.append(reward);reconfigs+=int(info["changed_ris"]);sic_successes.append(float(bool(info["sic_success"])))
  if info["delivered"]:
   delivered+=1;weighted_delivered+=PRIORITY_WEIGHT[priority]
   if priority=="CRITICAL":critical_delivered+=1
   latency.append(info["latency_ms"]);snr.append(info["snr_db"]);aoi=float(info["latency_ms"])
  else:aoi+=float(info["latency_ms"] or 100.0)
  aoi_samples.append(aoi)
  if done:break
 return {"seed":episode_seed,"policy":policy,"scenario":scenario,"priority":priority,"steps":env.max_steps,"delivery_rate":delivered/env.max_steps,"critical_delivery_rate":critical_delivered/env.max_steps if priority=="CRITICAL" else np.nan,"priority_weighted_delivery":weighted_delivered/(env.max_steps*PRIORITY_WEIGHT[priority]),"mean_latency_ms":float(np.mean(latency)) if latency else np.nan,"mean_aoi_ms":float(np.mean(aoi_samples)),"mean_snr_db":float(np.mean(snr)) if snr else np.nan,"ris_reconfigurations":reconfigs,"mean_reward":float(np.mean(rewards)),"cnoma_sic_success_rate":float(np.mean(sic_successes)) if sic_successes else np.nan,"observation_mode":env.observation_mode,"observation_noise_std_db":env.snr_noise_std_db,"observation_delay_steps":env.observation_delay,"simulation_only":True}

def _write_csv(path,rows):
 if not rows:return
 with path.open("w",newline="",encoding="utf-8") as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

def _aggregate(rows,keys,metrics):
 grouped={}
 for row in rows:grouped.setdefault(tuple(row[k] for k in keys),[]).append(row)
 output=[]
 for key,subset in grouped.items():
  result=dict(zip(keys,key))
  for metric in metrics:
   values=np.asarray([r[metric] for r in subset if np.isfinite(r[metric])],dtype=float)
   result[f"{metric}_mean"]=float(np.mean(values)) if values.size else np.nan
   low,high=bootstrap_ci(values);result[f"{metric}_ci95_low"]=low;result[f"{metric}_ci95_high"]=high
  output.append(result)
 return output

def train_and_evaluate(train_seeds,eval_seeds,episodes,eval_episodes_per_seed,steps,output_dir,learned_weight):
 output_dir.mkdir(parents=True,exist_ok=True);episode_rows=[]
 for train_seed in train_seeds:
  env=RISEnvironment(seed=train_seed,max_steps=steps,observation_mode="partial");agent=QLearningRISAgent(seed=train_seed,learned_value_weight=learned_weight);train_agent(agent,env,episodes=episodes,max_steps=steps)
  if train_seed==train_seeds[0]:agent.save(output_dir.parent/"models"/"ris_q_table.npz")
  for eval_seed in eval_seeds:
   for repeat in range(eval_episodes_per_seed):
    episode_seed=eval_seed+repeat*100000
    for scenario in SCENARIOS:
     for priority in PRIORITY_WEIGHT:
      for policy in POLICIES:
       eval_env=RISEnvironment(seed=episode_seed,max_steps=steps,observation_mode="partial");row=run_episode(eval_env,policy,episode_seed,priority,scenario,agent);row["train_seed"]=train_seed;row["learned_value_weight"]=learned_weight;episode_rows.append(row)
 _write_csv(output_dir/"ris_episode_results.csv",episode_rows)
 metrics=["delivery_rate","critical_delivery_rate","priority_weighted_delivery","mean_latency_ms","mean_aoi_ms","mean_snr_db","ris_reconfigurations","mean_reward","cnoma_sic_success_rate"]
 summary=_aggregate(episode_rows,["policy","scenario"],metrics);_write_csv(output_dir/"ris_summary.csv",summary)
 priority_summary=_aggregate(episode_rows,["policy","scenario","priority"],["delivery_rate","mean_latency_ms","mean_aoi_ms","priority_weighted_delivery","cnoma_sic_success_rate"]);_write_csv(output_dir/"ris_priority_summary.csv",priority_summary)
 metadata={"created_utc":datetime.now(timezone.utc).isoformat(),"simulation_only":True,"training_seeds":list(train_seeds),"evaluation_seeds":list(eval_seeds),"evaluation_repeats_per_seed":eval_episodes_per_seed,"training_episodes_per_seed":episodes,"steps_per_episode":steps,"learned_value_weight":learned_weight,"observation_scenarios":SCENARIOS,"cnoma":{"users":2,"sic":True,"power_profiles":3},"policies":list(POLICIES),"priorities":list(PRIORITY_WEIGHT),"outputs":["ris_episode_results.csv","ris_summary.csv","ris_priority_summary.csv","ris_weight_ablation.csv"],"notes":["All channel, RIS, SNR, latency, delivery and AoI values are software simulations.","Evaluation seeds are disjoint from training seeds.","The oracle policy uses perfect current information and is a reference upper case."]}
 (output_dir/"experiment_metadata.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8");return episode_rows,summary

def run_weight_ablation(train_seeds,eval_seeds,episodes,steps,output_dir,default_weight):
 rows=[]
 for weight in [0.0,default_weight]:
  for train_seed in train_seeds:
   env=RISEnvironment(seed=train_seed,max_steps=steps,observation_mode="partial");agent=QLearningRISAgent(seed=train_seed,learned_value_weight=weight);train_agent(agent,env,episodes=episodes,max_steps=steps)
   for eval_seed in eval_seeds:
    for priority in PRIORITY_WEIGHT:
     eval_env=RISEnvironment(seed=eval_seed,max_steps=steps);row=run_episode(eval_env,"agent",eval_seed,priority,"moderate",agent);rows.append({"learned_value_weight":weight,"train_seed":train_seed,"eval_seed":eval_seed,"priority":priority,"delivery_rate":row["delivery_rate"],"mean_latency_ms":row["mean_latency_ms"],"mean_aoi_ms":row["mean_aoi_ms"]})
 summary=_aggregate(rows,["learned_value_weight","priority"],["delivery_rate","mean_latency_ms","mean_aoi_ms"]);_write_csv(output_dir/"ris_weight_ablation.csv",summary)

def main():
 parser=argparse.ArgumentParser(description="Multi-seed software-only RIS evaluation");parser.add_argument("--train-seeds",type=int,default=10);parser.add_argument("--train-episodes",type=int,default=250);parser.add_argument("--eval-seeds",type=int,default=5);parser.add_argument("--eval-episodes-per-seed",type=int,default=1);parser.add_argument("--steps",type=int,default=40);parser.add_argument("--seed",type=int,default=1000);parser.add_argument("--learned-weight",type=float,default=0.05);parser.add_argument("--output-dir",default="outputs");args=parser.parse_args()
 if min(args.train_seeds,args.train_episodes,args.eval_seeds,args.eval_episodes_per_seed,args.steps)<1:parser.error("all counts must be positive")
 if args.learned_weight<0:parser.error("learned weight must be non-negative")
 train_seeds=[args.seed+i for i in range(args.train_seeds)];eval_seeds=[args.seed+10000+i for i in range(args.eval_seeds)];output_dir=Path(args.output_dir)
 rows,summary=train_and_evaluate(train_seeds,eval_seeds,args.train_episodes,args.eval_episodes_per_seed,args.steps,output_dir,args.learned_weight);run_weight_ablation(train_seeds,eval_seeds,args.train_episodes,args.steps,output_dir,args.learned_weight)
 print("SOFTWARE-ONLY MULTI-SEED RIS-CNOMA EVALUATION");print(f"Independent training seeds: {len(train_seeds)}");print(f"Disjoint evaluation seeds: {len(eval_seeds)}");print(f"Episode rows: {len(rows)}")
 for row in summary:
  if row["scenario"]=="moderate":print(f"{row['policy']:>14} | delivery={row['delivery_rate_mean']:.3f} [{row['delivery_rate_ci95_low']:.3f}, {row['delivery_rate_ci95_high']:.3f}]")
if __name__=="__main__":main()
