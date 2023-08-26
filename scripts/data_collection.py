import argparse
import yaml
import json
import time
import random
import pandas as pd
import pickle
import numpy as np

from multiprocessing import Process, Array, Lock, Manager
from subprocess import run
from yaml.loader import SafeLoader
from os import path
from k8s_env_shim import Env
from pprint import pprint
from itertools import chain, combinations
from setup_service import Service
from setup_deployment import Deployment


class DataCollect:

    def __init__(self, data, current_benchmarks, verbose=False):
        self.data = data
        self.current_benchmarks = current_benchmarks
        self.lock = Lock()
        self.verbose = verbose

    # Check if the services for a benchmark have already been deployed.
    def benchmark_already_deployed(self, benchmark_name):
        return benchmark_name in self.current_benchmarks and self.current_benchmarks[benchmark_name]

    # Randomly generate a subset of available benchmarks to run at random RPS and duration.
    def generate_workload(self, benchmarks):
        workload = []
        subsets = list(chain.from_iterable(combinations(benchmarks, r) for r in range(len(benchmarks)+1)))
        subset = random.choice(subsets)
        for benchmark in subset:
            rps = random.randint(benchmark['invoker-configs']['rps-min'], benchmark['invoker-configs']['rps-max'])
            duration = random.randint(benchmark['invoker-configs']['duration-min'], benchmark['invoker-configs']['duration-max'])
            workload.append((benchmark, rps, duration))
        return workload

    # Unpack Env state.
    def unpack_env_state(self, env_state):
        ret = []
        for k in env_state.keys():
            cpu_idle = env_state[k]['cpu'][0]
            cpu_user = env_state[k]['cpu'][1]
            cpu_system = env_state[k]['cpu'][2]
            mem_free = env_state[k]['mem']
            net_transmit = env_state[k]['net'][0]
            net_receive = env_state[k]['net'][1]
            ret.append((cpu_idle, cpu_user, cpu_system, mem_free, net_transmit, net_receive))
        return ret
    
    # Print the Env state nicely.
    def print_env_state(self, env_state):
        for k in env_state.keys():
            print(f"        Node {k}:")
            print("            CPU Usage:")
            print(f"                Idle: {round(100*env_state[k]['cpu'][0], 6)} %")
            print(f"                User: {round(100*env_state[k]['cpu'][1], 6)} %")
            print(f"                System: {round(100*env_state[k]['cpu'][2], 6)} %")
            print("            Memory Usage:")
            print(f"                Free: {round(100*env_state[k]['mem'], 6)} %")
            print("            Network Throughput (bps):")
            print(f"                Transmit: {env_state[k]['net'][0]}")
            print(f"                Receive: {env_state[k]['net'][1]}")

    # Stop the Horizontal Pod Autoscaler from scaling.
    def freeze_autoscaler(self, name, replicas):
        # Set minReplicas and maxReplicas equal to the given replicas
        set_scale_cmd = '''kubectl patch hpa ''' + name + ''' --patch '{"spec":{"maxReplicas":''' + str(replicas) + '''}}'\n
                kubectl patch hpa ''' + name + ''' --patch '{"spec":{"minReplicas":''' + str(replicas) + '''}}' '''
        ret = run(set_scale_cmd, capture_output=True, shell=True, universal_newlines=True)
        if ret.returncode != 0:
            assert False, f"\n[ERROR] Failed to run command `{set_scale_cmd}`\n[ERROR] Error message: {ret.stderr}"

    # Setup the benchmark, invoke, print stats, and delete service.
    # This function will be multithreaded to run several benchmarks concurrently.
    def run_service(self, env, benchmark_name, deployments, services, entry_service, rps, duration):
        # Check if the benchmark already exists. If not, deploy. If so, skip deployment.
        # Check if benchmark setup is successful. If not, attempt to delete existing deployments.
        # TODO: deploy only the services that the benchmark is missing. For example, if streaming and decoder are ready, deploy recog only.
        if not env.setup_functions(deployments, services):
            self.current_benchmarks[benchmark_name] = 0
            env.delete_functions(services)
            print(f"[ERROR] Benchmark `{benchmark_name}` setup failed, please read error message and try again.")
            return 0
        # Invoke.
        (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename = \
            env.invoke_service(entry_service, duration, rps)
        lat_stat = env.get_latencies(stat_lat_filename)
        if lat_stat == []:
            print(f"[ERROR] No responses were returned for benchmark `{benchmark_name}`, so no latency statistics have been computed.")
            return
        
        # Sample env.
        env_state = env.sample_env(duration)

        # Print statistics.
        lat_stat.sort()
        lat_50 = lat_stat[(int)(len(lat_stat) * 0.5)]
        lat_90 = lat_stat[(int)(len(lat_stat) * 0.90)]
        lat_99 = lat_stat[(int)(len(lat_stat) * 0.99)]
        lat_999 = lat_stat[(int)(len(lat_stat) * 0.999)]

        unpacked_env_state = self.unpack_env_state(env_state)
        num_nodes = len(unpacked_env_state)
        avgs = np.zeros(len(unpacked_env_state[0]))

        for i in range(num_nodes):
            avgs = np.add(avgs, np.array(unpacked_env_state[i])/num_nodes)
                    
        cpu_idle, cpu_user, cpu_system, mem_free, net_transmit, net_receive = avgs

        if self.verbose:
            print(f"[INFO] Invocation statistics for benchmark `{benchmark_name}`:\n")
            print(
                f'    stat: {stat_issued}, {stat_completed}, {stat_real_rps}, {stat_target_rps}, latency file: {stat_lat_filename}')
            print('    50th: ', lat_50/1000, 'ms')
            print('    90th: ', lat_90/1000, 'ms')
            print('    99th: ', lat_99/1000, 'ms')
            print('    99.9th: ', lat_999/1000, 'ms')
            print('    env_state:')
            self.print_env_state(env_state)

        # Delete when finished.   
        env.delete_functions(services)
        self.current_benchmarks[benchmark_name] = 0
        # Update data table.
        with self.lock:
            self.data.append([benchmark_name, 
                              rps, 
                              duration, 
                              stat_issued, 
                              stat_completed, 
                              stat_real_rps, 
                              stat_target_rps, 
                              lat_50, lat_90, lat_99, lat_999,
                              cpu_idle, cpu_user, cpu_system,
                              mem_free,
                              net_transmit, net_receive])

def main(args):
    with Manager() as manager:
        # Initialize shared variables
        data = manager.list()
        current_benchmarks = manager.dict()

        # Verbosity
        verbose = args.v == 't'

        # Instantiate Env.
        env = Env(verbose=verbose)

        # Instantiate DataCollect.
        dc = DataCollect(data, current_benchmarks, verbose=verbose)

        # Setup Prometheus and check if setup is successful.
        if not env.setup_prometheus():
            print("[ERROR] Prometheus setup failed, please read error message and try again.")
            return 0
        
        # Load and parse json config file.
        with open(args.config, 'r') as f:
            json_data = json.load(f)

        benchmarks = json_data['benchmarks']
        processes = []


        t_start = time.time()
        while time.time() - t_start < int(args.t):
            # Generate a list of random (benchmark, rps, duration) values
            workload = dc.generate_workload(benchmarks)

            for benchmark, rps, duration in workload:
                benchmark_name = benchmark['name']
                if verbose:
                    print(f"[INFO] Proposed incoming workload: {benchmark_name} at {rps} RPS for {duration} seconds.")
                functions = benchmark['functions']
                # Read configs for benchmark
                entry_point_function = benchmark['entry-point']
                entry_point_function_index = functions.index(entry_point_function)

                # Instantiate Services and Deployments
                services = []
                deployments = []
                for function in functions:
                    file_name = f"k8s-yamls/{function}.yaml"
                    # Instantiate Service objects
                    with open(path.join(path.dirname(__file__), file_name)) as f:
                        dep, svc = yaml.load_all(f, Loader=SafeLoader)
                    port = svc['spec']['ports'][0]['port']
                    service = Service(function, file_name, port)
                    services.append(service)

                    # Instantiate Deployment objects
                    deployment = Deployment(dep, env.api)
                    deployments.append(deployment)

                entry_service = services[entry_point_function_index]
                # Check if the benchmark has already been deployed. If so, ignore it.
                # print("[INFO] Current benchmark statuses:")
                # # Sort current benchmark statuses
                # pprint({k: v for k, v in sorted(dc.current_benchmarks.items(), key=lambda item: item[1], reverse=True)})
                if dc.benchmark_already_deployed(benchmark_name):
                    if verbose:
                        print(f"[INFO] Dropped proposed benchmark `{benchmark_name}` because it is already running.")
                    continue
                
                # If benchmark can be deployed, create and start process for multiprocessing.
                p = Process(target=dc.run_service, args=(env, benchmark_name, deployments, services, entry_service, rps, duration))
                dc.current_benchmarks[benchmark_name] = 1
                if verbose:
                    print(f"[INFO] Process for benchmark `{benchmark_name}` created.\n")
                p.start()
                processes.append(p)
            time.sleep(int(args.r))

        # Once all processes have finished, they can be joined.
        for p in processes:
            p.join()
        
        # Dump data in pickle file.
        with open('data.pickle', 'wb') as handle:
            pickle.dump(list(dc.data), handle, protocol=pickle.HIGHEST_PROTOCOL)
    print("[INFO] Done!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # Config file for benchmarks
    parser.add_argument('--config')
    # Total time to run (seconds)
    parser.add_argument('-t')
    # Rate at which to generate workloads (seconds)
    parser.add_argument('-r')
    # Verbosity: 't' for verbose, 'f' for non-verbose
    parser.add_argument('-v')
    args = parser.parse_args()
    main(args)