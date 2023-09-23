from k8s_env_shim import Env
import json
import yaml


from yaml.loader import SafeLoader
from os import path
from pprint import pprint
from setup_service import Service
from setup_deployment import Deployment
import random

steptime = 5
latencyqos = 400000

def run_service(env, service, invoker_configs):
    # Get invoker configs.
    duration = invoker_configs['duration']
    rps = invoker_configs['rps']
    # Invoke.
    (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename = \
        env.invoke_service(service, duration, rps)
    lat_stat = env.get_latencies(stat_lat_filename)
    if lat_stat == []:
        print("[ERROR] No responses were returned, no latency statistics is computed.")
        return
    
    return (stat_issued/stat_completed,  lat_stat[(int)(len(lat_stat) * 0.90)])


class RLEnv:
    initial_cpu_lim = 1000 #milicores
    initial_mem_lim = 2000 #MiB

    server = Env()

    states = {
        "cpu_user" : 0,
        "mem_free" : 0,
        "90_latency" : 0,
        "completion_rate" : 0,
        "cpu_limit" : 0,
        "mem_limit" : 0
    }

    actions = {
        "cpu" : 0,
        "mem" : 0
    }

    deployments = []
    services = []

    def __init__(self, config):
        self.states['cpu_limit'] = self.initial_cpu_limit
        self.states['memory_limit'] = self.initial_memory_limit

        with open(config, 'r') as f:
            json_data = json.load(f)

        self.entry_point_function = json_data['entry-point']
        self.functions = json_data['functions']
        self.invoker_configs = json_data['invoker-configs']
        self.entry_point_function_index = self.functions.index(self.entry_point_function)

        # Load YAML files as JSON-formatted dictionaries
        for function in self.functions:
            # Instantiate Deployment objects
            file_name = f"k8s-yamls/{function}.yaml"
            with open(path.join(path.dirname(__file__), file_name)) as f:
                dep, svc = yaml.load_all(f, Loader=SafeLoader)
            deployment = Deployment(dep, self.env.api)
            self.deployments.append(deployment)

            # Instantiate Service objects
            port = svc['spec']['ports'][0]['port']
            service = Service(function, file_name, port)
            self.services.append(service)

        # Check if Prometheus setup is successful.
        if not self.env.setup_prometheus():
            print("[ERROR] Prometheus setup failed, please read error message and try again.")
            return 0

        # Check if benchmark setup is successful. If not, attempt to delete existing deployments.
        if not self.env.setup_functions(self.deployments, self.services):
            self.env.delete_functions(self.services)
            print("[ERROR] Benchmark setup failed, please read error message and try again.")
            return 0

    def observestates(self, time): #currently for 1 machine
        states = self.server.observestates(time)
        self.states["cpu_user"] = states['1']["cpu"][1]
        self.states["mem_free"] = states['1']["mem"]

    def invokefunction(self, time, rps):
        entry_service = self.services[self.entry_point_function_index]
        complete_rate, latency = run_service(self.env, entry_service, {'duration' : time, "rps": rps})
        self.states["90_latency"] = latency,
        self.states["completion_rate"] = complete_rate

    def executeaction(self, action): #[cpu, mem]
        self.server.scale_pods(self.deployments, str(action[0]) + "m", str(action[1]) + "Mi")

    def step(self, action):
        self.executeaction(action)
        time = random.randint(10, 20)
        self.invokefunction(time, random.randint(100, 400))
        self.observestates(time)
        reward = self.states["cpu_user"]*100/self.states["cpu_limit"]+self.states["mem_free"]*1000000/self.states["mem_limit"]+(-self.states["90_latency"]/latencyqos + self.states["completion_rate"])
        return self.states, reward