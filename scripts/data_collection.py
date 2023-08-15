import argparse
from k8s_env_shim import Env
from pprint import pprint
import json
import os
import pickle
import time
import numpy as np

def main(args):
    # Instantiate Env.
    env = Env(args.config)

    # Load and initialize data collection configs.
    with open(args.config, 'r') as f:
        json_data = json.load(f)
    invoker_params = json_data['invoker_configs']
    benchmarks = invoker_params['names']
    rps_values = json_data['rps_values']
    n_runs = json_data['n_runs']

    # Invoke for every given benchmark at every given target RPS value.
    for benchmark in benchmarks:
        print(f'RUNNING BENCHMARK: {benchmark}...\n')
        
        # Clear previously collected data.
        if args.clearprevious == 'true':
            try:
                os.remove(f'./data/{benchmark}/{benchmark}_tail_lats_50.pickle')
                os.remove(f'./data/{benchmark}/{benchmark}_tail_lats_95.pickle')
                os.remove(f'./data/{benchmark}/{benchmark}_tail_lats_99.pickle')
            except:
                pass
            try:
                os.remove(f'./data/{benchmark}/{benchmark}_drop_rates.pickle')
            except:
                pass
            try:
                os.remove(f'./data/{benchmark}/{benchmark}_rps_deltas.pickle')
            except:
                pass

        # Check if the pickle files exist. If so, initialize data collection with the previously collected
        # values already in place. If not, initialize with empty dicts.
        try:
            with open(f'./data/{benchmark}/{benchmark}_tail_lats_50.pickle', 'rb') as handle:
                tail_lats_50 = pickle.load(handle)
            with open(f'./data/{benchmark}/{benchmark}_tail_lats_95.pickle', 'rb') as handle:
                tail_lats_95 = pickle.load(handle)
            with open(f'./data/{benchmark}/{benchmark}_tail_lats_99.pickle', 'rb') as handle:
                tail_lats_99 = pickle.load(handle)
        except:
            tail_lats_50 = {}
            tail_lats_95 = {}
            tail_lats_99 = {}
        try:
            with open(f'./data/{benchmark}/{benchmark}_drop_rates.pickle', 'rb') as handle:
                drop_rates = pickle.load(handle)
        except:
            drop_rates = {}
        try:
            with open(f'./data/{benchmark}/{benchmark}_rps_deltas.pickle', 'rb') as handle:
                rps_deltas = pickle.load(handle)
        except:
            rps_deltas = {}

        # Check if setup is successful. If not, attempt to delete existing deployment.
        if not env.setup():
            env.delete_deployment()
            print("[ERROR] Setup failed, please read error message and try again.")
            return 0
        
        # Run invoker for every given target RPS value.
        for rps in rps_values:
            print(f'Collecting data for {rps} RPS...\n')

            sample_tail_lats_50 = []
            sample_tail_lats_95 = []
            sample_tail_lats_99 = []
            sample_drop_rates = []
            sample_rps_deltas = []

            # Run multiple iterations.
            for i in range(n_runs):
                # If an error is encountered, keep running until it works.
                error = True
                while error:
                    try:
                        print(f'Run {i+1}/{n_runs}\n')

                        # Invoke.
                        (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename = \
                            env.invoke_service()
                        lat_stat = env.get_latencies(stat_lat_filename)
                        if lat_stat == []:
                            print("[ERROR] No responses were returned, no latency statistics is computed.")
                            return
                        lat_stat.sort()

                        # Sample env.
                        env_state = env.sample_env()

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

                        # Save collected data to lists.
                        sample_tail_lats_50.append(lat_stat[(int)(len(lat_stat)*0.50)]/1000)
                        sample_tail_lats_95.append(lat_stat[(int)(len(lat_stat)*0.95)]/1000)
                        sample_tail_lats_99.append(lat_stat[(int)(len(lat_stat)*0.99)]/1000)
                        sample_drop_rates.append((stat_issued - stat_completed) / stat_issued)
                        sample_rps_deltas.append(stat_real_rps - stat_target_rps)
                        
                        # No error was encountered, so the loop continues.
                        error = False

                    except Exception as err:
                        print(f'[ERROR] An error occurred while running this run.')
                        print(f'[ERROR] Error message:\n{err}')
                        error = True
                        pass

            # Update dicts using data collected in lists. 
            sample_tail_lats_50 = np.array(sample_tail_lats_50)
            sample_tail_lats_95 = np.array(sample_tail_lats_95)
            sample_tail_lats_99 = np.array(sample_tail_lats_99)
            sample_drop_rates = np.array(sample_drop_rates)
            sample_rps_deltas = np.array(sample_rps_deltas)
            tail_lats_50[stat_target_rps] = sample_tail_lats_50
            tail_lats_95[stat_target_rps] = sample_tail_lats_95
            tail_lats_99[stat_target_rps] = sample_tail_lats_99
            drop_rates[stat_target_rps] = sample_drop_rates
            rps_deltas[stat_target_rps] = sample_rps_deltas

            # Save dicts to pickle files.
            with open(f'./data/{benchmark}/{benchmark}_tail_lats_50.pickle', 'wb') as handle:
                pickle.dump(tail_lats_50, handle, protocol=pickle.HIGHEST_PROTOCOL)
            with open(f'./data/{benchmark}/{benchmark}_tail_lats_95.pickle', 'wb') as handle:
                pickle.dump(tail_lats_95, handle, protocol=pickle.HIGHEST_PROTOCOL)
            with open(f'./data/{benchmark}/{benchmark}_tail_lats_99.pickle', 'wb') as handle:
                pickle.dump(tail_lats_99, handle, protocol=pickle.HIGHEST_PROTOCOL)

            with open(f'./data/{benchmark}/{benchmark}_drop_rates.pickle', 'wb') as handle:
                pickle.dump(drop_rates, handle, protocol=pickle.HIGHEST_PROTOCOL)

            with open(f'./data/{benchmark}/{benchmark}_rps_deltas.pickle', 'wb') as handle:
                pickle.dump(rps_deltas, handle, protocol=pickle.HIGHEST_PROTOCOL)
    
    # Delete deployment when finished.
    env.delete_deployment()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--config')
    parser.add_argument('--clearprevious')
    args = parser.parse_args()
    main(args)