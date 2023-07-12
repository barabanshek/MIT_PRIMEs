# This is just an example for using env_shim.
from env_shim import *
import pickle
import os
import time as t

# Demo parameters.
kDemoDeploymentActions = {
    "fibonacci": {
        "benchmark_name": "fibonacci",
        "functions": {
            "fibonacci-python": {'node' : 3, 'containerScale' : 30, 'containerConcurrency' : 10}
        },
        "entry_point": "fibonacci-python",
        "port": 80
    },

    "fibonacci_10": {
        "benchmark_name": "fibonacci",
        "functions": {
            "fibonacci-python": {'node' : 2, 'containerScale' : 10}
        },
        "entry_point": "fibonacci-python",
        "port": 80
    },

    "video-analytics": {
        "benchmark_name": "video-analytics",
        "functions": {
            "decoder": {'node' : 1, 'containerScale' : 5, 'containerConcurrency' : 0},
            "recog": {'node' : 2, 'containerScale' : 30, 'containerConcurrency' : 0},
            "streaming": {'node' : 3, 'containerScale' : 5, 'containerConcurrency' : 0}
        },
        "entry_point": "streaming",
        "port": 80
    },

    "video-analytics-same-node": {
        "benchmark_name": "video-analytics",
        "functions": {
            "decoder": {'node' : 1, 'containerScale' : 1, 'containerConcurrency' : 0},
            "recog": {'node' : 1, 'containerScale' : 1, 'containerConcurrency' : 0},
            "streaming": {'node' : 1, 'containerScale' : 1, 'containerConcurrency' : 0}
        },
        "entry_point": "streaming",
        "port": 80
    },

    "online-shop-ad": {
        "benchmark_name": "online-shop",
        "functions": {
            "adservice": {'node' : 1, 'containerScale' : 5}
        },
        "entry_point": "adservice",
        "port": 80
    },

    "online-shop-cart": {
        "benchmark_name": "online-shop",
        "functions": {
            "cartservice": {'node' : 1, 'containerScale' : 5}
        },
        "entry_point": "cartservice",
        "port": 80
    },

    "online-shop-currency": {
        "benchmark_name": "online-shop",
        "functions": {
            "currencyservice": {'node' : 3, 'containerScale' : 5}
        },
        "entry_point": "currencyservice",
        "port": 80
    },

    "online-shop-email": {
        "benchmark_name": "online-shop",
        "functions": {
            "emailservice": {'node' : 2, 'containerScale' : 5}
        },
        "entry_point": "emailservice",
        "port": 80
    },

    "online-shop-payment": {
        "benchmark_name": "online-shop",
        "functions": {
            "paymentservice": {'node' : 4, 'containerScale' : 5}
        },
        "entry_point": "paymentservice",
        "port": 80
    },

    "online-shop-productcatalogservice": {
        "benchmark_name": "online-shop",
        "functions": {
            "productcatalogservice": {'node' : 3, 'containerScale' : 5}
        },
        "entry_point": "productcatalogservice",
        "port": 80
    },

    "online-shop-shippingservice": {
        "benchmark_name": "online-shop",
        "functions": {
            "shippingservice": {'node' : 3, 'containerScale' : 5}
        },
        "entry_point": "shippingservice",
        "port": 80
    },

    "hotel-app-geo-tracing": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-geo-tracing": {'node' : 2, 'containerScale' : 5, 'containerConcurrency' : 0}
        },
        "entry_point": "hotel-app-geo-tracing",
        "port": 80
    },

    "hotel-app-geo": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-geo": {'node' : 2, 'containerScale' : 1, 'containerConcurrency' : 0}
        },
        "entry_point": "hotel-app-geo",
        "port": 80
    },

    "hotel-app-profile": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-profile": {'node' : 2, 'containerScale' : 1, 'containerConcurrency' : 0}
        },
        "entry_point": "hotel-app-profile",
        "port": 80
    },

    "hotel-app-rate": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-rate": {'node' : 2, 'containerScale' : 1, 'containerConcurrency' : 0}
        },
        "entry_point": "hotel-app-rate",
        "port": 80
    },

    "hotel-app-recommendation": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-recommendation": {'node' : 3, 'containerScale' : 1, 'containerConcurrency' : 0}
        },
        "entry_point": "hotel-app-recommendation",
        "port": 80
    },

    "hotel-app-reservation": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-reservation": {'node' : 2, 'containerScale' : 1, 'containerConcurrency' : 0}
        },
        "entry_point": "hotel-app-reservation",
        "port": 80
    },

    "hotel-app-user": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-user": {'node' : 4, 'containerScale' : 1, 'containerConcurrency' : 0}
        },
        "entry_point": "hotel-app-user",
        "port": 80
    }
}

