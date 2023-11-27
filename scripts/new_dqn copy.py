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

steps_done = 0

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
    # Duration to run each benchmark
    episode_duration = int(args.d)
    # Initialize Envs
    env_shim = Env(verbose=True)
    # Setup Prometheus and check if setup is successful.
    if not env_shim.setup_prometheus():
        print("[ERROR] Prometheus setup failed, please read error message and try again.")
        return 0
    
    if args.config == 'dqn_configs.json':
        print("Using dqn_configs benchmarks...")
        with open(args.config, 'r') as f:
            json_data = json.load(f)
            benchmarks = json_data['benchmarks']
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
                manifests = [new_dep, new_svc, new_hpa]
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
        bm_objects_set = [bm_objects]
        
    elif args.config == 'eval_configs.json':
        print("Using eval_configs benchmarks...")
        with open(args.config, 'r') as f:
            json_data = json.load(f)
            benchmarks = json_data['benchmarks']
        # List of all Benchmark objects
        bm_objects_set = []
        # Create manifests and objects.
        for k in range(len(benchmarks[0]['rps-vals'])):
            bm_objects = []
            for benchmark in benchmarks:
                deployments, services = [], []
                benchmark_name = benchmark['name']
                functions = benchmark['functions']
                entry_point_function = benchmark['entry-point']
                entry_point_function_index = functions.index(entry_point_function)            
                sla = benchmark['sla']
                rps_vals = benchmark['rps-vals']
                for i in range(len(functions)):
                    rand_id = ''.join(random.choices(string.ascii_lowercase, k=10))
                    benchmark_name += '-' + rand_id
                    # Read YAML of original function to get dicts.
                    file_name = f"k8s-yamls/{functions[i]}.yaml"
                    with open(path.join(path.dirname(__file__), file_name)) as f:
                        dep, svc, hpa = yaml.load_all(f, Loader=SafeLoader)
                    # Update function to include new id.
                    new_funct = functions[i] + '-' + rand_id
                    # Update the old dict to include new id.
                    new_dep, new_svc, new_hpa = rename_yaml(dep, svc, hpa, new_funct)
                    # List of manifests as dicts to be converted into new YAML file.
                    manifests = [new_dep, new_svc, new_hpa]
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
                rps_range = (rps_vals[k], rps_vals[k])
                bm_object = Benchmark(benchmark_name, deployments, services, entry_point_function_index, sla, rps_range)
                bm_objects.append(bm_object)
            bm_objects_set.append(bm_objects)
    else:
        print("Using saved training benchmarks...")
        with open('train_benchmark.pickle', 'r') as handle:
            bm_objects_set = pickle.load(handle)
            
    timestep = int(args.t)
    # Action space is cartesian product of the three possible scaling decisions for three functions
    action_space = ActionSpace([[0,0,0]])
    
    run_id = ''.join(random.choices(string.ascii_lowercase, k=6))
    # Get number of actions from action space
    n_actions = action_space.n
    # Get number of observations from state space.
    n_observations = 5 + len(bm_objects_set[0])

    policy_net = DQN(n_observations, n_actions).to(device)
    target_net = DQN(n_observations, n_actions).to(device)
    target_net.load_state_dict(policy_net.state_dict())

    optimizer = optim.AdamW(policy_net.parameters(), lr=LR, amsgrad=True)
    memory = ReplayMemory(10000)
        
    # Initialize wandb logging.
    wandb.init(project='serverless-dqn')
    
    num_episodes = len(bm_objects_set)
    ### Iterate through training episodes.
    for i_episode in range(num_episodes):
        bm_objects = bm_objects_set[i]
        # Initialize KubernetesEnv
        k8s_env = KubernetesEnv(env_shim, bm_objects)
        rl_env = RLEnv(action_space, k8s_env, timestep)
        rl_env.rand_id = run_id
        # Simultaneously deploy all benchmarks.
        processes = []
        for bm in bm_objects:
            p = Process(target=deploy_benchmark, args=(bm, env_shim))
            processes.append(p)
            p.start()
        for proc in processes:
            proc.join()
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
            if total_time >= episode_duration:
                break
            if done:
                episode_durations.append(t + 1)
                plot_durations(run_id)
                break
            if t == 149:
                # plot_durations()
                break
        print('Episode finished.')
        print(f'Total Invoke Failures: {k8s_env.total_invoke_failures}\n')
        cleanup(delete_manifests=False)

    print('Done.')
    print(f'Total Invoke Failures: {k8s_env.total_invoke_failures}\n')
    print(f'Saving models to saved_models/{run_id}...')
    # Save Replay Buffer, policy net, and target net.
    make_dir(f'saved_models/{run_id}')
    target = f'saved_models/{run_id}/target_net.pth'
    policy = f'saved_models/{run_id}/policy_net.pth'
    buffer = f'saved_models/{run_id}/replay_buffer.pickle'
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
    parser.add_argument('--config', default='train_benchmarks.pickle')
    parser.add_argument('-t')
    parser.add_argument('-d')
    args = parser.parse_args()
    main(args)
