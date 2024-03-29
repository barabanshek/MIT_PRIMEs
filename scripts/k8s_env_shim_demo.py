import argparse
import yaml
import json

from yaml.loader import SafeLoader
from os import path
from k8s_env_shim import Env
from pprint import pprint
from setup_service import Service
from setup_deployment import Deployment

# Run the benchmark and print stats
def run_service(env, service, invoker_configs):
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

    # Print statistics.
    print("[INFO] Invocation statistics:\n")
    lat_stat.sort()
    print(
        f'    stat: {stat_issued}, {stat_completed}, {stat_real_rps}, {stat_target_rps}, latency file: {stat_lat_filename}')
    print('    50th: ', lat_stat[(int)(len(lat_stat) * 0.5)])
    print('    90th: ', lat_stat[(int)(len(lat_stat) * 0.90)])
    print('    99th: ', lat_stat[(int)(len(lat_stat) * 0.99)])
    print('    99.9th: ', lat_stat[(int)(len(lat_stat) * 0.999)])
    print('    env_state:')
    pprint(env_state)

def main(args):
    # Instantiate Env.
    env = Env()

    # Load and parse json config file.
    with open(args.config, 'r') as f:
        json_data = json.load(f)
        
    entry_point_function = json_data['entry-point']
    functions = json_data['functions']
    invoker_configs = json_data['invoker-configs']
    entry_point_function_index = functions.index(entry_point_function)

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

    entry_service = services[entry_point_function_index]
    run_service(env, entry_service, invoker_configs)

    # Scale up pod replicas.
    env.scale_deployments(deployments, 5)

    run_service(env, entry_service, invoker_configs)

    # Delete deployment when finished.
    env.delete_functions(services)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--config')
    args = parser.parse_args()
    main(args)