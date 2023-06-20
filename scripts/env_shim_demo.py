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
# 90th pct latency
tail_lat = None

def main(args):

    env = Env(args.serverconfig)
    env.enable_env()
    agent = EpsilonGreedyAgent()
    agent.num_actions = 3#0 for subtract 1 rps, 1 for add 0 rps, 2 for add 1 rps
    agent.states = 20
    agent.reset()
    benchmark = kDemoDeploymentActions[args.benchmark]['benchmark_name'] #benchmark
    functions = kDemoDeploymentActions[args.benchmark]['functions'] #functions
    rewards = []
    minmaxcontainer = 5 #initial rps
    actiontaken = []
    for ppp in range(int(args.numruns)):
        print(ppp)
        state = minmaxcontainer
        action = agent.get_action(state) #this will be 0 or 1 2
        minmaxcontainer += (float)(action-1)
        actiontaken.append(minmaxcontainer)
        if minmaxcontainer<=0:
            minmaxcontainer = 1
            reward = -100
            rewards.append(reward)
            print(reward)
            agent.update_Q(action, state, reward)
            continue
        # Exec demo configuration.
        # Deploy.
        benchmark["functions"]["decoder"][1] = minmaxcontainer
        benchmark["functions"]["recog"][1] = minmaxcontainer
        benchmark["functions"]["streaming"][1] = minmaxcontainer
        ret = env.deploy_application(benchmark, functions)
        if ret == EnvStatus.ERROR:
            assert False

        # Invoke.
        (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename = \
            env.invoke_application(
                benchmark,
                kDemoDeploymentActions[args.benchmark]['entry_point'],
                {'port': kDemoDeploymentActions[args.benchmark]['port'], 'duration': args.duration, 'rps': args.rps}) #changed rps will be here

    # Sample env.
    env_state = env.sample_env(args.duration)
    lat_stat = env.get_latencies(stat_lat_filename)
    lat_stat.sort()
    tail_lat = lat_stat[(int)(len(lat_stat) * 0.90)]


        # Print statistics.
        #print(f'    stat: {stat_issued}, {stat_completed}, {stat_real_rps}, {stat_target_rps}, latency file: {stat_lat_filename}')
        #print('    50th: ', lat_stat[(int)(len(lat_stat) * 0.5)])
        #print('    90th: ', lat_stat[(int)(len(lat_stat) * 0.90)])
        #print('    99th: ', lat_stat[(int)(len(lat_stat) * 0.99)])
        #print('    99.9th: ', lat_stat[(int)(len(lat_stat) * 0.999)])
        #print('    env_state:', env_state)

        # make up a reward
    net = 0
    for x in range(3): #3 nodes
        net+=abs(env_state[x+1]['net'][0]-env_state[x+1]['net'][1])

    reward = -math.log10(lat_stat[(int)(len(lat_stat) * 0.9)]*net)
    rewards.append(reward)
    print('    90th: ', lat_stat[(int)(len(lat_stat) * 0.90)])
    print('netdiff', net)
    print(reward)
    agent.update_Q(action, state, reward)
    
    #graph the rewards

    plot(rewards)
    plot(actiontaken)
    plt.show()





#
# Example cmd:
#   python3.11 env_shim_demo.py --serverconfig server_configs.json --benchmark video-analytics --duration 10 --rps 5 --numruns 10
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


#env_state: {
#1: 
#{'cpu': [0.8438888888888869, 0.127, 0.011833333333333335], 
#'net': [645766256.0000001, 527176501.5208889], 
#'mem': 0.950110926376932}, 
#2: 
#{'cpu': [0.7837777777777768, 0.18339798750000005, 0.009833333333333333], 
#'net': [396424719.11111104, 547077626.6666667], 
#'mem': 0.9557290834384151}, 
#3: 
#{'cpu': [0.9563333333333333, 0.013277777777777763, 0.012500000000000015], 
#'net': [76926091.55555557, 39071269.333333336], 
#'mem': 0.9623702859704296}}