def main(args):

    env = Env(args.serverconfig)
    env.enable_env()
    with open(args.datacollectionconfig, 'r') as f:
        json_data = json.load(f)
    duration = json_data['duration']
    benchmarks = json_data['benchmarks']
    rps_values = json_data['rps_values']
    n_runs = json_data['n_runs']

    for benchmark in benchmarks:
        print(f'RUNNING BENCHMARK: {benchmark}...')
        # try:
        # if a benchmark encounters an error, skip it
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
                os.remove(f'./data/{benchmark}/{benchmark}_rps_delta.pickle')
            except:
                pass

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
            with open(f'./data/{benchmark}/{benchmark}_rps_delta.pickle', 'rb') as handle:
                rps_deltas = pickle.load(handle)
        except:
            rps_deltas = {}

        # Exec demo configuration.
        # Deploy.
        ret = env.deploy_application(
            kDemoDeploymentActions[benchmark]['benchmark_name'], kDemoDeploymentActions[benchmark]['functions'])
        if ret == EnvStatus.ERROR:
            assert False
        for rps in rps_values:
            print(f'Collecting data for {rps} RPS...')
            sample_tail_lats_50 = []
            sample_tail_lats_95 = []
            sample_tail_lats_99 = []
            sample_drop_rates = []
            sample_rps_deltas = []

            for i in range(n_runs):
                try:
                    print(f'Run {i+1}/{n_runs}')
                    # Invoke.
                    (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename = \
                        env.invoke_application(
                            kDemoDeploymentActions[benchmark]['benchmark_name'],
                            kDemoDeploymentActions[benchmark]['entry_point'],
                            {'port': kDemoDeploymentActions[benchmark]['port'], 'duration': duration, 'rps': rps})

                    # Sample env.
                    env_state = env.sample_env(duration)
                    lat_stat = env.get_latencies(stat_lat_filename)
                    lat_stat.sort()

                    # Print statistics.
                    print(
                        f'    stat: {stat_issued}, {stat_completed}, {stat_real_rps}, {stat_target_rps}, latency file: {stat_lat_filename}')
                    print('    50th: ', lat_stat[(int)(len(lat_stat) * 0.5)])
                    print('    90th: ', lat_stat[(int)(len(lat_stat) * 0.90)])
                    print('    99th: ', lat_stat[(int)(len(lat_stat) * 0.99)])
                    print('    99.9th: ', lat_stat[(int)(len(lat_stat) * 0.999)])
                    print('    env_state:', env_state)

                    sample_tail_lats_50.append(lat_stat[(int)(len(lat_stat)*0.50)]/1000)
                    sample_tail_lats_95.append(lat_stat[(int)(len(lat_stat)*0.95)]/1000)
                    sample_tail_lats_99.append(lat_stat[(int)(len(lat_stat)*0.99)]/1000)

                    sample_drop_rates.append((stat_issued - stat_completed) / stat_issued)
                    sample_rps_deltas.append(stat_real_rps - stat_target_rps)

                except Exception as err:
                    print(f'> Error occurred while running this run.')
                    print(f'ERROR: {err}')
                    pass
                t.sleep(30)
            
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

        # except Exception as e:
        #     print(f'> Error occurred while running {benchmark}, so it was skipped.')
        #     print(f'ERROR: {e}')
        #     pass


#
# Example cmd:
#   python3 data_collection.py --serverconfig server_configs.json --benchmark video-analytics --duration 10 --rps 5
#
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--serverconfig')
    parser.add_argument('--datacollectionconfig')
    parser.add_argument('--clearprevious')
    args = parser.parse_args()

    main(args)
