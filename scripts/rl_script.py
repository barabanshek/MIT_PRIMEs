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


# calculate instantaneous reward
def calculate_reward(r):
    return 1 - r ** 0.4

# discretize state variable
def calculate_state(s):
    if s > 0.80:
        return 4
    elif s > 0.60:
        return 3
    elif s > 0.40:
        return 2
    elif s > 0.20:
        return 1
    else:
        return 0

# set random seed
seed = 0
set_random_seed(seed=seed)

@dataclass
class BanditEnv:
    
    def step(self, rl_env, action):
        # calculate reward
        # action is int : -1, 0, or 1 and represents decreasing, maintaining, or increasing the configs
        r, s = rl_env.take_action(action)
        reward = calculate_reward(r)
        state = calculate_state(s)
        return (reward, state)
    

#Code for running the bandit environment. 
@dataclass
class BanditEngine:
    max_steps: int
    agent: Any
    rl_env: Any

    def __post_init__(self):
        self.env = BanditEnv()
        self.state = 0
    
    def run(self, n_runs=1):
        log = []
        for i in tqdm(range(n_runs), desc='Runs'):
            run_rewards = []
            run_actions = []
            run_CPUs = []
            self.agent.reset()
            for t in range(self.max_steps):
                time.sleep(1)
                try:
                    prev_state = self.state
                    action = self.agent.get_action(self.state)
                    reward, self.state = self.env.step(self.rl_env, action)
                    self.agent.update_Q(prev_state, self.state, action, reward, t)
                    run_actions.append(action)
                    run_rewards.append(reward)
                    cpu = self.rl_env.take_action(action)[1]
                    run_CPUs.append(cpu)
                    wandb.log({"action" : action, "reward" : reward, "state" : self.state, "CPU utilization" : cpu})
                    data = {'reward': run_rewards, 
                    'action': run_actions, 
                    'step': np.arange(len(run_rewards))}
                    if hasattr(self.agent, 'epsilon'):
                        data['epsilon'] = self.agent.epsilon
                    run_log = pd.DataFrame(data)
                    log.append(run_log)
                except:
                    print('> Error encountered during this step, probably due to empty latency list.')
                    print('> This step has been skipped.')
                    pass
        return log

#Code for aggregrating results of running an agent in the bandit environment. 
def bandit_sweep(agents, rl_env, labels, n_runs=1, max_steps=10):
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
    alpha: float = 0.5
    gamma : float = 0.9
    epsilon_decay : float = 0.995

    def __post_init__(self):
        self.reset()

    def reset(self):
        self.epsilon = 0.9
        self.action_counts = np.zeros(self.num_actions) # action counts n(a)
        
        # Q-Table
        # 5 states : > {0, 20, 40, 60, 80} percent CPU usage
        # 3 actions : increase, decrease, maintain number of instances
        self.Q = np.zeros((5, 3)) # Q table
    
    def update_Q(self, prev_state, state, action, reward, t):
        if t > 50 and self.epsilon > 0.1 / self.epsilon_decay:
            self.epsilon *= self.epsilon_decay
        self.action_counts[action] += 1
        self.Q[prev_state][action] = self.Q[prev_state][action] * (1-self.alpha) + self.alpha * (reward + self.gamma*max(self.Q[state])) # add discounted reward
        
    def get_action(self, state):
        print(f'current state: {state}')
        print('Q-Table:')
        print(self.Q)
        if state < 0 or random.random() < self.epsilon:
            selected_action = random.choice(range(0, self.Q.shape[1]))
            print('choosing random action...')
            print(f'chose action: {selected_action}!')
        else:
            self.action_choices = self.Q[state]
            self.best_action = argmax(self.action_choices)
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
    },
    "video-analytics-same-node": {
    "benchmark_name": "video-analytics",
    "functions": [],
    "entry_point": "streaming",
    "port": 80
    },
    "hotel-app-rate": {
    "benchmark_name": "hotel-app",
    "functions": [],
    "entry_point": "hotel-app-rate",
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
        self.actions = json_data['actions']
        self.step_size = json_data['step_size']
        self.services = json_data['services']
        self.node = json_data['node']
        self.revision_index = 0
        self.agent = EpsilonGreedyAgent(num_actions=len(self.actions))
        self.env = Env(server_configs_json)
        self.all_params = ['containerScale', 'containerConcurrency']
        self.default_param_vals = [1, 10]
        self.env.enable_env()

        functions = []
        for val in range(self.min_, self.max_+self.step_size, self.step_size):
            dict_ = {}
            for i in range(len(self.services)):
                dict_[self.services[i]] = {'node' : self.node, self.param : val}
                for j in range(len(self.all_params)):
                    if self.all_params[j] != self.param:
                        dict_[self.services[i]][self.all_params[j]] = self.default_param_vals[j]
            functions.append(dict_)
        kDemoDeploymentActions[self.benchmark]['functions'] = functions
        # Exec demo configuration.
        # Deploy.
        self.param_val = self.kd_benchmark['functions'][self.revision_index][self.entry_point][self.param]
        self.env.deploy_all_revisions(self.kd_benchmark['benchmark_name'], self.kd_benchmark['functions'])

    # invoke function given the action
    def take_action(self, action):
        action_val = self.actions[action]
        print(self.param_val)
        if self.param_val + action_val in range (self.min_, self.max_+self.step_size):
            self.param_val += action_val
            print('changing revision...')

        # looking for the updated revision
        for i in range(len(self.kd_benchmark['functions'])):
            funct = self.kd_benchmark['functions'][i]
            if funct[self.entry_point][self.param] == self.param_val:
                self.revision_index = i
        print(f'revision: {self.revision_index+1} (starting from 1, not 0)')
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
        if len(lat_stat) == 0:
            print('> ERROR: No latencies were collected. Perhaps try using a smaller RPS value if this problem persists.')

        # printing stats
        print(
            f'    stat: {stat_issued}, {stat_completed}, {stat_real_rps}, {stat_target_rps}, latency file: {stat_lat_filename}')
        print('    50th: ', lat_stat[(int)(len(lat_stat) * 0.5)])
        print('    90th: ', lat_stat[(int)(len(lat_stat) * 0.90)])
        print('    99th: ', lat_stat[(int)(len(lat_stat) * 0.99)])
        print('    99.9th: ', lat_stat[(int)(len(lat_stat) * 0.999)])
        print('    env_state:', env_state)
        rps_delta = np.abs(stat_real_rps - stat_target_rps)
        rps_ratio = rps_delta / stat_target_rps
        cpu_usage = env_state[self.kd_benchmark['functions'][self.revision_index][self.entry_point]['node']]['cpu'][1]
        tail_lat = lat_stat[(int)(len(lat_stat) * 0.99)] # 99th pct latency
        QOS_LAT = 4000000
        lat_ratio = tail_lat / QOS_LAT

        return (lat_ratio, cpu_usage) # used to calculate reward and update state
    
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
