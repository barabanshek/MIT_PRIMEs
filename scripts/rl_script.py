from env_shim_demo import *
from env_shim import *
import numpy as np
import random
import time
import os
import gym
import json
import matplotlib.pyplot as plt
import matplotlib as mpl
import seaborn as sns
import pandas as pd

import unittest
from copy import deepcopy
from tqdm.notebook import tqdm
from dataclasses import dataclass
from typing import Any
mpl.rcParams['figure.dpi']= 100

# some util functions
def plot(logs, x_key, y_key, legend_key, **kwargs):
    nums = len(logs[legend_key].unique())
    palette = sns.color_palette("hls", nums)
    if 'palette' not in kwargs:
        kwargs['palette'] = palette
    ax = sns.lineplot(x=x_key, y=y_key, data=logs, hue=legend_key, **kwargs)
    return ax

def set_random_seed(seed):
    np.random.seed(seed)
    random.seed(seed)

def argmax(array):
    array = np.array(array)
    return np.random.choice(np.where(array == array.max())[0])


# set random seed
seed = 0
set_random_seed(seed=seed)

#To simulate a realistic Bandit scenario, we will make use of the BanditEnv.
@dataclass
class BanditEnv:

    def step(self, action):
        # run and get 90th percentile latency as reward
        # action is int : -1, 0, or 1 and represents decreasing, maintaining, or increasing the current containerConcurrency
        tail_lat = RLEnv.invoke_function(action)
        return tail_lat
    
#Code for running the bandit environment. 
@dataclass
class BanditEngine:
    max_steps: int
    agent: Any

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
                reward = self.env.step(action)
                self.agent.update_Q(action, reward)
                run_actions.append(action)
                run_rewards.append(reward)
            data = {'reward': run_rewards, 
                    'action': run_actions, 
                    'step': np.arange(len(run_rewards))}
            if hasattr(self.agent, 'epsilon'):
                data['epsilon'] = self.agent.epsilon
            run_log = pd.DataFrame(data)
            log.append(run_log)
        return log

#Code for aggregrating results of running an agent in the bandit environment. 
def bandit_sweep(agents, labels, n_runs=2000, max_steps=500):
    logs = dict()
    pbar = tqdm(agents)
    for idx, agent in enumerate(pbar):
        pbar.set_description(f'Alg:{labels[idx]}')
        engine = BanditEngine(max_steps=max_steps, agent=agent)
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
    epsilon: float = 0.1

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
        else:
            self.best_action = argmax(self.Q)
            selected_action = self.best_action
            
        return selected_action


