from k8s_env_shim import Env
import json
import yaml
import os

from yaml.loader import SafeLoader
from os import path
from pprint import pprint
from setup_service import Service
from setup_deployment import Deployment
import random
import math

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
        lat_stat.append(latencyqos*10)
    
    return (stat_completed/stat_issued,  lat_stat[(int)(len(lat_stat) * 0.90)])


class RLEnv:
    initial_cpu_lim = 1000 #milicores
    initial_mem_lim = 2000 #MiB

    states = {
        "cpu_user" : 0,
        "mem_free" : 0,
        "cpu_limit" : 0,
        "mem_limit" : 0,
        "replicas" : 0
    }

    deployments = []
    services = []

    cpu_step = 30
    mem_step = 100
    replicas_step = 1

    functions = {}
    rps = {}
    durations = {}
    def __init__(self, config):
        self.states['cpu_limit'] = self.initial_cpu_lim
        self.states['mem_limit'] = self.initial_mem_lim
        self.env = Env()
        with open(config, 'r') as f:
            json_data = json.load(f)
        
        benchmarks = json_data['benchmarks']

        self.entry_point_function = []
        self.functions = []
        self.entry_point_function_index = {}

        self.deployments = []
        self.services = []
        index = 0
        for benchmark in benchmarks:
            # Read configs for benchmark
            self.functions.append(benchmark['name'])
            self.entry_point_function.append(benchmark['entry-point'])
            functions = benchmark['functions']
            self.entry_point_function_index.update({benchmark['entry-point']: index})

            for function in functions:
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
            
            index += 1

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
        state = self.env.sample_env(time)
        self.states["cpu_user"] = state[1]["cpu"][1]
        self.states["mem_free"] = state[1]["mem"]

    def invokefunction(self, time, rps, entrypoint):
        entry_service = self.services[self.entry_point_function_index[entrypoint]]
        complete_rate, latency = run_service(self.env, entry_service, {'duration' : time, "rps": rps})
        return latency, complete_rate

    def executeaction(self, action): #[cpu, mem]
        cpu = action%3 - 1
        #mem = (action//3) % 3 - 1
        #replica = (action//9) - 1
        oldcpu = self.states["cpu_limit"]
        self.states["cpu_limit"] += (cpu*self.cpu_step)
        #self.states["mem_limit"] += (mem*self.mem_step)
        #self.states["replicas"] += (replica*self.replicas_step)
        if self.states["cpu_limit"]<=0:
            self.states["cpu_limit"] = 20 #default
        
        if self.states["mem_limit"]<=0:
            self.states["mem_limit"] = 100 #default
        
        if self.states["replicas"]<=0:
            self.states["replicas"] = 1 #default
        if self.states["replicas"]>5:
            self.states["replicas"] = 5 #overflow i think
        try:
            self.env.scale_pods(self.deployments, (str)(str(self.states["cpu_limit"]) + "m"), (str)(str(self.states["mem_limit"]) + "Mi"))
            self.env.scale_deployments(self.deployments, (int)(self.states["replicas"]))
        except:
            print("pods failed to scale")
            self.states["cpu_limit"] = oldcpu


    def reset(self): #default params
        self.states["cpu_user"] = 0
        self.states["mem_free"] = 0
        self.states["cpu_limit"] = 100
        self.states["mem_limit"] = 500
        self.states["replicas"] = 1
        self.env.scale_pods(self.deployments, (str)(str(self.states["cpu_limit"]) + "m"), (str)(str(self.states["mem_limit"]) + "Mi"))
        self.env.scale_deployments(self.deployments, (int)(self.states["replicas"]))
        return list(self.states.values())
    
    def step(self, action, rps, duration, entrypoint):
        self.executeaction(action)
        latency, complete_rate = self.invokefunction(duration, rps, entrypoint) #self.invokefunction(time, random.randint(100, 400))

        self.observestates(duration)
        reward = 0
        reward = (2 * ((complete_rate) + max((1-latency/latencyqos), 0)) - 2.5*(self.states["cpu_user"]*10)) # + ((min((self.states["cpu_user"]*10000/self.states["cpu_limit"]), 1))**3 + (min((((1-self.states["mem_free"])*625)/self.states["mem_limit"]), 1))**3) 
        if latency == latencyqos*10:
            reward -= 2
        return list(self.states.values()), reward, latency, complete_rate