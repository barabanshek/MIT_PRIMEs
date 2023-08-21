import argparse
import yaml
import json
from multiprocessing import Process

from yaml.loader import SafeLoader
from os import path
from k8s_env_shim import Env
from pprint import pprint
from setup_service import Service
from setup_deployment import Deployment

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
def run_service(env, benchmark_name, deployments, services, entry_service, invoker_configs):
    # Check if benchmark setup is successful. If not, attempt to delete existing deployments.
    if not env.setup_functions(deployments, services):
        env.delete_functions(services)
        print(f"[ERROR] Benchmark `{benchmark_name}` setup failed, please read error message and try again.")
        return 0
    # Get invoker configs.
    duration = invoker_configs['duration']
    rps = invoker_configs['rps']
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

    for benchmark in benchmarks:
        # Read configs for benchmark
        benchmark_name = benchmark['name']
        entry_point_function = benchmark['entry-point']
        functions = benchmark['functions']
        invoker_configs = benchmark['invoker-configs']
        entry_point_function_index = functions.index(entry_point_function)

        # Instantiate Deployments and Services
        deployments = []
        services = []
        for function in functions:
            # Instantiate Deployment objects
            file_name = f"k8s-yamls/{function}.yaml"
            with open(path.join(path.dirname(__file__), file_name)) as f:
                dep, svc = yaml.load_all(f, Loader=SafeLoader)
            deployment = Deployment(dep, env.api)
            deployments.append(deployment)

            # Instantiate Service objects
            port = svc['spec']['ports'][0]['port']
            service = Service(function, file_name, port)
            services.append(service)
        entry_service = services[entry_point_function_index]

        # Create and start process for multiprocessing.
        p = Process(target=run_service, args=(env, benchmark_name, deployments, services, entry_service, invoker_configs))
        print(f"[INFO] Process for benchmark `{benchmark_name}` created.\n")
        p.start()
        processes.append(p)
    
    # Once all processes have finished, they can be joined.
    for p in processes:
        p.join()
    
    print("[INFO] Done!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--config')
    args = parser.parse_args()
    main(args)