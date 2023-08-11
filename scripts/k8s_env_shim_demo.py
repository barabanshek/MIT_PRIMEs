import argparse
from k8s_env_shim import Env
from pprint import pprint

def main(args):
    # Instantiate Env.
    env = Env(args.config)

    # Check if setup is successful. If not, attempt to delete existing deployment.
    if not env.setup():
        env.delete_deployment()
        print("[ERROR] Setup failed, please read error message and try again.")
        return 0
    
    # Invoke.
    (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename = \
        env.invoke_service()
    lat_stat = env.get_latencies(stat_lat_filename)
    if lat_stat == []:
        print("No responses were returned, no latency statistics is computed.")
        return
    
    # Sample env.
    env_state = env.sample_env()
    lat_stat = env.get_latencies(stat_lat_filename)
    if lat_stat == []:
        print("No responses were returned, no latency statistics is computed.")
        return

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

    # Scale up pod replicas.
    env.scale_deployment(5)

    # Invoke again.
    (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename = \
        env.invoke_service()
    lat_stat = env.get_latencies(stat_lat_filename)
    if lat_stat == []:
        print("No responses were returned, no latency statistics is computed.")
        return
    
    # Sample env.
    env_state = env.sample_env()
    lat_stat = env.get_latencies(stat_lat_filename)
    if lat_stat == []:
        print("No responses were returned, no latency statistics is computed.")
        return

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

    # Delete deployment when finished.
    env.delete_deployment()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--config')
    args = parser.parse_args()
    main(args)