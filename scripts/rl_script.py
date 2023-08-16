import numpy as np
import random
import time
import json
import pandas as pd
import wandb
import argparse
import yaml

from tqdm import tqdm
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from yaml.loader import SafeLoader
from os import path
from k8s_env_shim import Env
from pprint import pprint
from setup_service import Service
from setup_deployment import Deployment

# Some util functions.

def set_random_seed(seed):
    np.random.seed(seed)
    random.seed(seed)

def argmax(array):
    array = np.array(array)
    return np.random.choice(np.where(array == array.max())[0])


# Calculate instantaneous reward.
def calculate_reward(r):
    return 1 - r ** 0.4

# Discretize state variable.
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

# Set random seed.
seed = 0
set_random_seed(seed=seed)

@dataclass
class BanditEnv:
    
    def step(self, rl_env, action):
        # Calculate reward and update state.
        r, s = rl_env.take_action(action)
        reward = calculate_reward(r)
        state = calculate_state(s)
        return (reward, state)
    

# Code for running the bandit environment. 
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
                while True:
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
                        param_val = self.rl_env.current_scale
                        print(f'Replicas : {param_val}')
                        wandb.log({"action" : action, 
                                   "reward" : reward, 
                                   "state" : self.state, 
                                   "CPU utilization" : cpu, 
                                   "Replicas" : int(param_val)})
                        data = {'reward': run_rewards, 
                        'action': run_actions, 
                        'step': np.arange(len(run_rewards))}
                        if hasattr(self.agent, 'epsilon'):
                            data['epsilon'] = self.agent.epsilon
                        run_log = pd.DataFrame(data)
                        log.append(run_log)
                    except Exception as e:
                        print(e)
                        print('[ERROR] Error encountered during this step, probably due to empty latency list.')
                        print('[ERROR] This step has been skipped.')
                        continue
                    break
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
        print(f'[INFO] Current state: {state}')
        print('[INFO] Q-Table:')
        print(self.Q)
        if state < 0 or random.random() < self.epsilon:
            print('[RUNNING] Choosing random action...')
            selected_action = random.choice(range(0, self.Q.shape[1]))
            print(f'[INFO] Chose action: {selected_action}!')
        else:
            self.action_choices = self.Q[state]
            self.best_action = argmax(self.action_choices)
            selected_action = self.best_action
            print(f'[INFO] Best action is {selected_action}')
            
        return selected_action

class RLEnv:
    def __init__(self, configs_json, rl_configs_json):
        # Instantiate Env.
        self.env = Env(configs_json)

        # Load and parse json config file.
        with open(configs_json, 'r') as f:
            configs_json_data = json.load(f)
        entry_point_function = configs_json_data['entry_point']
        functions = configs_json_data['functions']
        entry_point_function_index = functions.index(entry_point_function)

        self.deployments = []
        self.services = []

        # Load YAML files as JSON-formatted dictionaries
        for function in functions:
            # Instantiate Deployment objects
            file_name = f"k8s-yamls/{function}.yaml"
            with open(path.join(path.dirname(__file__), file_name)) as f:
                dep, svc = yaml.load_all(f, Loader=SafeLoader)
            deployment = Deployment(dep, self.env.api)
            self.deployments.append(deployment)

            # Instantiate Service objects
            port = svc['spec']['ports'][0]['port']
            service = Service(function, file_name, port)
            self.services.append(service)
            self.entry_service = self.services[entry_point_function_index]

        # Check if Prometheus setup is successful.
        if not self.env.setup_prometheus():
            print("[ERROR] Prometheus setup failed, please read error message and try again.")
            return 0

        # Check if benchmark setup is successful. If not, attempt to delete existing deployments.
        if not self.env.setup_functions(self.deployments, self.services):
            self.env.delete_deployments(self.deployments)
            print("[ERROR] Benchmark setup failed, please read error message and try again.")
            return 0

        # Load and parse RL configs from JSON file.
        with open(rl_configs_json, 'r') as f:
            rl_json_data = json.load(f)
        self.n_runs = rl_json_data['n-runs']
        self.min_scale = rl_json_data['min-scale']
        self.max_scale = rl_json_data['max-scale']
        self.actions = rl_json_data['actions']
        self.step_size = rl_json_data['step-size']
        self.steps = rl_json_data['steps']

        # Instantiate RL agent.
        self.agent = EpsilonGreedyAgent(num_actions=len(self.actions))

    def get_steps(self):
        return self.steps
    
    # Scale the number of replicas given the action number.
    def take_action(self, action):
        action_val = self.actions[action]

        self.current_scale = self.deployments[0].deployment_object.spec.replicas

        if self.current_scale + action_val in range (self.min_scale, self.max_scale+self.step_size):
            self.env.scale_deployments(self.deployments, self.current_scale + action_val)

        # Invoke the entry point Service.
        (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename = \
            self.env.invoke_service(self.entry_service)

        # Sample Env.
        env_state = self.env.sample_env()

        # Get latencies.
        lat_stat = self.env.get_latencies(stat_lat_filename)
        lat_stat.sort()

        # Check if requests were completed.
        if len(lat_stat) == 0:
            assert False, '[ERROR] No latencies were collected. Perhaps try using a smaller RPS value if this problem persists.\n'
        
        # Print statistics.
        print("[INFO] Invocation statistics:\n")
        print(
            f'    stat: {stat_issued}, {stat_completed}, {stat_real_rps}, {stat_target_rps}, latency file: {stat_lat_filename}')
        print('    50th: ', lat_stat[(int)(len(lat_stat) * 0.5)])
        print('    90th: ', lat_stat[(int)(len(lat_stat) * 0.90)])
        print('    99th: ', lat_stat[(int)(len(lat_stat) * 0.99)])
        print('    99.9th: ', lat_stat[(int)(len(lat_stat) * 0.999)])
        print('    env_state:')
        pprint(env_state)

        # Calculate metrics.
        rps_delta = np.abs(stat_real_rps - stat_target_rps)
        rps_ratio = rps_delta / stat_target_rps
        avg_cpu_usage = np.mean([env_state[i]['cpu'][1] for i in range(1, len(env_state)+1)])
        tail_lat = lat_stat[(int)(len(lat_stat) * 0.99)]
        QOS_LAT = 100000
        lat_ratio = tail_lat / QOS_LAT

        # Return values for calculating reward and for updating state.
        return (lat_ratio, avg_cpu_usage) 
    
    # Delete all deployments.
    def delete_deployments(self):
        self.env.delete_deployments(self.deployments)
    
def main(args):
    rl_env = RLEnv(args.config, args.rlconfig)
    wandb.init(project="k8s-rl-serverless", config={"benchmark" : rl_env.entry_service.service_name})
    logs = bandit_sweep([rl_env.agent], rl_env, ['Epsilon Greedy Agent'], n_runs=1, max_steps=rl_env.get_steps())
    wandb.finish()
    rl_env.delete_deployments()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--config')
    parser.add_argument('--rlconfig')
    args = parser.parse_args()

    main(args)
