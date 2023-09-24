import argparse
import yaml
import json
import csv
from yaml.loader import SafeLoader
from os import path
from k8s_env_shim import Env
from pprint import pprint
from setup_service import Service
from setup_deployment import Deployment
import random
import numpy as np

def run_service(env, service, invoker_configs, func_name):
    # Get invoker configs.
    duration = invoker_configs['duration']
    rps = invoker_configs['rps']
    # Invoke.
    (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename = \
        env.invoke_service(service, duration, rps)
    lat_stat = env.get_latencies(stat_lat_filename)
    if lat_stat == []:
        print("[ERROR] No responses were returned, no latency statistics is computed.")
        return
    
    # Sample env.
    env_state = env.sample_env(duration)

    cpu_util = 0
    mem_free = 0
    for f in env_state:
        print(f)
        cpu_util += f['cpu'][1]
        mem_free += f['mem']

    cpu_util/=len(env_state)
    mem_free/=len(env_state)
    lat_stat.sort()

    with open("output.csv", "a", newline = '') as file:
            writer = csv.writer(file)
            writer.writerow([rps, duration, func_name, lat_stat[(int)(len(lat_stat) * 0.5)], lat_stat[(int)(len(lat_stat) * 0.90)], lat_stat[(int)(len(lat_stat) * 0.99)], cpu_util, mem_free, stat_issued/stat_completed])
            file.close()

def main(args):
    env = Env()

    with open(args.config, 'r') as f:
        json_data = json.load(f)
        
    entry_point_function = []
    functions = []
    invoker_configs = []
    for f in json_data["benchmarks"]:
        entry_point_function.append(f['entry-point'])
        functions.append(f['functions'][0])
        invoker_configs.append(f['invoker-configs'])

    # Load YAML files as JSON-formatted dictionaries
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

    # Check if Prometheus setup is successful.
    if not env.setup_prometheus():
        print("[ERROR] Prometheus setup failed, please read error message and try again.")
        return 0

    # Check if benchmark setup is successful. If not, attempt to delete existing deployments.
    if not env.setup_functions(deployments, services):
        env.delete_functions(services)
        print("[ERROR] Benchmark setup failed, please read error message and try again.")
        return 0
    
    with open("output.csv", "a", newline = '') as file:
            writer = csv.writer(file)
            writer.writerow(["rps", "duration", "service_name", "50%", "90%", "99%", "cpu_util", "mem_free", "complete_rate"])
            file.close()
    env.scale_deployments(deployments, 1)
    cpus = [str(x) + "m" for x in range (40, 1040, 40)]
    memorys = [str(x) + "Mi" for x in range(100, 4100, 100)]

    for h in range(len(services)):
        for k in range(5):
            duration = random.randint(invoker_configs[h]["duration"][0], invoker_configs[h]["duration"][1])
            rps = random.randint(invoker_configs[h]["rps"][0], invoker_configs[h]["rps"][1])
            for i in cpus:
                for j in memorys:
                    env.scale_pods([deployments[h]], i, j)
                    run_service(env, services[h], {"duration": duration, "rps": rps}, entry_point_function[h])

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--config')
    args = parser.parse_args()
    main(args)