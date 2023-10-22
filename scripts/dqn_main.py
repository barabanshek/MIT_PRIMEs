### Source: https://pytorch.org/tutorials/intermediate/reinforcement_q_learning.html

### Setup
import math
import random
import matplotlib
import matplotlib.pyplot as plt
import wandb
from collections import namedtuple, deque
from itertools import count, product
from multiprocessing import Process, Manager
from RLEnv import RLEnv, ActionSpace
from KubernetesEnv import KubernetesEnv, Benchmark
from data_collection import make_dir, rename_yaml, delete_files_in_directory

import json
import yaml
import string
import argparse
import time
import pickle
from subprocess import run
from yaml.loader import SafeLoader
from os import path
from k8s_env_shim import Env
from pprint import pprint
from setup_service import Service
from setup_deployment import Deployment

import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F

plt.ion()

# if GPU available, use GPU
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

### Experience Replay
Transition = namedtuple('Transition', ('state', 'action', 'next_state', 'reward'))

class ReplayMemory(object):
    
    def __init__(self, capacity):
        self.memory = deque([], maxlen=capacity)
    
    def push(self, *args):
        """Save a transition"""
        self.memory.append(Transition(*args))
        
    def sample(self, batch_size):
        return random.sample(self.memory, batch_size)
    
    def __len__(self):
        return len(self.memory)

### Q-network
class DQN(nn.Module):
    
    def __init__(self, n_observations, n_actions):
        super(DQN, self).__init__()
        self.layer1 = nn.Linear(n_observations, 128)
        self.layer2 = nn.Linear(128, 128)
        self.layer3 = nn.Linear(128, n_actions)
        
    # Called with either one element to determine next action, or a batch
    # during optimization. Returns tensor([[left0exp,right0exp]...]).
    def forward(self, x):
        x = F.relu(self.layer1(x))
        x = F.relu(self.layer2(x))
        return self.layer3(x)

### Training

# BATCH_SIZE is the number of transitions sampled from the replay buffer
# GAMMA is the discount factor as mentioned in the previous section
# EPS_START is the starting value of epsilon
# EPS_END is the final value of epsilon
# EPS_DECAY controls the rate of exponential decay of epsilon, higher means a slower decay
# TAU is the update rate of the target network
# LR is the learning rate of the ``AdamW`` optimizer
BATCH_SIZE = 8
GAMMA = 0.99
EPS_START = 0.9
EPS_END = 0.05
EPS_DECAY = 150
TAU = 0.005
LR = 1e-4

steps_done = 0

def select_action(state, policy_net, rl_env):
    global steps_done
    sample = random.random()
    # Desmos format: 0.05+(0.9-0.05)*e^{(-1*x/1000)}
    eps_threshold = EPS_END + (EPS_START - EPS_END) * \
        math.exp(-1. * steps_done / EPS_DECAY)
    steps_done += 1
    if sample > eps_threshold:
        with torch.no_grad():
            # t.max(1) will return the largest column value of each row.
            # second column on max result is index of where max element was
            # found, so we pick action with the larger expected reward.
            # Get the action that returns the highest Q value.
            print(f'Taking BEST action (epsilon={round(eps_threshold, 3)})...')
            return policy_net(state).max(1)[1].view(1, 1)
    else:
        print(f'Taking RANDOM action (epsilon={round(eps_threshold, 3)})...')
        return torch.tensor([[rl_env.action_space.sample()]], device=device, dtype=torch.long)
    
episode_durations = []

def plot_avg_times(id, avg_times):
    plt.figure(1)
    plt.title('Average time per timestep')
    plt.xlabel('Timestep')
    plt.ylabel('Duration')
    plt.plot(avg_times)
    plt.pause(0.001)
    plt.savefig(f'avg-times-{id}.png')

def plot_durations(id, show_result=False):
    plt.figure(1)
    durations_t = torch.tensor(episode_durations, dtype=torch.float)
    if show_result:
        plt.title('Result')
    else:
        plt.clf()
        plt.title('Training...')
    plt.xlabel('Episode')
    plt.ylabel('Duration')
    plt.plot(durations_t.numpy())
    # Take 100 episode averages and plot them too
    if len(durations_t) >= 100:
        means = durations_t.unfold(0, 100, 1).mean(1).view(-1)
        means = torch.cat((torch.zeros(99), means))
        plt.plot(means.numpy())
    
    plt.pause(0.001) # pause a bit so that plots are updated
    plt.savefig(f'plot-durations-{id}.png')

