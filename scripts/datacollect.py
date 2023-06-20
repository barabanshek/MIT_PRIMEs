# This is just an example for using env_shim.
from env_shim import *
from agent import *
import math
import matplotlib.pyplot as plt

# Demo parameters.
kDemoDeploymentActions = {
    "fibonacci": {
        "benchmark_name": "fibonacci",
        "functions": {
            "fibonacci-python": [2, 10, 100, 50]
        },
        "entry_point": "fibonacci-python",
        "port": 80
    },

    "fibonacci_10": {
        "benchmark_name": "fibonacci",
        "functions": {
            "fibonacci-python": [2, 10]
        },
        "entry_point": "fibonacci-python",
        "port": 80
    },

    "video-analytics": {
        "benchmark_name": "video-analytics",
        "functions": {
            "decoder": [1, 3, 1, 25],
            "recog": [2, 3, 1, 25],
            "streaming": [3, 3, 1, 25]
        },
        "entry_point": "streaming",
        "port": 80
    },

    "video-analytics-same-node": {
        "benchmark_name": "video-analytics",
        "functions": {
            "decoder": [1, 3],
            "recog": [1, 3],
            "streaming": [1, 3]
        },
        "entry_point": "streaming",
        "port": 80
    },

    "online-shop-ad": {
        "benchmark_name": "online-shop",
        "functions": {
            "adservice": [1, 3]
        },
        "entry_point": "adservice",
        "port": 80
    },

    "online-shop-cartservice": {#doesnt work
        "benchmark_name": "online-shop",
        "functions": {
            "cartservice": [1, 3]
        },
        "entry_point": "cartservice",
        "port": 80
    },

    "online-shop-currency": {
        "benchmark_name": "online-shop",
        "functions": {
            "currencyservice": [3, 3]
        },
        "entry_point": "currencyservice",
        "port": 80
    },

    "online-shop-email": {
        "benchmark_name": "online-shop",
        "functions": {
            "emailservice": [2, 3]
        },
        "entry_point": "emailservice",
        "port": 80
    },

    "online-shop-payment": {
        "benchmark_name": "online-shop",
        "functions": {
            "paymentservice": [2, 3]
        },
        "entry_point": "paymentservice",
        "port": 80
    },

    "online-shop-productcatalogservice": {
        "benchmark_name": "online-shop",
        "functions": {
            "productcatalogservice": [3, 3]
        },
        "entry_point": "productcatalogservice",
        "port": 80
    },

    "online-shop-shippingservice": {
        "benchmark_name": "online-shop",
        "functions": {
            "shippingservice": [3, 3]
        },
        "entry_point": "shippingservice",
        "port": 80
    },

    "online-shop-checkoutservice": { #not working
        "benchmark_name": "online-shop",
        "functions": {
            "checkoutservice": [3, 3]
        },
        "entry_point": "checkoutservice",
        "port": 80
    },

    "hotel-app-geo-tracing": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-geo-tracing": [2, 5]
        },
        "entry_point": "hotel-app-geo-tracing",
        "port": 80
    },

    "hotel-app-geo": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-geo": [2, 5]
        },
        "entry_point": "hotel-app-geo",
        "port": 80
    },

    "hotel-app-profile": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-profile": [2, 5]
        },
        "entry_point": "hotel-app-profile",
        "port": 80
    },

    "hotel-app-rate": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-rate": [2, 5]
        },
        "entry_point": "hotel-app-rate",
        "port": 80
    },

    "hotel-app-recommendation": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-recommendation": [3, 15]
        },
        "entry_point": "hotel-app-recommendation",
        "port": 80
    },

    "hotel-app-reservation": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-reservation": [2, 5]
        },
        "entry_point": "hotel-app-reservation",
        "port": 80
    },

    "hotel-app-user": {
        "benchmark_name": "hotel-app",
        "functions": {
            "hotel-app-user": [2, 5]
        },
        "entry_point": "hotel-app-user",
        "port": 80
    }
}

def main(args):
    with open(args.filename, "w", newline = '') as file:
        writer = csv.writer(file)
        writer.writerow(["rps", "50%", "90%", "99%", "completerate"])
        file.close()
    env = Env(args.serverconfig)
    env.enable_env()
    benchmark = kDemoDeploymentActions[args.benchmark]['benchmark_name'] #benchmark
    functions = kDemoDeploymentActions[args.benchmark]['functions'] #functions
    rps = (int)(args.min)
    fiftylatencies = 0
    ninetylatencies = 0
    ninetyninelatencies = 0

    while rps<=(int)(args.max):
        for x in range((int)(args.numruns)):
            # Exec demo configuration.
            # Deploy.
            ret = env.deploy_application(benchmark, functions)
            if ret == EnvStatus.ERROR:
                assert False

            # Invoke.
            (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename = \
                env.invoke_application(
                    benchmark,
                    kDemoDeploymentActions[args.benchmark]['entry_point'],
                    {'port': kDemoDeploymentActions[args.benchmark]['port'], 'duration': args.duration, 'rps': rps}) #changed rps will be here

            # Sample env.
            env_state = env.sample_env(args.duration)
            lat_stat = env.get_latencies(stat_lat_filename)
            lat_stat.sort()
            print(stat_real_rps)
            print(stat_target_rps)
            fiftylatencies = (lat_stat[(int)(len(lat_stat)*0.5)]) #50th
            ninetylatencies = (lat_stat[(int)(len(lat_stat)*0.9)]) #90th latency
            ninetyninelatencies = (lat_stat[(int)(len(lat_stat)*0.99)]) #99th
            completed = str(stat_real_rps) + "/" + str(stat_target_rps)
            with open(args.filename, "a", newline = '') as file:
                writer = csv.writer(file)
                writer.writerow([rps, fiftylatencies, ninetylatencies, ninetyninelatencies, completed])
                file.close()

        rps+=(int)(args.step)
            

#
# Example cmd:
#   python3 datacollect.py --serverconfig server_configs.json --benchmark online-shop-currency --duration 10 --numruns 5 --min 1 --max 10 --step 1 --filename online-shop-currency-5.csv
#
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--serverconfig')
    parser.add_argument('--benchmark')
    parser.add_argument('--duration')
    parser.add_argument('--numruns')
    parser.add_argument('--min')
    parser.add_argument('--max')
    parser.add_argument('--step')
    parser.add_argument('--filename')
    args = parser.parse_args()

    main(args)

