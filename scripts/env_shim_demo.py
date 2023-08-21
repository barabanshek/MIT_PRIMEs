# This is just an example for using env_shim.
from env_shim import *

# Demo parameters.
kDemoDeploymentActions = {
    "fibonacci": {
        "benchmark_name": "fibonacci",
        "functions": [
            { "fibonacci-python": {'node' : 1, 'containerScale' : 1, 'containerConcurrency' : 10}},
            { "fibonacci-python": {'node' : 1, 'containerScale' : 2, 'containerConcurrency' : 10}}
            ],
        "entry_point": "fibonacci-python",
        "port": 80
    }
}

def main(args):
    env = Env(args.serverconfig)
    env.enable_env()

    # Exec demo configuration.
    # Deploy.
    env.deploy_all_revisions(kDemoDeploymentActions[args.benchmark]['benchmark_name'], kDemoDeploymentActions[args.benchmark]['functions'])
    # ret = env.deploy_application(
    #     kDemoDeploymentActions[args.benchmark]['benchmark_name'], kDemoDeploymentActions[args.benchmark]['functions'])
    # if ret == EnvStatus.ERROR:
    #     assert False

    env.split_traffic('fibonacci-python', 1)
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
    tail_lat = lat_stat[(int)(len(lat_stat) * 0.90)]


    # Print statistics.
    print(
        f'    stat: {stat_issued}, {stat_completed}, {stat_real_rps}, {stat_target_rps}, latency file: {stat_lat_filename}')
    print('    50th: ', lat_stat[(int)(len(lat_stat) * 0.5)])
    print('    90th: ', lat_stat[(int)(len(lat_stat) * 0.90)])
    print('    99th: ', lat_stat[(int)(len(lat_stat) * 0.99)])
    print('    99.9th: ', lat_stat[(int)(len(lat_stat) * 0.999)])
    print('    env_state:', env_state)

    env.split_traffic('fibonacci-python', 2)

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

    env.split_traffic('fibonacci-python', 1)

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
    tail_lat = lat_stat[(int)(len(lat_stat) * 0.90)]


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
