import os
import json
import re
import csv
import numpy as np
import time
import signal

from os import path
from subprocess import run
from pprint import pprint
from kubernetes import client, config
from prometheus_api_client import PrometheusConnect

INVOKER_FILE = '~/vSwarm/tools/invoker/'

# Register a handler for timeouts
def timeout_handler(signum, frame):
    raise Exception("[ERROR] timeout limit exceeded.\n")

class Env:
    def __init__(self, verbose=False):
        # Configs can be set in Configuration class directly or using helper
        # utility. If no argument provided, the config will be loaded from
        # default location.
        config.load_kube_config()

        # Register signal function handler
        signal.signal(signal.SIGALRM, timeout_handler)

        # Initialize vars
        self.api = client.AppsV1Api()

        # Verbosity
        self.verbose = verbose

        # Some extra vars for later use
        self.total_mem_ = None

    # Setup Prometheus
    def setup_prometheus(self):
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
        print("[UPDATE] Env is initialized, some stats: ")
        print("[INFO] Worker node names: ")
        pprint(self.k_worker_hostnames_)
        print("[INFO] Number of available metrics for workers: ", {
              k: len(v.all_metrics()) for k, v in self.k_worker_metrics_.items()})
        print()
        return 1

    # Create Deployments and Service.
    # timeout : timeout limit for each deployment
    def setup_functions(self, deployments, services, wait_to_scale=True, timeout=60):

        # Create Deployments    
        for deployment, service in zip(deployments, services):
            # Start the timer
            signal.alarm(timeout)
            try:
                deployment.create_deployment()
            except Exception as e:
                # print('\n[ERROR] Previous Deployments may still be deleting...')
                print(f'\n[ERROR] {e}')
                return 0
            try:
                if wait_to_scale:
                    if self.verbose:
                        print(f"[RUNNING] Waiting for all pods in Deployment to be ready")
                    t_start = time.time()
                    while not deployment.is_ready():
                        continue
                    # Cancel the timer when the Deployment is ready
                    signal.alarm(0)   
                    if self.verbose:             
                        print(f"[UPDATE] Deployment {deployment.deployment_name} successfully rolled out in {round(time.time() - t_start, 3)} seconds.\n")
            except:
                assert False, f"\n[ERROR] Deployment {deployment.deployment_name} deployment time exceeded timeout limit."
            # Create Service
            service.create_service()
            if not self.verbose:
                print(f"[INFO] Service can be invoked at IP: {service.get_service_ip()} at port {service.port}\n")
        return 1
    
    # Scale number of replicas
    def scale_deployments(self, deployment, replicas, wait_to_scale=True, timeout=30):

        # Start the timer
        signal.alarm(timeout)
        deployment.scale_deployment(replicas)
        try:
            if wait_to_scale:
                if self.verbose:
                    print(f"[RUNNING] Waiting for all replicas to scale")
                t_start = time.time()
                while not deployment.is_ready():
                    continue
                # Cancel the timer when the replicas are ready
                signal.alarm(0)      
                if self.verbose:          
                    print(f"[UPDATE] Deployment {deployment.deployment_name} successfully scaled in {round(time.time() - t_start, 3)} seconds.\n")
        except:
            assert False, f"\n[ERROR] Deployment {deployment.deployment_name} deployment time exceeded timeout limit."

    # Delete functions when finished
    def delete_functions(self, services, deployments_only=False, deployments=None, wait_time=2):
        if not deployments_only:
            for service in services:
                service.delete_service()
        else:
            for deployment in deployments:
                deployment.delete_deployment()
        time.sleep(wait_time)

    # Get number of worker nodes
    def get_worker_num(self):
        return len(self.k_worker_hostnames_)

    # Invoke Service using invoker and return stats
    def invoke_service(self, service, duration, rps):
        ip = service.get_service_ip()

        # Setup hostname file
        os.system('''echo '[ { "hostname": "''' + ip + '''" } ]' > ''' + INVOKER_FILE + '''endpoints.json''')
        if not self.verbose:
            print(f"[INFO] Hostname file has been set up at {INVOKER_FILE}/endpoints.json")

        # Format the invoker command nicely
        invoker_cmd_join_list = [f'{INVOKER_FILE}/invoker',
                                '-dbg',
                                f'-port {service.port}',
                                f'-time {duration}',
                                f'-rps {rps}',
                                f'-latf {service.name}.csv',
                                f'-endpointsFile {INVOKER_FILE}/endpoints.json']
        invoker_cmd = ' '.join(invoker_cmd_join_list)

        # Run invoker while redirecting output to separate file
        if not self.verbose:
            print("[RUNNING] Invoking with command at second {}".format(time.time()), f'`{invoker_cmd}`\n')
        
        self.invoker_start_time = time.time()
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

        # Check if latency file exists and return stats.
        if stat_lat_filename == None:
            assert False, "[ERROR] stat_lat_filename was not found."
        else:
            timestamp = time.time()
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
    def sample_env(self, interval_sec):
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

            try:
                network_rx_bps = (float)(p_metric.custom_query(
                    query=f'sum(rate(node_network_receive_bytes_total[{interval_sec}s]))')[0]['value'][1]) * 8
            except:
                assert False
            try:
                network_tx_bps = (float)(p_metric.custom_query(
                    query=f'sum(rate(node_network_transmit_bytes_total[{interval_sec}s]))')[0]['value'][1]) * 8
            except:
                assert False
            #
            tpl['net'] = [network_tx_bps, network_rx_bps]
            
            # Memory-related metrics
            # Free memory, Bytes
            # import pdb; pdb.set_trace()
            mem_query = p_metric.custom_query(
            query=f'node_memory_MemAvailable_bytes[{interval_sec}s]')
            if 'value' in mem_query[0]:
                assert False
            try:
                mem_free = mem_query[0]['values']
            except:
                assert False

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