import os
import argparse
import yaml
import json
import time
import re
import csv
import numpy as np

from os import path
from subprocess import run, Popen, PIPE
from pprint import pprint
from kubernetes import client, config
from prometheus_api_client import PrometheusConnect

from setup_service import Service
from setup_deployment import Deployment

class Env:
    def __init__(self, config_file):
        # Configs can be set in Configuration class directly or using helper
        # utility. If no argument provided, the config will be loaded from
        # default location.
        config.load_kube_config()

        # Initialize vars
        self.api = client.AppsV1Api()

        # Load and parse json config file.
        with open(config_file, 'r') as f:
            self.json_data = json.load(f)
        self.name = self.json_data['name']
        self.depl_file = self.json_data['depl_file']
        self.svc_file = self.json_data['svc_file']

        # Load YAML files as JSON-formatted dictionaries
        with open(path.join(path.dirname(__file__), self.depl_file)) as f:
            self.dep = yaml.safe_load(f)
        with open(path.join(path.dirname(__file__), self.svc_file)) as f:
            self.svc = yaml.safe_load(f)
            self.port = self.svc['spec']['ports'][0]['port']

        # Instantiate Deployment and Service objects
        self.deployment = Deployment(self.name, self.dep, self.api)
        self.service = Service(self.name, self.svc_file)

        # Some extra vars for later use
        self.total_mem_ = None

    # Create Deployment and Service, setup Prometheus.
    def setup(self, wait_time=5):
        # Create Deployment
        try:   
            self.deployment.create_deployment()
        except Exception as e:
            print('\n[ERROR] Previous Deployments may still be deleting...')
            print(f'\n[ERROR] {e}')
            return 0
        print(f"[INFO] Waiting for {wait_time} seconds while Deployment is being created")
        time.sleep(wait_time)

        # Create Service
        self.service.create_service()
        print(f"[INFO] Service can be invoked at IP: {self.service.get_service_ip()} at port {self.port}\n")

        # Setup Prometheus on all nodes
        # Get node hostnames as appears in knative.
        node_cmd = '''kubectl get nodes | awk '{print $1}' '''
        stdout = run(node_cmd, capture_output=True, shell=True, universal_newlines=True).stdout
        ret = stdout.split('\n')[1:-1]

        # Worker ids start from 1, also skip the first node as it is a Master.
        ret = ret[1:]
        self.k_worker_hostnames_ = {}
        for i in range(len(ret)):
            self.k_worker_hostnames_[i + 1] = ret[i]

        # Setup Prometheus.
        self.k_worker_metrics_ = {}
        for v_id, v_hostname in self.k_worker_hostnames_.items():
            self.k_worker_metrics_[v_id] = PrometheusConnect(
                url=f'http://{v_hostname}:9090/', disable_ssl=True)

        # Print some env stats.
        print("[INFO] Env is initialized, some stats: ")
        print("[INFO] Worker node names: ", self.k_worker_hostnames_)
        print("[INFO] Number of available metrics for workers: ", {
              k: len(v.all_metrics()) for k, v in self.k_worker_metrics_.items()})
        print()

        return 1

    # Get number of worker nodes
    def get_worker_num(self):
        return len(self.k_worker_hostnames_)
    


    # Invoke Service using invoker and return stats
    def invoke_service(self):
        ip = self.service.get_service_ip()
        invoker_file = '~/vSwarm/tools/invoker'

        # Get invoker configs
        invoke_params = self.json_data['invoker_configs']

        # Setup hostname file
        os.system('''echo '[ { "hostname": "''' + ip + '''" } ]' > ''' + invoker_file + '''endpoints.json''')
        print(f"[INFO] Hostname file has been set up at {invoker_file}/endpoints.json")

        # Format the invoker command nicely
        invoker_cmd_join_list = [f'{invoker_file}/invoker',
                                '-dbg',
                                f'-port {self.port}',
                                f'-time {invoke_params["duration"]}',
                                f'-rps {invoke_params["rps"]}',
                                f'-endpointsFile {invoker_file}/endpoints.json']
        invoker_cmd = ' '.join(invoker_cmd_join_list)

        # Run invoker while redirecting output to separate file
        print("[INFO] Invoking with command", f'`{invoker_cmd}`\n')
        stdout = os.popen(invoker_cmd)

        # Find latency file and parse stats
        stat_issued = None
        stat_completed = None
        stat_real_rps = None
        stat_target_rps = None
        stat_lat_filename = None
        for line in stdout:
            m = re.search('The measured latencies are saved in (.*csv)', line)
            if m:
                stat_lat_filename = m.group(1)
            m = re.search('completed requests: ([0-9]*), ([0-9]*)', line)
            if m:
                stat_issued = (int)(m.group(1))
                stat_completed = (int)(m.group(2))
            m = re.search(
                'target RPS: ([0-9]*\.?[0-9]*) \/ ([0-9]*\.?[0-9]*)', line)
            if m:
                stat_real_rps = (float)(m.group(1))
                stat_target_rps = (float)(m.group(2))

        # Return run stats.
        return (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename

    # Get latencies given the stat file
    def get_latencies(self, latency_stat_filename):
        lat = []
        with open(latency_stat_filename) as f:
            csv_reader = csv.reader(f, delimiter=' ', quotechar='|')
            for row in csv_reader:
                lat.append((float)(', '.join(row)))
        return lat

    # Get cluster runtime stats, such as CPU/mem/network utilization over the past @param interval_sec
    # Returns: {worker_id: {'cpu': [idel, user, system], 'net': [tx, rx], 'mem': free}}
    def sample_env(self):
        interval_sec = self.json_data['invoker_configs']['duration']
        ret = {}
        for p_id, p_metric in self.k_worker_metrics_.items():
            tpl = {}

            # CPU-related metrics
            # Average CPU idle cycles for all CPUs, [0-1]
            cpu_idle = (float)(p_metric.custom_query(
                query=f'avg(rate(node_cpu_seconds_total{{mode="idle"}}[{interval_sec}s]))')[0]['value'][1])
            # Average CPU user cycles for all CPUs, [0-1]
            cpu_user = (float)(p_metric.custom_query(
                query=f'avg(rate(node_cpu_seconds_total{{mode="user"}}[{interval_sec}s]))')[0]['value'][1])
            # Average CPU system cycles for all CPUs, [0-1]
            cpu_system = (float)(p_metric.custom_query(
                query=f'avg(rate(node_cpu_seconds_total{{mode="system"}}[{interval_sec}s]))')[0]['value'][1])
            #
            tpl['cpu'] = [cpu_idle, cpu_user, cpu_system]

            # Network-related metrics
            # Sum of the total network throughput for all devices, bps
            network_rx_bps = (float)(p_metric.custom_query(
                query=f'sum(rate(node_network_receive_bytes_total[{interval_sec}s]))')[0]['value'][1]) * 8
            network_tx_bps = (float)(p_metric.custom_query(
                query=f'sum(rate(node_network_transmit_bytes_total[{interval_sec}s]))')[0]['value'][1]) * 8
            #
            tpl['net'] = [network_tx_bps, network_rx_bps]

            # Memory-related metrics
            # Free memory, Bytes
            mem_free = p_metric.custom_query(
                query=f'node_memory_MemAvailable_bytes[{interval_sec}s]')[0]['values']
            mem_free = np.array([(int)(val) for (_, val) in mem_free])
            mem_free_avg = np.average(mem_free)

            # Total memory, look-up 1 time and cache
            if self.total_mem_ == None:
                self.total_mem_ = (int)(p_metric.custom_query(
                    query=f'node_memory_MemTotal_bytes')[0]['value'][1])

            #
            mem_free_frac = mem_free_avg / (float)(self.total_mem_)
            tpl['mem'] = mem_free_frac

            # Append all metrics for this worker
            ret[p_id] = tpl

        return ret

    
    # Scale number of replicas
    def scale_deployment(self, replicas, wait_time=5):
        self.deployment.scale_deployment(replicas)
        # Wait for replicas to become ready
        print(f"[INFO] Waiting {wait_time} seconds for replicas to become ready...\n")
        time.sleep(wait_time)

    # Delete Deployment when finished
    def delete_deployment(self):
        self.deployment.delete_deployment()