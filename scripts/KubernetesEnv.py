from multiprocessing import Process, Manager
import random
import time
import signal
from pprint import pprint
from subprocess import run
from itertools import count
# Register a handler for timeouts
def timeout_handler(signum, frame):
    raise Exception("[ERROR] timeout limit exceeded.\n")

# Register signal function handler
signal.signal(signal.SIGALRM, timeout_handler)

# Stop the Horizontal Pod Autoscaler from scaling.
def freeze_autoscaler(name, replicas):
    # Set minReplicas and maxReplicas equal to the given replicas
    set_scale_cmd = '''kubectl patch hpa ''' + name + ''' --patch '{"spec":{"maxReplicas":''' + str(replicas) + '''}}'\n
            kubectl patch hpa ''' + name + ''' --patch '{"spec":{"minReplicas":''' + str(replicas) + '''}}' '''
    ret = run(set_scale_cmd, capture_output=True, shell=True, universal_newlines=True)
    if ret.returncode != 0:
        assert False, f"\n[ERROR] Failed to run command `{set_scale_cmd}`\n[ERROR] Error message: {ret.stderr}"
        
def print_env_state(unpacked_env_state):
    for node_i in range(len(unpacked_env_state)):
        print(f"        Node {node_i + 1}:")
        print("            CPU Usage:")
        print(f"                Idle: {round(100*unpacked_env_state[node_i][0], 6)} %")
        print(f"                User: {round(100*unpacked_env_state[node_i][1], 6)} %")
        print(f"                System: {round(100*unpacked_env_state[node_i][2], 6)} %")
        print("            Memory Usage:")
        print(f"                Free: {round(100*unpacked_env_state[node_i][3], 6)} %")
        print("            Network Throughput (bps):")
        print(f"                Transmit: {unpacked_env_state[node_i][4]}")
        print(f"                Receive: {unpacked_env_state[node_i][5]}")

def unpack_env_state(env_state):
    ret = []
    for k in env_state.keys():
        cpu_idle = env_state[k]['cpu'][0]
        cpu_user = env_state[k]['cpu'][1]
        cpu_system = env_state[k]['cpu'][2]
        mem_free = env_state[k]['mem']
        net_transmit = env_state[k]['net'][0]
        net_receive = env_state[k]['net'][1]
        ret.append((cpu_idle, cpu_user, cpu_system, mem_free, net_transmit, net_receive))
    return ret

class Benchmark():
    def __init__(self, name, deployments, services, entry_point_i, sla, rps_range):
        self.name = name
        self.deployments = deployments
        self.services = services
        self.sla = sla
        self.entry_service = services[entry_point_i]
        self.rps_range = rps_range
        self.rps = random.randint(self.rps_range[0], self.rps_range[1])
        self.replicas = 1
    def update_replicas(self):
        get_replicas_cmd = f"kubectl get deployment/{self.services[0].name} -o jsonpath='{{.spec.replicas}}'"
        self.replicas = int(run(get_replicas_cmd, shell=True, capture_output=True, universal_newlines=True).stdout)
        return self.replicas
    def set_replicas(self, target_replicas):
        self.replicas = target_replicas
    