### Training loop

def optimize_model(memory, policy_net, target_net, optimizer):
    if len(memory) < BATCH_SIZE:
        return
    transitions = memory.sample(BATCH_SIZE)
    # Transpose the batch (see https://stackoverflow.com/a/19343/3343043 for
    # detailed explanation). This converts batch-array of Transitions 
    # to Transition of batch-arrays.
    batch = Transition(*zip(*transitions))
    
    # Compute a mask of non-final states and concatenate the batch elements
    # (a final state would've been the one after which simulation ended)
    non_final_mask = torch.tensor(tuple(map(lambda s: s is not None,
                                            batch.next_state)), device=device, dtype=torch.bool)
    non_final_next_states = torch.cat([s for s in batch.next_state if s is not None])
    state_batch = torch.cat(batch.state)
    action_batch = torch.cat(batch.action)
    reward_batch = torch.cat(batch.reward)
    
    # Compute Q(s_t, a) - the model computes Q(s_t), then we select the 
    # columns of actions taken. These are the actions which would've been taken
    # for each batch state according to policy_net
    state_action_values = policy_net(state_batch).gather(1, action_batch)
    
    # Compute V(s_{t+1}) for all next states.
    # Expected values of actions for non_final_next_states are computed based
    # on the "older" target_net; selecting their best reward with max(1)[0].
    # This is merged based on the mask, such that we'll have either the expected 
    # state value or 0 in case the state was final.
    next_state_values = torch.zeros(BATCH_SIZE, device=device)
    with torch.no_grad():
        next_state_values[non_final_mask] = target_net(non_final_next_states).max(1)[0]
    # Compute the expected Q values
    expected_state_action_values = (next_state_values * GAMMA) + reward_batch
    
    # Compute Huber loss
    criterion = nn.SmoothL1Loss()
    loss = criterion(state_action_values, expected_state_action_values.unsqueeze(1))
    
    # Optimize the model
    optimizer.zero_grad()
    loss.backward()
    # In-place gradient clipping
    torch.nn.utils.clip_grad_value_(policy_net.parameters(), 100)
    optimizer.step()
    
# Deploy a benchmark and return its Deployment and Service objects.
def deploy_benchmark(benchmark, env):
    if not env.setup_functions(benchmark.deployments, benchmark.services):
        env.delete_functions(benchmark.services)
        print(f"[ERROR] Benchmark `{benchmark.name}` setup failed, please read error message and try again.")
        return 0    

    print(f'Successfully created objects for benchmark {benchmark.name}.')

# Cleanup functions when done.
def cleanup(aggressive=False, delete_manifests=True):
    run('''kubectl delete deployment --all''', shell=True)
    run('''kubectl delete service --all''', shell=True)
    run('''kubectl delete hpa --all''', shell=True)
    if aggressive:
        run('''kubectl delete pods --all --grace-period=0 --force''', shell=True)
    run('''kubectl apply -f ~/vSwarm/benchmarks/hotel-app/yamls/knative/database.yaml''', shell=True)
    run('''kubectl apply -f ~/vSwarm/benchmarks/hotel-app/yamls/knative/memcached.yaml''', shell=True)
    if delete_manifests:
        delete_files_in_directory('./k8s-yamls/tmp/')
    run('''find . -name 'rps*.csv' -delete''', shell=True)
    print('Deleted all latency files.')

# TODO (Nikita): this function still needs a lot of work.
def wandb_log(log_data):
    def truncate_name(name):
        if "hotel-app-profile" in name:
            return "hotel-app-profile"
        if "hotel-app-geo" in name:
            return "hotel-app-geo"
        if "fibonacci-python" in name:
            return "fibonacci-python"

    lats_dict = dict(
            (truncate_name(lat_f), {
                '50th': lat_v[0],
                '90th': lat_v[1],
                '99th': lat_v[2],
                '99.9th': lat_v[3],
            }) for (lat_f, lat_v) in log_data['lats'].items()
        )

    wandb.log({
        "reward": log_data['reward'],
        "QoS": lats_dict,
        "Observations": {
            "cpu": log_data['observation:cpu'],
            "mem_free": log_data['observation:mem_free'],
            "net_transmit": log_data['observation:net_transmit'],
            "net_receive": log_data['observation:net_receive'],
        },
        "Containers": {
            "fn1": log_data['num_containers'][0],
            "fn2": log_data['num_containers'][1],
            "fn3": log_data['num_containers'][2]
        },
        "RPS": log_data['rps'],
        "Episode": log_data['episode']
    })

