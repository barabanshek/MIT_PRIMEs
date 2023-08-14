import argparse
from k8s_env_shim import Env
from pprint import pprint

# Run the benchmark and print stats
def run_service(env):
    # Invoke.
    (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename = \
        env.invoke_service()
    lat_stat = env.get_latencies(stat_lat_filename)
    if lat_stat == []:
        print("[ERROR] No responses were returned, no latency statistics is computed.")
        return
    
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

def main(args):
    # Instantiate Env.
    env = Env(args.config)


    # Check if Prometheus setup is successful.
    if not env.setup_prometheus():
        print("[ERROR] Prometheus setup failed, please read error message and try again.")
        return 0

    # Check if benchmark setup is successful. If not, attempt to delete existing deployment.
    if not env.setup_benchmark():
        env.delete_deployment()
        print("[ERROR] Benchmark setup failed, please read error message and try again.")
        return 0

    run_service(env)

    # Scale up pod replicas.
    env.scale_deployment(1)

    run_service(env)

    # Delete deployment when finished.
    env.delete_deployment()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--config')
    args = parser.parse_args()
    main(args)

# JSON config
# {
#     "benchmarks" :
#     {
#         "entry_point" : 0,
#         "names" : ["streaming", "decoder", "recog"],
#         "deployment_files" : ["streaming-deployment.yml", "decoder-deployment.yml", "recog-deployment.yml"],
#         "service_files" : ["streaming-service.yml", "decoder-service.yml", "recog-service.yml"],
#         "invoker_configs" : {
#             "duration" : 10,
#             "rps" : 5
#         }
#     }
# }