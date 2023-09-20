import argparse
import yaml
import json
import time
import random
import pandas as pd
import pickle
import numpy as np
import string
import os

from multiprocessing import Process, Array, Lock, Manager
from subprocess import run
from yaml.loader import SafeLoader
from os import path
from k8s_env_shim import Env
from pprint import pprint
from itertools import chain, combinations
from setup_service import Service
from setup_deployment import Deployment


# Take Deployment, Service, and HPA dicts and reassign the names.
def rename_yaml(dep, svc, hpa, new_name):
    # Update Deployment name.
    dep['metadata']['name'] = new_name
    dep['metadata']['labels']['app'] = new_name
    dep['spec']['selector']['matchLabels']['app'] = new_name
    dep['spec']['template']['metadata']['labels']['app'] = new_name
    for i in range(len(dep['spec']['template']['spec']['containers'])):
        if dep['spec']['template']['spec']['containers'][i]['name'] != 'relay':
            dep['spec']['template']['spec']['containers'][i]['name'] = new_name
    # Update chaining.
    if "-addr" in dep['spec']['template']['spec']['containers'][i]['args']:
        address = dep['spec']['template']['spec']['containers'][i]['args'][1]
        ind = address.index('.')
        address = address[:ind] + new_name[-11:] + address[ind:]
        dep['spec']['template']['spec']['containers'][i]['args'][1] = address
    # Update Service name.
    svc['metadata']['name'] = new_name
    svc['spec']['selector']['app'] = new_name

    # Update HPA name.
    hpa['metadata']['name'] = new_name + '-hpa'
    hpa['spec']['scaleTargetRef']['name'] = new_name

    return dep, svc, hpa

def delete_files_in_directory(directory_path):
   try:
     files = os.listdir(directory_path)
     for file in files:
       file_path = os.path.join(directory_path, file)
       if os.path.isfile(file_path):
         os.remove(file_path)
     print("All files deleted successfully.")
   except OSError:
     print("Error occurred while deleting files.")

