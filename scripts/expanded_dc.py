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

from data_collection import DataCollect
from k8s_env_shim import Env
from multiprocessing import Process, Manager
from subprocess import run
from yaml.loader import SafeLoader
from os import path
from k8s_env_shim import Env
from pprint import pprint
from itertools import chain, combinations
from setup_service import Service
from setup_deployment import Deployment

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
        dc = DataCollect(data, current_benchmarks, success_count, verbose=verbose)

        # Setup Prometheus and check if setup is successful.
        if not env.setup_prometheus():
            print("[ERROR] Prometheus setup failed, please read error message and try again.")
            return 0
        
        # Load and parse json config file.
        with open(args.config, 'r') as f:
            json_data = json.load(f)
        # Load and parse data collection json config file.
        with open(args.dcconfig, 'r') as f:
            dc_json_data = json.load(f)
        
        percent_range = dc_json_data['percent_range']/100
        # Load CSV file as pandas Dataframe.
        hpa_data = pd.read_csv(args.data)

        benchmarks = json_data['benchmarks']
        processes = []

        # Generate a list of random (benchmark, rps, duration) values
        dc.save_data()

        for i in range(len(hpa_data['Benchmark'])):
            benchmark_name = hpa_data['Benchmark'][i]
            # Skip chained functions for now.
            if benchmark_name == 'video-analytics':
                continue
            target_rps = hpa_data['Target RPS'][i]
            duration = hpa_data['Duration (s)'][i]
            recommendations = hpa_data['Replicas']

            # Search for the benchmark.
            for bm in benchmarks:
                if benchmark['name'] == benchmark_name:
                    benchmark = bm
                    break
            
            # Get upper and lower bounds for scaling recs
            min_recommendations = [np.floor(rec * (1 + percent_range)) for rec in recommendations]
            max_recommendations = [np.ceil(rec * (1 - percent_range)) for rec in recommendations]
            # Get scaling ranges for each function.
            scale_ranges = [np.arange(min_recommendations[i], max_recommendations[i]) for i in range(len(recommendations))]
            
            functions = benchmark['functions']
            # Read configs for benchmark
            entry_point_function = benchmark['entry-point']
            entry_point_function_index = functions.index(entry_point_function)

            # TODO: separate "official" YAMLS from the copies we make when running.
            # Instantiate Services and Deployments
            services = []
            deployments = []
            # Assign this benchmark a random id to avoid conflicts
            rand_id = ''.join(random.choices(string.ascii_lowercase, k=10))
            benchmark_name += '-' + rand_id
            # Deploy all functions.
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
                # Ignore HPA because we are scaling manually.
                manifests = [new_dep, new_svc]
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

            p = Process(target=dc.run_service, args=(env, benchmark_name, deployments, services, entry_service, target_rps, duration, scale_ranges))
            dc.current_benchmarks[benchmark_name] = 1
            if verbose:
                print(f"[INFO] Process for benchmark `{benchmark_name}` created.\n")
            p.start()
            processes.append(p)

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
    # CSV file for data
    parser.add_argument('--data')
    # Data collection configs
    parser.add_argument('--dcconfig')
    # Verbosity: 't' for verbose, 'f' for non-verbose
    parser.add_argument('-v', action='store_true', help= 'Verbosity: -v for verbose, leave empty for non-verbose')
    #TODO: add -h argument
    args = parser.parse_args()
    main(args)