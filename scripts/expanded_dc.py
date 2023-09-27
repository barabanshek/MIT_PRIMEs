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

from data_processing import standardize_format, make_dir
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
     
def create_df(data_file):
    with open(data_file, 'rb') as handle:
        data = pickle.load(handle)
        df = pd.DataFrame(data)
    # with open(f'./data/successes_{data_id}.pickle', 'rb') as handle:
    #     successes = pickle.load(handle)
    #     print(f'Benchmarks: {len(successes)}')
    #     print(f'Successes: {sum(successes)}')
    pd.set_option('display.max_columns', None)
    # remove RPS column
    df.columns = ['timestamp',
                  'benchmark', 
                  'cpu_util',
                  'mem_util',
                  'replicas',
                  'cpu_requests', 'cpu_limits', 'mem_requests', 'mem_limits',
                  'duration', 
                  'issued', 
                  'completed', 
                  'rps_real', 
                  'rps_target', 
                  '50th', '90th', '99th', '99.9th', 
                  'avg_cpu_idle', 'avg_cpu_user', 'avg_cpu_system',
                              'avg_mem_free',
                              'avg_net_transmit (bps)', 'avg_net_receive (bps)']
    return df

def main(args):
    with Manager() as manager:
        # Initialize shared variables
        data = manager.list()
        current_benchmarks = manager.dict()
        success_count = manager.list()
        
        # Verbosity
        verbose = args.v
        hpa_data_file = args.f
        data_id = hpa_data_file[-17:-7]
        exp_id = ''.join(random.choices(string.ascii_lowercase, k=10))
        data_folder = './expanded_data'
        data_filename = f'expanded_data_{data_id}_{exp_id}.pickle'
        # Instantiate Env.
        env = Env(verbose=verbose)

        # Instantiate DataCollect.
        # This will be used to collect data.
        dc = DataCollect(data, current_benchmarks, success_count, verbose=verbose)
        make_dir('./expanded_data')
        dc.save_data(data_folder, data_filename)
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
        
        benchmarks = json_data['benchmarks']
        percent_range = dc_json_data['percent_range']/100
        n_values = dc_json_data['n_values']
        n_runs = dc_json_data['n_runs']
        
        # Load pickle file as pandas Dataframe.
        hpa_df = create_df(hpa_data_file)

        # Clean data.
        index = hpa_df[hpa_df['cpu_util'].map(standardize_format) == 0].index
        hpa_df.drop(index, inplace=True)

        '''
        For each row in the DataFrame:
	    1. Read the replica recommendation and evaluate the scale range. Here, we can set the exact number of values in the range to test. 
	    2. Read the invocation specs: duration, RPS.
	    3. Read the benchmark name, create the duplicate yaml without HPA, and deploy
	    4. Once deployed, for every value N in scale range:
            1. Create a new process
            2. Scale the deployment to N
            3. Invoke the benchmark with its assigned duration and RPS.
            4. Collect data
	    5. Join the processes created in the loop so that we wait until it finishes executing.
        ''' 
        
        # For each row:
        print(hpa_df.index)
        for ind in hpa_df.index:
            print(f'[INFO] Expanding data for row {ind}')
            benchmark_name = hpa_df['benchmark'][ind]
            # Skip chained functions for now.
            if benchmark_name == 'video-analytics':
                continue
            # Read invocation specs: duration, RPS
            target_rps = hpa_df['rps_target'][ind]
            duration = hpa_df['duration'][ind]
            
            # Read recommendation value.
            recommendations = hpa_df['replicas'][ind]
            # Get upper and lower bounds for scaling recs
            min_recommendations = [np.ceil(rec * (1 - percent_range)) for rec in recommendations]
            max_recommendations = [np.ceil(rec * (1 + percent_range)) for rec in recommendations]
            interval_sizes = [np.ceil((max_recommendations[i] - min_recommendations[i])/n_values) for i in range(len(recommendations))]
            # print(min_recommendations, max_recommendations, interval_sizes)
            
            # Get scaling ranges for each function.
            #TODO: set the range such that K values are explored.
            scale_ranges = [list(np.arange(min_recommendations[j], max_recommendations[j], interval_sizes[j])) for j in range(len(recommendations))]
            # print(scale_ranges)
            # Deploy the benchmark now and start the processes.
            # TODO: separate "official" YAMLS from the copies we make when running.
            # Instantiate Services and Deployments

            # Get the benchmark dictionary as parameterized in the configs JSON.
            for bm in benchmarks:
                if bm['name'] == benchmark_name:
                    benchmark = bm
                    break
                
            # Get the benchmark's necessary functions
            functions = benchmark['functions']
            # Get the benchmark's entry point function
            entry_point_function = benchmark['entry-point']
            entry_point_function_index = functions.index(entry_point_function)
            
            # Deploy all functions.
            # For each scale value.
            # The scale ranges need to be the same size for all functions.
            # [[1, 2, 3], [4, 5, 6], [1, 2, 3]]
            # [[20.0, 19.0, 18.0, 17.0, 16.0, 15.0]]
            processes = []
            for scale_val_ind in range(len(scale_ranges[0])):
                    
                services = []
                deployments = []

                # Assign the benchmark a random id.
                temp_name = benchmark_name
                rand_id = ''.join(random.choices(string.ascii_lowercase, k=10))
                temp_name += '-' + rand_id
                
                # For each function.
                for i in range(len(scale_ranges)):
                    scale = scale_ranges[i][scale_val_ind]
                    if verbose:
                        print(f'[INFO] Collecting data for function {functions[i]} across range {scale_ranges[i]}')
                        print(f'[INFO] Currently collecting data for {scale} replicas.')
                    # Read YAML of original function to get dicts.
                    file_name = f"k8s-yamls/{functions[i]}.yaml"
                    with open(path.join(path.dirname(__file__), file_name)) as f:
                        dep, svc, hpa = yaml.load_all(f, Loader=SafeLoader)
                    # Update function to include new id.
                    new_funct = functions[i] + '-' + rand_id
                    # Update the old dict to include new id.
                    new_dep, new_svc, new_hpa = rename_yaml(dep, svc, hpa, new_funct)
                    # Freeze the autoscaler.
                    new_hpa['spec']['minReplicas'] = int(scale)
                    new_hpa['spec']['maxReplicas'] = int(scale)
                    # List of manifests as dicts to be converted into new YAML file.
                    # Ignore HPA because we are scaling manually.
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
                # Create process.
                p = Process(target=dc.run_service, args=(env, temp_name, deployments, services, entry_service, target_rps, duration), kwargs={'timeout' : 120})
                dc.current_benchmarks[temp_name] = 1
                if verbose: 
                    print(f"[INFO] Process for benchmark `{temp_name}` created.\n")
                p.start()
                processes.append(p)

            # Wait until the processes for the current benchmark finish
            for p in processes:
                p.join()
            dc.save_data(data_folder, data_filename)    
            dc.cleanup()    


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # Config file for benchmarks
    parser.add_argument('--config')
    # CSV file for data
    parser.add_argument('--f')
    # Data collection configs
    parser.add_argument('--dcconfig')
    # Verbosity: 't' for verbose, 'f' for non-verbose
    parser.add_argument('-v', action='store_true', help= 'Verbosity: -v for verbose, leave empty for non-verbose')
    #TODO: add -h argument
    args = parser.parse_args()
    main(args)