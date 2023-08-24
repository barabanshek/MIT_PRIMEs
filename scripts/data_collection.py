import argparse
import yaml
import json
import time
import random

from multiprocessing import Process, Array, Lock
from subprocess import run
from yaml.loader import SafeLoader
from os import path
from k8s_env_shim import Env
from pprint import pprint
from setup_service import Service
from setup_deployment import Deployment

lock = Lock()

global current_benchmarks
current_benchmarks = {}

# Check if the services for a benchmark have already been deployed.
def benchmark_already_deployed(benchmark_name):
    return benchmark_name in current_benchmarks and current_benchmarks[benchmark_name]
    # rets = [run(f"kubectl get service/{service.service_name}", capture_output=True, shell=True).returncode for service in services]
    # return sum(rets) == 0

# Randomly generate a subset of available benchmarks to run at random RPS and duration.
def generate_workload(benchmarks):
    workload = []
    size = random.choice(range(0, len(benchmarks)+1))
    subset = random.sample(benchmarks, size)
    for benchmark in subset:
        rps = random.randint(benchmark['invoker-configs']['rps-min'], benchmark['invoker-configs']['rps-max'])
        duration = random.randint(benchmark['invoker-configs']['duration-min'], benchmark['invoker-configs']['duration-max'])
        workload.append((benchmark, rps, duration))
    return workload

# Print the Env state nicely.
def print_env_state(env_state):
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

# Setup the benchmark, invoke, print stats, and delete service.
# This function will be multithreaded to run several benchmarks concurrently.
def run_service(env, benchmark_name, deployments, services, entry_service, rps, duration):
    # Check if the benchmark already exists. If not, deploy. If so, skip deployment.
    # Check if benchmark setup is successful. If not, attempt to delete existing deployments.
    # TODO: deploy only the services that the benchmark is missing. For example, if streaming and decoder are ready, deploy recog only.
    if not env.setup_functions(deployments, services):
        current_benchmarks[benchmark_name] = 0
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
    print(f"[INFO] Invocation statistics for benchmark `{benchmark_name}`:\n")
    lat_stat.sort()
    print(
        f'    stat: {stat_issued}, {stat_completed}, {stat_real_rps}, {stat_target_rps}, latency file: {stat_lat_filename}')
    print('    50th: ', lat_stat[(int)(len(lat_stat) * 0.5)]/1000, 'ms')
    print('    90th: ', lat_stat[(int)(len(lat_stat) * 0.90)]/1000, 'ms')
    print('    99th: ', lat_stat[(int)(len(lat_stat) * 0.99)]/1000, 'ms')
    print('    99.9th: ', lat_stat[(int)(len(lat_stat) * 0.999)]/1000, 'ms')
    print('    env_state:')
    print_env_state(env_state)

    # Delete when finished.
    current_benchmarks[benchmark_name] = 0
    env.delete_functions(services)

def main(args):
    # Instantiate Env.
    env = Env()

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
    while time.time() - t_start < 30:
        # Generate a list of random (benchmark, rps, duration) values
        workload = generate_workload(benchmarks)

        for benchmark, rps, duration in workload:
            benchmark_name = benchmark['name']
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
            print("[INFO] Current benchmark statuses:")
            # Sort current benchmark statuses
            pprint({k: v for k, v in sorted(current_benchmarks.items(), key=lambda item: item[1], reverse=True)})
            with lock:
                if benchmark_already_deployed(benchmark_name):
                    print(f"[INFO] Dropped proposed benchmark {benchmark_name} because it is already running.")
                    continue
            
            # If benchmark can be deployed, create and start process for multiprocessing.
            p = Process(target=run_service, args=(env, benchmark_name, deployments, services, entry_service, rps, duration))
            current_benchmarks[benchmark_name] = 1
            print(f"[INFO] Process for benchmark `{benchmark_name}` created.\n")
            p.start()
            processes.append(p)
        time.sleep(5)

# Once all processes have finished, they can be joined.
    for p in processes:
        p.join()
    
    print("[INFO] Done!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--config')
    args = parser.parse_args()
    main(args)