class KubernetesEnv():
    """Env class that serves as API between RLEnv and env_shim.
    
    - Attributes:
        - `env` (Env) : env_shim API.
        - `benchmarks` (List[Benchmark]) : list of the environment's benchmarks.
        - `t` (Int) : time interval of invocation.
    - Methods:
        - `get_env_state` (Int) : sample k8s environment and return the env state as a Dict
            - Returns a Dict
        - `get_lats` (Benchmark, Int, Dict) : invoke a function and add all the latencies to the latency dictionary.
            - Returns a List
        - `evaluate_action` (List[Any]) : update each deployment with the corresponding action.
            - Returns nothing
        - `check_termination` : check if the environment has reached a termination state (e.g. crashing)
            - Returns a boolean
        - check_truncation` : check if the environment has reached a truncation state (e.g. a user-defined timeout limit)
            - Returns a boolean 
    """
    def __init__(self, env, benchmarks):
        self.env = env
        self.benchmarks = benchmarks
                    
    def get_env_state(self, t):
        try:
            sampled_env_state = self.env.sample_env(t)
        except Exception as e:
            print('Failed to sample Env.')
            print(f'Error: {e}')
            assert False
        # Unpack the env state so that it's [(cpu_idle, cpu_user, cpu_system, mem_free, net_transmit, net_receive)]
        unpacked_env_state = unpack_env_state(sampled_env_state)
        return unpacked_env_state
    
    def get_lats(self, benchmark, t, lats):
        print(f'Invoking benchmark {benchmark.name}...')
        (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename = \
                        self.env.invoke_service(benchmark.entry_service, t, benchmark.rps)
        lat_stat = self.env.get_latencies(stat_lat_filename)
        if lat_stat == []:
            print(f'>>> ERROR: no latencies for {benchmark.name}')
            return
            
        lat_stat.sort()
        lat_50 = lat_stat[(int)(len(lat_stat) * 0.5)]
        lat_90 = lat_stat[(int)(len(lat_stat) * 0.90)]
        lat_99 = lat_stat[(int)(len(lat_stat) * 0.99)]
        lat_999 = lat_stat[(int)(len(lat_stat) * 0.999)]
        if self.env.verbose:
            print(f"[INFO] Invocation statistics for benchmark `{benchmark.name}`:\n")
            print(
                f'    stat: {stat_issued}, {stat_completed}, {stat_real_rps}, {stat_target_rps}, latency file: {stat_lat_filename}')
            print('    50th: ', lat_50/1000, 'ms')
            print('    90th: ', lat_90/1000, 'ms')
            print('    99th: ', lat_99/1000, 'ms')
            print('    99.9th: ', lat_999/1000, 'ms')
        lats[benchmark.name] = (lat_50, lat_90, lat_99, lat_999)
        
    # Update each deployment with the corresponding desired replica count.
    def scale_with_action(self, desired, benchmark, timeout=60):
        # Get current replicas
        curr_replicas = benchmark.replicas
        # Update replica count
        target_replicas = desired
        # Define scale cmd.
        print(f'Scaling {benchmark.services[0].name} from {curr_replicas} to {target_replicas} replicas...')
        scale_cmd = f"kubectl scale deployment/{benchmark.services[0].name} --replicas={target_replicas}"
        # Scale.
        signal.alarm(timeout)
        start = time.time()
        ret = run(scale_cmd, shell=True, capture_output=True, universal_newlines=True)
        if ret.returncode != 0:
            assert False, f"\n[ERROR] Failed to scale {benchmark.services[0].name} to {target_replicas} replicas.`\n[ERROR] Error message: {ret.stderr}"
        print(f'Waiting to scale deployment `{benchmark.services[0].name}`...')
        # Wait to scale.
        while not benchmark.deployments[0].is_ready():
            continue
        # Cancel the timer when the replicas are ready
        signal.alarm(0)      
        print(f'Deployment `{benchmark.services[0].name}` successfully scaled in {round(time.time() - start, 3)} seconds.\n')
        
    # Take the action and get the latencies for a given time.
    def evaluate_action(self, action_set, t):
        print(f'ACTION SET: {action_set}')
        updated_counts = [max(self.benchmarks[i].replicas + action_set[i], 1) for i in range(len(action_set))]
        print(f'PROPOSED REPLICAS: {updated_counts}\n')
        # Scale each deployment in parallel.
        for c in count():
            print(f'Scale attempt {c+1}:')
            try:
                processes = []
                for benchmark, desired in zip(self.benchmarks, updated_counts):
                    p = Process(target=self.scale_with_action, args=(desired, benchmark))
                    processes.append(p)
                    p.start()
                # Join processes.
                for proc in processes:
                    proc.join()
            except Exception as e:
                print(f'Scale error: {e}')
                print('Scale failed: retrying...')
            else:
                print('>>> Scale success.\n')
                break
        # Update all benchmark objects.
        for benchmark in self.benchmarks:
            benchmark.update_replicas()
        print('All deployments successfully scaled.\n')
        # Invoke in parallel
        for c in count():
            print(f'Invocation attempt {c+1}:')
            try:
                with Manager() as manager:
                    lats = manager.dict()
                    processes = []
                    for benchmark in self.benchmarks:
                        p = Process(target=self.get_lats, args=(benchmark, t, lats))
                        processes.append(p)
                        p.start()
                    # Join processes.
                    for proc in processes:
                        proc.join()
                    lats = dict(lats)
                    print(lats)
                    if len(lats.keys()) != len(self.benchmarks):
                        print('Invocation error: insufficient latencies.')
                        assert False
                    print('>>> Invocation success.\n')
                    return lats
            except Exception as e:
                print(f'Invocation error: {e}')
                print('Invocation failed: retrying...')

    # TODO: update
    def check_termination(self):
        return False
    
    # TODO: update
    def check_truncation(self):
        return False
