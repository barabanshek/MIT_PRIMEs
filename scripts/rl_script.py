from env_shim import *
import numpy as np
import random
import time
import os
import gym
import json
import matplotlib.pyplot as plt
import matplotlib as mpl
import pandas as pd
from tqdm import tqdm
import pickle
import wandb

import unittest
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

# some util functions

def set_random_seed(seed):
    np.random.seed(seed)
    random.seed(seed)

def argmax(array):
    array = np.array(array)
    return np.random.choice(np.where(array == array.max())[0])


# set random seed
seed = 0
set_random_seed(seed=seed)

@dataclass
class BanditEnv:

    def step(self, rl_env, action):
        # run and get 90th percentile latency as reward
        # action is int : -1, 0, or 1 and represents decreasing, maintaining, or increasing the configs
        tail_lat = rl_env.take_action(action)
        return 1/tail_lat

#Code for running the bandit environment. 
@dataclass
class BanditEngine:
    max_steps: int
    agent: Any
    rl_env: Any

    def __post_init__(self):
        self.env = BanditEnv()
    
    def run(self, n_runs=1):
        log = []
        for i in tqdm(range(n_runs), desc='Runs'):
            run_rewards = []
            run_actions = []
            self.agent.reset()
            for t in range(self.max_steps):
                action = self.agent.get_action()
                reward = self.env.step(self.rl_env, action)
                self.agent.update_Q(action, reward)
                run_actions.append(action)
                run_rewards.append(reward)
                wandb.log({"action" : action, "reward" : reward})
            data = {'reward': run_rewards, 
                    'action': run_actions, 
                    'step': np.arange(len(run_rewards))}
            if hasattr(self.agent, 'epsilon'):
                data['epsilon'] = self.agent.epsilon
            run_log = pd.DataFrame(data)
            log.append(run_log)
        return log

#Code for aggregrating results of running an agent in the bandit environment. 
def bandit_sweep(agents, rl_env, labels, n_runs=1, max_steps=20):
    logs = dict()
    pbar = tqdm(agents)
    for idx, agent in enumerate(pbar):
        pbar.set_description(f'Alg:{labels[idx]}')
        engine = BanditEngine(max_steps=max_steps, agent=agent, rl_env=rl_env)
        ep_log = engine.run(n_runs)
        ep_log = pd.concat(ep_log, ignore_index=True)
        ep_log['Alg'] = labels[idx]
        logs[f'{labels[idx]}'] = ep_log
    logs = pd.concat(logs, ignore_index=True)
    return logs

##EpsilonGreedy Agent
@dataclass
class EpsilonGreedyAgent:
    num_actions: int
    epsilon: float = 0.5

    def __post_init__(self):
        self.reset()

    def reset(self):
        self.t = 0
        self.action_counts = {-1 : 0, 0 : 0, 1 : 0} # action counts n(a)
        self.Q = {-1 : 0.0, 0 : 0.0, 1 : 0.0} # action value Q(a)
    
    def update_Q(self, action, reward):
        self.action_counts[action] += 1
        self.Q[action] += (1.0 / self.action_counts[action]) * (reward - self.Q[action])
        self.t += 1
        
    def get_action(self):
        if random.random() < self.epsilon:
            selected_action = random.choice(range(0, self.num_actions))
            print('choosing random action...')
            print(f'chose action: {selected_action}!')
        else:
            self.best_action = argmax(self.Q)
            selected_action = self.best_action
            print(f'best action is {selected_action}')
            
        return selected_action

# Demo parameters.
kDemoDeploymentActions = {
    "fibonacci": {
        "benchmark_name": "fibonacci",
        "functions": [],
        "entry_point": "fibonacci-python",
        "port": 80
    }
}
# 90th pct latency
tail_lat = None

class RLEnv:
    def __init__(self, server_configs_json, rl_configs_json):
        with open(rl_configs_json, 'r') as f:
            json_data = json.load(f)
        self.benchmark = json_data['benchmark']
        self.kd_benchmark = kDemoDeploymentActions[self.benchmark]
        self.entry_point = self.kd_benchmark['entry_point']
        self.rps = json_data['rps']
        self.duration = json_data['duration']
        self.n_runs = json_data['n_runs']
        self.param = json_data['parameter']
        self.min_ = json_data['min']
        self.max_ = json_data['max']
        self.revision_index = 5
        self.agent = EpsilonGreedyAgent(num_actions=3)
        self.env = Env(server_configs_json)
        self.env.enable_env()

        functions = [{'fibonacci-python' : {'node' : 1, 'containerScale' : i, 'containerConcurrency' : 10}} for i in range(self.min_, self.max_+1)]
        kDemoDeploymentActions[self.benchmark]['functions'] = functions
        # Exec demo configuration.
        # Deploy.
        self.param_val = self.kd_benchmark['functions'][self.revision_index][self.entry_point][self.param]
        self.env.deploy_all_revisions(self.kd_benchmark['benchmark_name'], self.kd_benchmark['functions'])

    # invoke function given the action
    def take_action(self, action):
        if self.param_val + action in range (self.min_, self.max_+1):
            self.param_val += action
            print('changing revision...')

        # looking for the updated revision
        funct = self.kd_benchmark['functions'][self.revision_index]
        funct[self.entry_point][self.param] = self.param_val
        self.revision_index = self.kd_benchmark['functions'].index(funct)

        # splitting traffic onto the updated revision
        self.env.split_traffic(self.kd_benchmark['entry_point'], self.revision_index+1)

        # invoking
        (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename = \
        self.env.invoke_application(
            self.kd_benchmark['benchmark_name'],
            self.kd_benchmark['entry_point'],
            {'port': self.kd_benchmark['port'], 'duration': self.duration, 'rps': self.rps})

        # Sample env.
        env_state = self.env.sample_env(self.duration)
        lat_stat = self.env.get_latencies(stat_lat_filename)
        lat_stat.sort()
        tail_lat = lat_stat[(int)(len(lat_stat) * 0.90)] # 90th pct latency

        # printing stats
        print(
            f'    stat: {stat_issued}, {stat_completed}, {stat_real_rps}, {stat_target_rps}, latency file: {stat_lat_filename}')
        print('    50th: ', lat_stat[(int)(len(lat_stat) * 0.5)])
        print('    90th: ', lat_stat[(int)(len(lat_stat) * 0.90)])
        print('    99th: ', lat_stat[(int)(len(lat_stat) * 0.99)])
        print('    99.9th: ', lat_stat[(int)(len(lat_stat) * 0.999)])
        print('    env_state:', env_state)
        return tail_lat # used to calculate reward
    
def main(args):
    wandb.init(project="rl-serverless", config={"node" : 1, "containerScale" : 1, "containerConcurrency" : 10})
    rl_env = RLEnv(args.serverconfig, args.rlconfig)
    logs = bandit_sweep([rl_env.agent], rl_env, ['Epsilon Greedy Agent'], n_runs=1)
    with open('logs.pickle', 'wb') as handle:
        pickle.dump(logs, handle, protocol=pickle.HIGHEST_PROTOCOL)
    wandb.finish()
#
# Example cmd:
#   python3 env_shim_demo.py --serverconfig server_configs.json --benchmark video-analytics --duration 10 --rps 5
#
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--serverconfig')
    parser.add_argument('--rlconfig')
    args = parser.parse_args()

    main(args)
