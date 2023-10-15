import math
import random
import matplotlib
import numpy as np
import pickle
import string
from multiprocessing import Manager, Process
from KubernetesEnv import KubernetesEnv
from subprocess import run
from itertools import count
from data_processing import make_dir
# Computes instantaneous reward given latencies Dict and SLAs for functions
# Returns: float representing instant reward
# latencies : Dict{'fibonacci-ID' : (50th, 90th, 99th, 99.9th), 'hotel-app-geo-ID' : ...}
# benchmarks: List[Benchmark] : benchmark objects to use for SLA comparison.
def compute_reward(latencies, benchmarks):
    sum = 0
    for benchmark in benchmarks:
        benchmark_name = benchmark.name
        sla = benchmark.sla['lat'][1]
        actual = latencies[benchmark_name][1]
        # If SLA violation, return negative reward.
        if actual > sla:
            return -1
        # else, return % difference between actual and SLA
        diff = actual / sla
        sum += diff
    # Get average of the % differences for each function
    avg_lat = sum/len(latencies)
    # Reward shaping
    return 1 - avg_lat ** 0.4

class ActionSpace():   
    """Object to represent an RL agent's action space.
    
    Attributes:
    - `n` - the number of available actions
    - `actions` - a List consisting of the available actions
    
    Methods:
    - `sample` - returns a random action from the action space
    
    """
    def __init__(self, actions):
        self.n = len(actions)
        self.actions = actions
        
    def sample(self):
        return random.choice(range(len(self.actions)))
        

class RLEnv():
    """Environment class for the RL agent.
    
    Attributes:
    - `action_space` - an ActionSpace object with the available actions
    - `state` - the current RL state.
    - `reward` - the instantaneous reward.
    - `terminated` - a boolean representing whether a terminal state has been reached
    - `truncated` - a boolean representing whether any truncation conditions have been satisified, e.g. time limit exceeded, etc.
    - `k8s_env` - the Kubernetes environment
    - `t` - the time-step size.
    Methods:
    - `reset` - re-initializes the environment and returns the initialized (state, info) tuple
    - 'step' - takes an Int representing an action, and takes that action in the environment. Returns typical RL stuff.
    - `compute_state` - computes the state by concatenating RPS values with env_state.
    """
    
    def __init__(self, action_space, k8s_env, t):
        self.action_space = action_space
        self.k8s_env = k8s_env
        self.t = t
        self.rand_id = ''.join(random.choices(string.ascii_lowercase, k=6))
        self.data = {'episode' : [],
                     'step' : [],
                     'cpu_util' : [],
                     'mem_free' : [],
                     'net_transmit' : [],
                     'net_receive': [],
                     'action' : [],
                     'reward' : [],
                     'mean_latency' : []}
        for benchmark in self.k8s_env.benchmarks:
            self.data[f'replicas_{benchmark.name}'] = []
    
    # Reset the env state.
    def reset(self):
        self.state = self.compute_state()
        # Scale all functions to 1 and set their replica count to 1.
        for idx, benchmark in enumerate(self.k8s_env.benchmarks):
            self.k8s_env.scale_with_action(1, benchmark)
            # Update replica count.
            benchmark.replicas = 1
            self.k8s_env.benchmarks[idx] = benchmark
        self.reward = 0
        self.terminated = False
        return self.state
    
    def compute_state(self):
        cpu_idle, cpu_user, cpu_system, mem_free, net_transmit, net_receive = self.k8s_env.get_env_state(self.t)[0]
        num_containers = sum([benchmark.replicas for benchmark in self.k8s_env.benchmarks])
        rps = self.k8s_env.benchmarks[0].rps
        env_state = np.array([cpu_user, mem_free, net_transmit, net_receive, num_containers, rps])
        return env_state
    
    def save_step(self, i_episode, step, action_i, lats):
        # Update data.
        self.data['episode'].append(i_episode)
        self.data['step'].append(step) 
        self.data['cpu_util'].append(self.state[0])
        self.data['mem_free'].append(self.state[1])
        self.data['net_transmit'].append(self.state[2])
        self.data['net_receive'].append(self.state[3])
        self.data['action'].append(self.action_space.actions[action_i])
        self.data['reward'].append(self.reward)
        self.data['mean_latency'].append(np.mean(list(lats.values())))
        for benchmark in self.k8s_env.benchmarks:
            self.data[f'replicas_{benchmark.name}'].append(benchmark.replicas)
        # Save file.
        foldername = f'./rl-data/'
        make_dir(foldername)
        filename = f'{foldername}/run-{self.rand_id}.pickle'
        with open(filename, 'wb') as handle:
            pickle.dump(self.data, handle, protocol=pickle.HIGHEST_PROTOCOL)
        print(f'Data saved in {filename}.')
        
    """Updates the RL environment at every time step.
    
    Args:
    - action_i (int) the index of the action to take.
    
    Returns:
    - state (np_array) : numpy array consisting of [node_cpu_util, node_mem_util, node_network_throughput, rps_target]
    - reward (float) : instanteous reward
    - terminated (bool) : whether the agent has reached a terminal state, e.g. OOM errors, etc.
    - truncated (bool) : whether any truncation conditions have been satisified, e.g. time limit exceeded, etc.
    """
    def step(self, action_i):
        # action_i represents the index of the action to take.
        # In this scenario, action will be a triplet of scaling actions 
        # for the three functions, e.g. (1, -1, 0).
        for c in count():
            try:
                print(f'>>> Attempt {c+1}')
                action = self.action_space.actions[action_i]
                lats = self.k8s_env.evaluate_action(action, self.t)
                # Compute state.
                self.state = self.compute_state()
                # Compute reward.
                self.reward = compute_reward(lats, self.k8s_env.benchmarks)
                self.terminated = self.k8s_env.check_termination()
                self.truncated = self.k8s_env.check_truncation()
            except Exception as e:
                print(f'>>> Error: {e}')
                print('>>> Retrying...')
            else:
                print('>>> Success.')
                break
        # Delete latency files to prevent buildup
        run('''find . -name 'rps*.csv' -delete''', shell=True)
        print('Deleted all latency files.')
        
        return (self.state, self.reward, self.terminated, self.truncated, lats)
    
    