class DataCollect:

    def __init__(self, data, current_benchmarks, success_count, args, verbose=False):
        self.data = data
        self.current_benchmarks = current_benchmarks
        self.lock = Lock()
        self.verbose = verbose
        self.success_count = success_count
        self.rand_string = ''.join(random.choices(string.ascii_lowercase, k=10))
        with open(args.config, 'r') as f:
            json_data = json.load(f)
            json_data['total_duration'] = args.t
            json_data['workload_interval'] = args.d
        config_folder = './experiment-configs'
        config_filename = f'{config_folder}/{self.rand_string}_configs.json'
        with open(config_filename, 'w') as f:
            json.dump(json_data, f)
            print(f'[INFO] Saved configs in {config_filename}')

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

    # Save the current data to a pickle file.
    def save_data(self):
        # Dump data in pickle file.
        data_filename = f'./data/data_{self.rand_string}.pickle'
        with open(data_filename, 'wb') as handle:
            pickle.dump(list(self.data), handle, protocol=pickle.HIGHEST_PROTOCOL)
        print(f"[SAVE] Data saved in {data_filename}.")
        with open(f'./data/successes_{self.rand_string}.pickle', 'wb') as handle:
            pickle.dump(list(self.success_count), handle, protocol=pickle.HIGHEST_PROTOCOL)
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

    # Get the percent utilizations.
    # [mem, cpu]
    def get_resource_metrics(self, name):
        metrics = []
        for i in range(2):
            get_resource_metrics_cmd = f"kubectl get hpa/{name}-hpa -o jsonpath='{{.status.currentMetrics[{i}].resource.current.averageUtilization}}'"
            try:
                ret = int(run(get_resource_metrics_cmd, shell=True, capture_output=True, universal_newlines=True).stdout)
                metrics.append(ret)
            except Exception as e:
                print(f"[ERROR] Benchmark: {name}")
                print(e)
        return metrics

    # Setup the benchmark, invoke, print stats, and delete service.
    # This function will be multithreaded to run several benchmarks concurrently.
    def run_service(self, env, benchmark_name, deployments, services, entry_service, rps, duration, max_retries=5, delay_time=2, num_metrics=2):
        # Check if the benchmark already exists. If not, deploy. If so, skip deployment.
        # Check if benchmark setup is successful. If not, attempt to delete existing deployments.
        # TODO: deploy only the services that the benchmark is missing. For example, if streaming and decoder are ready, deploy recog only.
        if not env.setup_functions(deployments, services):
            env.delete_functions(services)
            self.current_benchmarks[benchmark_name] = 0
            print(f"[ERROR] Benchmark `{benchmark_name}` setup failed, please read error message and try again.")
            self.success_count.append(0)
            return 0
        # Invoke.
        (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename = \
            env.invoke_service(entry_service, duration, rps)
        # Get timestamp.
        timestamp = time.time()
        # Get scales and resource utils.
        replicas = []
        cpu_requests = []
        mem_requests = []
        cpu_limits = []
        mem_limits = []
        cpu_utilizations = []
        mem_utilizations = []
        for service in services:
            # Get the number of replicas.
            get_replicas_cmd = f"kubectl get deployment/{service.name} -o jsonpath='{{.spec.replicas}}'"
            replicas.append(int(run(get_replicas_cmd, shell=True, capture_output=True, universal_newlines=True).stdout))
            # Get the requests and limits.
            get_cpu_requests_cmd = f"kubectl get deployment/{service.name} -o jsonpath='{{.spec.template.spec.containers[0].resources.requests.cpu}}'"
            get_mem_requests_cmd = f"kubectl get deployment/{service.name} -o jsonpath='{{.spec.template.spec.containers[0].resources.requests.memory}}'"
            get_cpu_limits_cmd = f"kubectl get deployment/{service.name} -o jsonpath='{{.spec.template.spec.containers[0].resources.limits.cpu}}'"
            get_mem_limits_cmd = f"kubectl get deployment/{service.name} -o jsonpath='{{.spec.template.spec.containers[0].resources.limits.memory}}'"
            cpu_requests.append(run(get_cpu_requests_cmd, shell=True, capture_output=True, universal_newlines=True).stdout)
            mem_requests.append(run(get_mem_requests_cmd, shell=True, capture_output=True, universal_newlines=True).stdout)
            cpu_limits.append(run(get_cpu_limits_cmd, shell=True, capture_output=True, universal_newlines=True).stdout)
            mem_limits.append(run(get_mem_limits_cmd, shell=True, capture_output=True, universal_newlines=True).stdout)         
            
            metrics_success = False
            # Try getting metrics multiple times
            for i in range(max_retries):
                metrics = self.get_resource_metrics(service.name)
                if len(metrics) == num_metrics:
                    metrics_success = True
                    print(f"[INFO] Metrics successfully collected for benchmark `{benchmark_name}.`")
                    break
                print(f"[ERROR] Not enough metrics were returned for benchmark `{benchmark_name}.`")
                print(f"[INFO] Retrying... ({i+1}/{max_retries})")
                time.sleep(delay_time)
            # Check if metrics were acquired.
            if not metrics_success:
                print(f"[ERROR] Failed to return metrics for benchmark `{benchmark_name}.`")
                env.delete_functions(services)
                self.current_benchmarks[benchmark_name] = 0
                self.success_count.append(0)
                return 
            mem_utilizations.append(metrics[0])
            cpu_utilizations.append(metrics[1])
        # Get latencies.
        lat_stat = env.get_latencies(stat_lat_filename)
        if lat_stat == []:
            print(f"[ERROR] No responses were returned for benchmark `{benchmark_name}`, so no latency statistics have been computed.")
            env.delete_functions(services)
            self.current_benchmarks[benchmark_name] = 0
            self.success_count.append(0)
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
        num_metrics = len(unpacked_env_state[0])
        state = []
        for i in range(num_metrics):
            state.append([unpacked_env_state[j][i] for j in range(num_nodes)])

        # avgs = np.zeros(len(unpacked_env_state[0]))

        # state = [np.array(unpacked_env_state[i]) for i in range(num_nodes)]
        # avgs = np.add(avgs, np.array(unpacked_env_state[i])/num_nodes)
                    
        cpu_idle, cpu_user, cpu_system, mem_free, net_transmit, net_receive = state

        if self.verbose:
            print(f"[INFO] Invocation statistics for benchmark `{benchmark_name}`:\n")
            print('    time: ', timestamp)
            print('    replicas: ', replicas)
            print(
                f'    stat: {stat_issued}, {stat_completed}, {stat_real_rps}, {stat_target_rps}, latency file: {stat_lat_filename}')
            print('    50th: ', lat_50/1000, 'ms')
            print('    90th: ', lat_90/1000, 'ms')
            print('    99th: ', lat_99/1000, 'ms')
            print('    99.9th: ', lat_999/1000, 'ms')
            print('    env_state:')
            self.print_env_state(env_state)

        # Delete Deployments when finished. 
        self.success_count.append(1)  
        env.delete_functions(services)
        self.current_benchmarks[benchmark_name] = 0
        # Update data table.
        with self.lock:
            self.data.append([timestamp, benchmark_name[:-11], 
                              cpu_utilizations,
                              mem_utilizations,
                              replicas,
                              cpu_requests, cpu_limits, mem_requests, mem_limits,
                              duration, 
                              stat_issued, 
                              stat_completed, 
                              stat_real_rps, 
                              stat_target_rps, 
                              lat_50, lat_90, lat_99, lat_999,
                              cpu_idle, cpu_user, cpu_system,
                              mem_free,
                              net_transmit, net_receive])
            
    def cleanup(self):
        run('''kubectl delete deployment --all''', shell=True)
        run('''kubectl delete service --all''', shell=True)
        run('''kubectl delete hpa --all''', shell=True)
        run('''kubectl apply -f ~/vSwarm/benchmarks/hotel-app/yamls/knative/database.yaml''', shell=True)
        run('''kubectl apply -f ~/vSwarm/benchmarks/hotel-app/yamls/knative/memcached.yaml''', shell=True)
        delete_files_in_directory('./k8s-yamls/tmp/')
        run('''find . -name 'rps*.csv' -delete''', shell=True)
        print('Deleted all latency files.')
        
def main(args):
    with Manager() as manager:
        # Initialize shared variables
        data = manager.list()
        current_benchmarks = manager.dict()
        success_count = manager.list()

        # Verbosity
        verbose = args.v

        # Instantiate Env.
        env = Env(verbose=verbose)

        # Instantiate DataCollect.
        dc = DataCollect(data, current_benchmarks, success_count, args, verbose=verbose)

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
            dc.save_data()
            workload = dc.generate_workload(benchmarks)

            for benchmark, rps, duration in workload:
                benchmark_name = benchmark['name']
                if verbose:
                    print(f"[INFO] Proposed incoming workload: {benchmark_name} at {rps} RPS for {duration} seconds.")
                functions = benchmark['functions']
                # Read configs for benchmark
                entry_point_function = benchmark['entry-point']
                entry_point_function_index = functions.index(entry_point_function)

                # TODO: separate "official" YAMLS from the copies we make when running.
                # Instantiate Services and Deployments
                services = []
                deployments = []
                # is_already_deployed = dc.benchmark_already_deployed(benchmark_name)
                # Assign this benchmark a random id to avoid conflicts
                # if is_already_deployed:
                rand_id = ''.join(random.choices(string.ascii_lowercase, k=10))
                benchmark_name += '-' + rand_id
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
                    file_name = f"k8s-yamls/tmp/{new_funct}.yaml"
                    # Dump manifests into new YAML file.
                    with open(file_name, 'x') as f:
                        yaml.dump_all(manifests, f)
                    # Instantiate Service objects
                    port = new_svc['spec']['ports'][0]['port']
                    service = Service(new_funct, file_name, port)
                    services.append(service)
                    # Instantiate Deployment objects
                    deployment = Deployment(new_dep, env.api)
                    deployments.append(deployment)

                entry_service = services[entry_point_function_index]
                # Check if the benchmark has already been deployed. If so, make a copy with a new ID.
                # print("[INFO] Current benchmark statuses:")
                # Sort current benchmark statuses
                # pprint({k: v for k, v in sorted(dc.current_benchmarks.items(), key=lambda item: item[1], reverse=True)})
                # if dc.benchmark_already_deployed(benchmark_name):
                #     if verbose:
                #         print(f"[INFO] Dropped proposed benchmark `{benchmark_name}` because it is already running.")
                #     continue
                
                # If benchmark can be deployed, create and start process for multiprocessing.
                p = Process(target=dc.run_service, args=(env, benchmark_name, deployments, services, entry_service, rps, duration))
                dc.current_benchmarks[benchmark_name] = 1
                if verbose:
                    print(f"[INFO] Process for benchmark `{benchmark_name}` created.\n")
                p.start()
                processes.append(p)
            time.sleep(int(args.d))

        # Once all processes have finished, they can be joined.
        print("Time up, terminating all processes.")
        for p in processes:
            p.terminate()
            p.join()
        

    print("[INFO] Done!")
    print("[INFO] Cleaning up...")
    #TODO: give non-cleanup option
    dc.cleanup()
    print("[INFO] Cleanup complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # Config file for benchmarks
    parser.add_argument('--config')
    # Total time to run (seconds)
    parser.add_argument('-t', help='Total time to run (seconds)')
    # Interval between each workload generation (seconds)
    parser.add_argument('-d', help='Interval between each workload generation (seconds)')
    # Verbosity: 't' for verbose, 'f' for non-verbose
    parser.add_argument('-v', action='store_true', help= 'Verbosity: -v for verbose, leave empty for non-verbose')
    #TODO: add -h argument
    args = parser.parse_args()
    main(args)