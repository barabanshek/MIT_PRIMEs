# This is just an example for using env_shim.
from env_shim import *

# Demo parameters.
kDemoDeploymentActions = {
    "fibonacci": {
        "benchmark_name": "fibonacci",
        "functions": {
            "fibonacci-python": {'node' : 3, 'containerScale' : 3, 'containerConcurrency' : 10}
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
            "decoder": {'node' : 1, 'containerScale' : 3, 'containerConcurrency' : 1},
            "recog": {'node' : 2, 'containerScale' : 3, 'containerConcurrency' : 1},
            "streaming": {'node' : 3, 'containerScale' : 3, 'containerConcurrency' : 1}
        },
        "entry_point": "streaming",
        "port": 80
    },

    "video-analytics-same-node": {
        "benchmark_name": "video-analytics",
        "functions": {
            "decoder": {'node' : 1, 'containerScale' : 3, 'containerConcurrency' : 1},
            "recog": {'node' : 1, 'containerScale' : 3},
            "streaming": {'node' : 1, 'containerScale' : 3}
        },
        "entry_point": "streaming",
        "port": 80
    },

    "online-shop-ad": {
        "benchmark_name": "online-shop",
        "functions": {
            "adservice": {'node' : 1, 'containerScale' : 5, 'containerConcurrency' : 1}
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
            "hotel-app-geo-tracing": {'node' : 2, 'containerScale' : 5}
        },
        "entry_point": "hotel-app-geo-tracing",
        "port": 80
    },

    "hotel-app-geo": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-geo": {'node' : 2, 'containerScale' : 5}
        },
        "entry_point": "hotel-app-geo",
        "port": 80
    },

    "hotel-app-profile": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-profile": {'node' : 2, 'containerScale' : 5}
        },
        "entry_point": "hotel-app-profile",
        "port": 80
    },

    "hotel-app-rate": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-rate": {'node' : 2, 'containerScale' : 5}
        },
        "entry_point": "hotel-app-rate",
        "port": 80
    },

    "hotel-app-recommendation": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-recommendation": {'node' : 3, 'containerScale' : 15}
        },
        "entry_point": "hotel-app-recommendation",
        "port": 80
    },

    "hotel-app-reservation": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-reservation": {'node' : 2, 'containerScale' : 5}
        },
        "entry_point": "hotel-app-reservation",
        "port": 80
    },

    "hotel-app-user": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-user": {'node' : 2, 'containerScale' : 5}
        },
        "entry_point": "hotel-app-user",
        "port": 80
    }
}

def main(args):
    env = Env(args.serverconfig)
    env.enable_env()

    # Exec demo configuration.
    # Deploy.
    ret = env.deploy_application(
        kDemoDeploymentActions[args.benchmark]['benchmark_name'], kDemoDeploymentActions[args.benchmark]['functions'])
    if ret == EnvStatus.ERROR:
        assert False

    # Invoke.
    (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename = \
        env.invoke_application(
            kDemoDeploymentActions[args.benchmark]['benchmark_name'],
            kDemoDeploymentActions[args.benchmark]['entry_point'],
            {'port': kDemoDeploymentActions[args.benchmark]['port'], 'duration': args.duration, 'rps': args.rps})

    # Sample env.
    env_state = env.sample_env(args.duration)
    lat_stat = env.get_latencies(stat_lat_filename)
    if lat_stat == []:
        print("No responses were returned, no latency statistics is computed.")
        return

    # Print statistics.
    lat_stat.sort()
    print(
        f'    stat: {stat_issued}, {stat_completed}, {stat_real_rps}, {stat_target_rps}, latency file: {stat_lat_filename}')
    print('    50th: ', lat_stat[(int)(len(lat_stat) * 0.5)])
    print('    90th: ', lat_stat[(int)(len(lat_stat) * 0.90)])
    print('    99th: ', lat_stat[(int)(len(lat_stat) * 0.99)])
    print('    99.9th: ', lat_stat[(int)(len(lat_stat) * 0.999)])
    print('    env_state:', env_state)


#
# Example cmd:
#   python3 env_shim_demo.py --serverconfig server_configs.json --benchmark video-analytics --duration 10 --rps 5
#
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--serverconfig')
    parser.add_argument('--benchmark')
    parser.add_argument('--duration')
    parser.add_argument('--rps')
    # parser.add_argument('--action')
    args = parser.parse_args()

    main(args)