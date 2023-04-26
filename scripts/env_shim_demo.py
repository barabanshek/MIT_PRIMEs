# This is just an example for using env_shim.
from env_shim import *

# Demo parameters.
kDemoDeploymentActions = {
    "fibonacci": {
        "benchmark_name": "fibonacci",
        "functions": {
            "fibonacci-python": [2, 2]
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
            "decoder": [1, 3],
            "recog": [2, 3],
            "streaming": [3, 3]
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
    lat_stat.sort()

    # Print statistics.
    print(
        f'    stat: {stat_issued}, {stat_completed}, {stat_real_rps}, {stat_target_rps}, latency file: {stat_lat_filename}')
    print('    50th: ', lat_stat[(int)(len(lat_stat) * 0.5)])
    print('    90th: ', lat_stat[(int)(len(lat_stat) * 0.90)])
    print('    99th: ', lat_stat[(int)(len(lat_stat) * 0.99)])
    print('    99.9th: ', lat_stat[(int)(len(lat_stat) * 0.999)])
    print('    env_state:', env_state)


#
# Example cmd:
#   python3 deploy_serverless.py --serverconfig server_configs.json --benchmark video-analytics --duration 10 --rps 5
#
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--serverconfig')
    parser.add_argument('--benchmark')
    parser.add_argument('--duration')
    parser.add_argument('--rps')
    args = parser.parse_args()

    main(args)
