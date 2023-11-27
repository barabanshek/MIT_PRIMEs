import os
import pickle
from itertools import combinations_with_replacement
import numpy as np
from subprocess import run
import time
import torch
from dqn_main import DQN, ReplayMemory, Transition
from k8s_env_shim import Env
import argparse
import json
import random
from os import path
import yaml
from yaml import SafeLoader
from dqn_main import rename_yaml, make_dir, Service, Deployment, Benchmark
import string


def main(args):
    with open(args.config, 'r') as f:
        json_data = json.load(f)
        benchmarks = json_data['benchmarks']
    # Initialize Envs
    env_shim = Env(verbose=True)

    # List of all Benchmark objects
    bm_objects = []
    # Create manifests and objects.
    for benchmark in benchmarks:
        deployments, services = [], []
        benchmark_name = benchmark['name']
        functions = benchmark['functions']
        entry_point_function = benchmark['entry-point']
        entry_point_function_index = functions.index(entry_point_function)            
        sla = benchmark['sla']
        rps_vals = benchmark['rps-vals']
        for rps in rps_vals:
            rps_range = (rps, rps)
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

    # train-test split.
    random.shuffle(bm_objects)
    bm_object_sets = list(combinations_with_replacement(bm_objects, 3))
    train_benchmark_sets = bm_object_sets[:int(0.80 * len(bm_object_sets))]
    test_benchmarks_sets = bm_object_sets[int(0.80 * len(bm_object_sets)):]
    print(len(train_benchmark_sets))
    with open('train_benchmarks.pickle', 'wb') as handle:
        pickle.dump(train_benchmark_sets, handle, protocol=pickle.HIGHEST_PROTOCOL)
    with open('test_benchmarks.pickle', 'wb') as handle:
        pickle.dump(test_benchmarks_sets, handle, protocol=pickle.HIGHEST_PROTOCOL)    
    
if __name__ == "__main__":
    # Config file for benchmarks
    parser = argparse.ArgumentParser()
    parser.add_argument('--config')
    args = parser.parse_args()
    main(args)