def save_replay_buffer(replay_buffer, filename):
    with open(filename, 'wb') as f:
        pickle.dump(replay_buffer, f)

def main(args):
    # Manually configure RPS values for now.
    RPS_VALS = random.sample(range(100, 1000), int(args.e))
    with open(args.config, 'r') as f:
        json_data = json.load(f)
        benchmarks = json_data['benchmarks']
    # Initialize Envs
    env_shim = Env(verbose=True)
    # Setup Prometheus and check if setup is successful.
    if not env_shim.setup_prometheus():
        print("[ERROR] Prometheus setup failed, please read error message and try again.")
        return 0
    # List of all Benchmark objects
    bm_objects = []
    # Create manifests and objects.
    for benchmark in benchmarks:
        deployments, services = [], []
        benchmark_name = benchmark['name']
        rand_id = ''.join(random.choices(string.ascii_lowercase, k=10))
        benchmark_name += '-' + rand_id
        functions = benchmark['functions']
        entry_point_function = benchmark['entry-point']
        entry_point_function_index = functions.index(entry_point_function)            
        sla = benchmark['sla']
        rps_range = (benchmark['rps-min'], benchmark['rps-max'])
        for i in range(len(functions)):
            # Read YAML of original function to get dicts.
            file_name = f"k8s-yamls/{functions[i]}.yaml"
            with open(path.join(path.dirname(__file__), file_name)) as f:
                dep, svc, hpa = yaml.load_all(f, Loader=SafeLoader)
            # Update function to include new id.
            new_funct = functions[i] + '-' + rand_id
            # Update the old dict to include new id.
            new_dep, new_svc, new_hpa = rename_yaml(dep, svc, hpa, new_funct)
            # List of manifests as dicts to be converted into new YAML file.
            manifests = [new_dep, new_svc]
            # Update file name
            make_dir('k8s-yamls/tmp')
            file_name = f"k8s-yamls/tmp/{new_funct}.yaml"
            # Dump manifests into new YAML file.
            with open(file_name, 'x') as f:
                yaml.dump_all(manifests, f)
            # Instantiate Service objects
            port = new_svc['spec']['ports'][0]['port']
            service = Service(new_funct, file_name, port)
            # Instantiate Deployment objects
            deployment = Deployment(new_dep, env_shim.api)
            # Update deployments and services
            deployments.append(deployment)
            services.append(service)
        bm_object = Benchmark(benchmark_name, deployments, services, entry_point_function_index, sla, rps_range)
        bm_objects.append(bm_object)
    # Initialize KubernetesEnv
    k8s_env = KubernetesEnv(env_shim, bm_objects)
    timestep = int(args.t)
    # Action space is cartesian product of the three possible scaling decisions for three functions
    action_space = ActionSpace(list(product([-1, 0, 1], repeat=len(benchmarks))))
    # Initialize RL Env.
    rl_env = RLEnv(action_space, k8s_env, timestep)
    run_id = rl_env.rand_id
    # Initialize state.
    init_state = rl_env.compute_state()
    # Get number of actions from action space
    n_actions = action_space.n
    # Get number of observations from state space.
    n_observations = len(init_state)

    policy_net = DQN(n_observations, n_actions).to(device)
    target_net = DQN(n_observations, n_actions).to(device)
    target_net.load_state_dict(policy_net.state_dict())

    optimizer = optim.AdamW(policy_net.parameters(), lr=LR, amsgrad=True)
    memory = ReplayMemory(10000)
        
    if torch.cuda.is_available():
        num_episodes = len(RPS_VALS)
    else:
        num_episodes = len(RPS_VALS)
    # Initialize wandb logging.
    wandb.init(project='serverless-dqn')
    
    ### Iterate through training episodes.
    for i_episode in range(num_episodes):
        rps = RPS_VALS[i_episode]
        print(f'\n>>> Running episode {i_episode + 1} with {rps} RPS.\n')
        # Simultaneously deploy all benchmarks.
        processes = []
        for bm in bm_objects:
            p = Process(target=deploy_benchmark, args=(bm, env_shim))
            processes.append(p)
            p.start()
        for proc in processes:
            proc.join()
        # Update RPS for all benchmarks.
        for idx, bm in enumerate(bm_objects):
            bm.rps = rps
            bm_objects[idx] = bm
        # Update KubernetesEnv with new Benchmark objects..
        k8s_env.benchmarks = bm_objects
        # Update RLEnv.
        rl_env.k8s_env = k8s_env
        # Keep trying to reset state.
        for c in count():
            try:
                # Reset state.
                print(f'Reseting state for new episode, attempt {c+1}.\n')
                state = rl_env.reset()
            except Exception as e:
                print(f'>>> Error: {e}')
                print('>>> Retrying...')
            else:
                print('>>> Env reset success.')
                break
        # state is of the form tensor([[cpu, mem, net_transmit, net_receive, n_containers]])
        state = torch.tensor(state, dtype=torch.float32, device=device).unsqueeze(0)
        avg_step_times = []
        t_start = time.time()
        for t in count():
            print(f'>>> Timestep: {t}')
            # action is of the form tensor[[action_i]]
            action = select_action(state, policy_net, rl_env)
            observation, reward, terminated, truncated, lats = rl_env.step(action.item())
            reward = torch.tensor([reward], device=device)
            done = terminated or truncated
            rl_env.save_step(i_episode, t+1, action.item(), lats)
            cpu, mem_free, net_transmit, net_receive, n_containers, rps_ = observation

            # Log things.
            log_data = {}
            log_data['episode'] = i_episode + 1
            log_data['reward'] = reward
            log_data['lats'] = lats
            log_data['observation:cpu'] = cpu
            log_data['observation:mem_free'] = mem_free
            log_data['observation:net_transmit'] = net_transmit
            log_data['observation:net_receive'] = net_receive
            log_data['num_containers'] = [benchmark.replicas for benchmark in k8s_env.benchmarks]
            log_data['rps'] = rps_
            wandb_log(log_data)

            if terminated:
                next_state = None
            else:
                next_state = torch.tensor(observation, dtype=torch.float32, device=device).unsqueeze(0)
                
            # Store the transition in memory
            memory.push(state, action, next_state, reward)
            
            # Move to the next state
            state = next_state
            
            # Perform one step of the optimization (on the policy network)
            optimize_model(memory, policy_net, target_net, optimizer)
            
            # Soft update of the target network's weights
            # θ′ ← τ θ + (1 −τ )θ′
            target_net_state_dict = target_net.state_dict()
            policy_net_state_dict = policy_net.state_dict()
            for key in policy_net_state_dict:
                target_net_state_dict[key] = policy_net_state_dict[key] * TAU + target_net_state_dict[key] * (1-TAU)
            target_net.load_state_dict(target_net_state_dict)
            total_time = time.time() - t_start
            avg_time = total_time/(t+1)
            print(f'Average time per step so far: {round(avg_time, 4)} seconds.')
            avg_step_times.append(avg_time)
            plot_avg_times(run_id, avg_step_times)
            if done:
                episode_durations.append(t + 1)
                plot_durations(run_id)
                break
            # if t == 149:
            #     plot_durations()
            #     break
        print('Episode finished.')
        print(f'Total Invoke Failures: {k8s_env.total_invoke_failures}\n')
        cleanup(delete_manifests=False)

    print('Done.')
    print(f'Total Invoke Failures: {k8s_env.total_invoke_failures}\n')
    print(f'Saving models to saved_models/{run_id}...')
    # Save Replay Buffer, policy net, and target net.
    make_dir(f'saved_models/{run_id}')
    target = f'saved_models/{rl_env.rand_id}/target_net.pth'
    policy = f'saved_models/{rl_env.rand_id}/policy_net.pth'
    buffer = f'saved_models/{rl_env.rand_id}/replay_buffer.pickle'
    target_scripted = torch.jit.script(target_net)
    target_scripted.save(target)
    policy_scripted = torch.jit.script(policy_net)
    policy_scripted.save(policy)
    save_replay_buffer(memory, buffer)
    cleanup()
    plot_durations(run_id, show_result=True)
    plt.ioff()
if __name__ == "__main__":
    # Config file for benchmarks
    parser = argparse.ArgumentParser()
    parser.add_argument('--config')
    parser.add_argument('-t')
    parser.add_argument('-e')
    args = parser.parse_args()
    main(args)
