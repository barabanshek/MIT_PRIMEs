from multiprocessing import Process, Manager
import random

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
        sampled_env_state = self.env.sample_env(t)
        # Unpack the env state so that it's [(cpu_idle, cpu_user, cpu_system, mem_free, net_transmit, net_receive)]
        unpacked_env_state = unpack_env_state(sampled_env_state)
        return unpacked_env_state
    
    def get_lats(self, benchmark, t, lats):
        (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename = \
                        self.env.invoke_service(benchmark.entry_service, t, benchmark.rps)
        lat_stat = self.env.get_latencies(stat_lat_filename)
        if lat_stat == []:
            print('no latencies')
            return
        lat_stat.sort()
        lat_50 = lat_stat[(int)(len(lat_stat) * 0.5)]
        lat_90 = lat_stat[(int)(len(lat_stat) * 0.90)]
        lat_99 = lat_stat[(int)(len(lat_stat) * 0.99)]
        lat_999 = lat_stat[(int)(len(lat_stat) * 0.999)]
        lats[benchmark.name] = (lat_50, lat_90, lat_99, lat_999)
        
    # Update each deployment with the corresponding action.
    # For example, if `deployments`=(fibonacci, hotel-app-geo) and `actions`=(1, -1)
    # then fibonacci will be scaled up by 1 and hotel-app-geo will be scaled down by 1.
    def scale_with_action(self, action, deployment):
        replicas = deployment.deployment_object.spec.replicas
        replicas = max(1, replicas + action)
        print(f'Scaling {deployment.deployment_name} to {replicas} replicas...')
        self.env.scale_deployments(deployment, replicas)
           
    def scale_and_get_lats(self, benchmark, action, t, lats):
        print(f"Taking action for {benchmark.name}...") 
        # NOTE: Update this when using chained functions or benchmarks with more than 1 deployment.
        self.scale_with_action(action, benchmark.deployments[0])
        self.get_lats(benchmark, t, lats)
        
    # Take the action and get the latencies for a given time.
    def evaluate_action(self, action_set, t):
        print(f'ACTION SET: {action_set}')
        with Manager() as manager:
            processes = []
            lats = manager.dict()
            for benchmark, action in zip(self.benchmarks, action_set):
                # Scale each deployment in parallel.
                p = Process(target=self.scale_and_get_lats, args=(benchmark, action, t, lats))
                processes.append(p)
                p.start()
            for proc in processes:
                proc.join() 
            lats = dict(lats)
            return lats
    # TODO: update
    def check_termination(self):
        return False
    
    # TODO: update
    def check_truncation(self):
        return False