# Demo parameters.
kDemoDeploymentActions = {
    "fibonacci": {
        "benchmark_name": "fibonacci",
        "functions": {
            "fibonacci-python": [1, 10]
        },
        "entry_point": "fibonacci-python",
        "port": 80
    },

    "fibonacci_10": {
        "benchmark_name": "fibonacci",
        "functions": {
            "fibonacci-python": [2, 10]
        },
        "entry_point": "fibonacci-python",
        "port": 80
    },

    "video-analytics": {
        "benchmark_name": "video-analytics",
        "functions": {
            "decoder": [1, 3, 1],
            "recog": [2, 3, 1],
            "streaming": [3, 3, 1]
        },
        "entry_point": "streaming",
        "port": 80
    },

    "video-analytics-same-node": {
        "benchmark_name": "video-analytics",
        "functions": {
            "decoder": [1, 3],
            "recog": [1, 3],
            "streaming": [1, 3]
        },
        "entry_point": "streaming",
        "port": 80
    },

    "online-shop-ad": {
        "benchmark_name": "online-shop",
        "functions": {
            "adservice": [1, 5]
        },
        "entry_point": "adservice",
        "port": 80
    },

    "online-shop-cart": {
        "benchmark_name": "online-shop",
        "functions": {
            "cartservice": [1, 5]
        },
        "entry_point": "cartservice",
        "port": 80
    },

    "online-shop-currency": {
        "benchmark_name": "online-shop",
        "functions": {
            "currencyservice": [3, 5]
        },
        "entry_point": "currencyservice",
        "port": 80
    },

    "online-shop-email": {
        "benchmark_name": "online-shop",
        "functions": {
            "emailservice": [2, 5]
        },
        "entry_point": "emailservice",
        "port": 80
    },

    "online-shop-payment": {
        "benchmark_name": "online-shop",
        "functions": {
            "paymentservice": [4, 5]
        },
        "entry_point": "paymentservice",
        "port": 80
    },

    "online-shop-productcatalogservice": {
        "benchmark_name": "online-shop",
        "functions": {
            "productcatalogservice": [3, 5]
        },
        "entry_point": "productcatalogservice",
        "port": 80
    },

    "online-shop-shippingservice": {
        "benchmark_name": "online-shop",
        "functions": {
            "shippingservice": [3, 5]
        },
        "entry_point": "shippingservice",
        "port": 80
    },

    "hotel-app-geo-tracing": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-geo-tracing": [2, 5]
        },
        "entry_point": "hotel-app-geo-tracing",
        "port": 80
    },

    "hotel-app-geo": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-geo": [2, 5]
        },
        "entry_point": "hotel-app-geo",
        "port": 80
    },

    "hotel-app-profile": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-profile": [2, 5]
        },
        "entry_point": "hotel-app-profile",
        "port": 80
    },

    "hotel-app-rate": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-rate": [2, 5]
        },
        "entry_point": "hotel-app-rate",
        "port": 80
    },

    "hotel-app-recommendation": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-recommendation": [3, 15]
        },
        "entry_point": "hotel-app-recommendation",
        "port": 80
    },

    "hotel-app-reservation": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-reservation": [2, 5]
        },
        "entry_point": "hotel-app-reservation",
        "port": 80
    },

    "hotel-app-user": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-user": [2, 5]
        },
        "entry_point": "hotel-app-user",
        "port": 80
    }
}

class RLEnv:
    def __init__(self, server_configs_json, rl_configs_json):
        with open(rl_configs_json, 'r') as f:
            json_data = json.load(f)
        self.serverconfig = json_data['env_shim_demo_args']['serverconfig']
        self.benchmark = json_data['env_shim_demo_args']['benchmark']
        self.duration = json_data['env_shim_demo_args']['duration']
        self.rps = json_data['env_shim_demo_args']['rps']
        self.agent = EpsilonGreedyAgent(num_actions=3)
        self.env = Env(server_configs_json)

        self.env.enable_env()

        # Exec demo configuration.
        # Deploy.
        ret = self.env.deploy_application(
            kDemoDeploymentActions[self.benchmark]['benchmark_name'], kDemoDeploymentActions[self.benchmark]['functions'])
        if ret == EnvStatus.ERROR:
            assert False

    def invoke_function(self, action):
        for params in kDemoDeploymentActions[self.benchmark]['functions'].items():
            params[2] = max(1, params[2] + action) # TODO: replace list with dict in yaml dicts
        self.env.deploy_application(self.benchmark, kDemoDeploymentActions)

        (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename = \
        self.env.invoke_application(
            kDemoDeploymentActions[self.benchmark]['benchmark_name'],
            kDemoDeploymentActions[self.benchmark]['entry_point'],
            {'port': kDemoDeploymentActions[self.benchmark]['port'], 'duration': self.duration, 'rps': self.rps})

        # Sample env.
        env_state = self.env.sample_env(self.duration)
        lat_stat = self.env.get_latencies(stat_lat_filename)
        lat_stat.sort()
        tail_lat = lat_stat[(int)(len(lat_stat) * 0.90)] # 90th pct latency
        return tail_lat
    
    

def main(args):
    rl_env = RLEnv(args.serverconfig, args.rlconfig)
    logs = bandit_sweep([rl_env.agent], ['Epsilon Greedy Agent'], n_runs=3)
    plot(logs, logs['step'], logs['reward'], 'Alg')

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