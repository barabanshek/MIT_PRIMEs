import os
from paramiko import SSHClient, RSAKey, AutoAddPolicy
from scp import SCPClient, SCPException
import threading
import time
import re
import yaml
from enum import Enum
import csv
import json
import argparse
from prometheus_api_client import PrometheusConnect
import numpy as np


#
# Environment - RL-term abstraction over the cluster.
#
class EnvStatus(Enum):
    SUCCESS = 0
    ERROR = 1


class Env:
    # Benchmarks.
    # {"name": {"fn_name": "path to .yaml"}}
    benchmarks_ = {
        "fibonacci": {
            "fibonacci-python": ["~/vSwarm/benchmarks/fibonacci/yamls/knative/", "kn-fibonacci-python.yaml"]
        },
        "video-analytics": {
            "decoder": ["~/vSwarm/benchmarks/video-analytics/yamls/knative/inline/", "service-decoder.yaml"],
            "recog": ["~/vSwarm/benchmarks/video-analytics/yamls/knative/inline/", "service-recog.yaml"],
            "streaming": ["~/vSwarm/benchmarks/video-analytics/yamls/knative/inline/", "service-streaming.yaml"]
        },
        "online-shop": {
            "adservice": ["~/vSwarm/benchmarks/online-shop/yamls/knative/", "kn-adservice.yaml"],
            "cartservice": ["~/vSwarm/benchmarks/online-shop/yamls/knative/", "kn-cartservice.yaml"],
            "currencyservice": ["~/vSwarm/benchmarks/online-shop/yamls/knative/", "kn-currencyservice.yaml"],
            "emailservice": ["~/vSwarm/benchmarks/online-shop/yamls/knative/", "kn-emailservice.yaml"],
            "paymentservice": ["~/vSwarm/benchmarks/online-shop/yamls/knative/", "kn-paymentservice.yaml"],
            "productcatalogservice": ["~/vSwarm/benchmarks/online-shop/yamls/knative/", "kn-productcatalogservice.yaml"],
            "shippingservice": ["~/vSwarm/benchmarks/online-shop/yamls/knative/", "kn-shippingservice.yaml"],
            # skipping checkoutservice, as it's chained
            # skipping recommendationservice, same
        },
        "hotel-app": {
            "hotel-app-geo-tracing": ["~/vSwarm/benchmarks/hotel-app/yamls/knative/", "kn-geo-tracing.yaml"],
            "hotel-app-geo": ["~/vSwarm/benchmarks/hotel-app/yamls/knative/", "kn-geo.yaml"],
            "hotel-app-profile": ["~/vSwarm/benchmarks/hotel-app/yamls/knative/", "kn-profile.yaml"],
            "hotel-app-rate": ["~/vSwarm/benchmarks/hotel-app/yamls/knative/", "kn-rate.yaml"],
            "hotel-app-recommendation": ["~/vSwarm/benchmarks/hotel-app/yamls/knative/", "kn-recommendation.yaml"],
            "hotel-app-reservation": ["~/vSwarm/benchmarks/hotel-app/yamls/knative/", "kn-reservation.yaml"],
            "hotel-app-user": ["~/vSwarm/benchmarks/hotel-app/yamls/knative/", "kn-user.yaml"],
            # skipping kn-search-tracing.yaml, as it's chained
            # skipping kn-search.yaml, same
        }
    }

    # Some consts.
    kDeployTimeout_s_ = 60

    def __init__(self, server_configs_json):
        # Parse server configuration.
        with open(server_configs_json, 'r') as f:
            json_data = json.load(f)
        self.server_nodes_ = json_data['servers']['hostnames']
        self.account_username_ = json_data['account']['username']
        self.account_ssh_key_filename_ = json_data['account']['ssh_key_filename']
        self.ssh_port_ = json_data['account']['port']

        # Init Env
        k = RSAKey.from_private_key_file(self.account_ssh_key_filename_)
        self.ssh_client_ = SSHClient()
        self.ssh_client_.set_missing_host_key_policy(AutoAddPolicy())
        self.ssh_client_.connect([n_name for n_name, n_role in self.server_nodes_.items() if n_role == "master"][0],
                                 self.ssh_port_,
                                 self.account_username_,
                                 pkey=k)
        self.scp = SCPClient(self.ssh_client_.get_transport())

        # Some extra vars for later use
        self.total_mem_ = None

    #
    def enable_env(self):
        # Enable knative to allow manual function placement.
        self.ssh_client_.exec_command(
            '''kubectl patch ConfigMap config-features -n knative-serving -p '{"data":{"kubernetes.podspec-affinity":"enabled"}}' ''')
        self.ssh_client_.exec_command(
            '''kubectl patch ConfigMap config-features -n knative-serving -p '{"data":{"kubernetes.podspec-tolerations":"enabled"}}' ''')

        # Check all nodes are ready.
        stdin, stdout, stderr = self.ssh_client_.exec_command(
            '''kubectl get nodes | awk '{print $2}' ''')
        ret = stdout.read().decode('UTF-8').split('\n')[1:-1]
        assert len(ret) == len(
            self.server_nodes_), "Incorrect number of servers detected"
        for node_status in ret:
            if not node_status == 'Ready':
                print(" > ERROR: some nodes are not ready")
                return EnvStatus.ERROR

        # Get node hostnames as appears in knative.
        stdin, stdout, stderr = self.ssh_client_.exec_command(
            '''kubectl get nodes | awk '{print $1}' ''')
        ret = stdout.read().decode('UTF-8').split('\n')[1:-1]

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
        print(" > Env is initialized, some stats: ")
        print("   knative worker node names: ", self.k_worker_hostnames_)
        print("   knative #of available metrics for workers: ", {
              k: len(v.all_metrics()) for k, v in self.k_worker_metrics_.items()})

    def get_worker_num(self):
        return len(self.k_worker_hostnames_)

    # Change parameters and deploy benchmark @param benchmark_name @param deployment_actions (if needed, add more here):
    #   {"function_name": [node, C]},
    #               where 'node' is the node we want to run the function on;
    #               'C' - number of function instances on that node
    def deploy_application(self, benchmark_name, deployment_actions):
        #
        self.function_urls_ = {}

        # Change .yaml deployment config for all functions.
        for fnct_name, depl_action in deployment_actions.items():
            # open .yaml and change config.
            with open(f'yamls/{self.benchmarks_[benchmark_name][fnct_name][1]}') as f:
                yaml_dict = yaml.safe_load(f.read())
                yaml_dict['spec']['template']['metadata']['annotations']['autoscaling.knative.dev/min-scale'] = str(
                    depl_action[1])
                yaml_dict['spec']['template']['metadata']['annotations']['autoscaling.knative.dev/max-scale'] = str(
                    depl_action[1])
                yaml_dict['spec']['template']['spec']['affinity']['nodeAffinity']['requiredDuringSchedulingIgnoredDuringExecution']['nodeSelectorTerms'][0]['matchExpressions'][0]['values'][0] = self.k_worker_hostnames_[
                    depl_action[0]]
                with open(f'tmp/{self.benchmarks_[benchmark_name][fnct_name][1]}', 'w+') as f_dpl:
                    yaml.dump(yaml_dict, f_dpl)

            # Send config to server.
            try:
                self.scp.put(f'tmp/{self.benchmarks_[benchmark_name][fnct_name][1]}',
                             remote_path=self.benchmarks_[
                                 benchmark_name][fnct_name][0] + self.benchmarks_[benchmark_name][fnct_name][1],
                             recursive=False)
                print(
                    f' > configuration for {benchmark_name}|{fnct_name} is sent')
            except:
                print(
                    f' > ERROR: failed to send configuration for {benchmark_name}|{fnct_name}')
                return EnvStatus.ERROR

        # Delete previous deployments.
        stdin, stdout, stderr = self.ssh_client_.exec_command(
            'kn service delete --all')
        exit_status = stdout.channel.recv_exit_status()
        if not exit_status == 0:
            print(
                f' > ERROR: failed to deploy benchmark {benchmark_name}, failed to delete prev. deployment')
            return EnvStatus.ERROR

        # Clean-up all pods.
        stdin, stdout, stderr = self.ssh_client_.exec_command(
            'kubectl delete pod --all --grace-period=0 --force')
        exit_status = stdout.channel.recv_exit_status()
        if not exit_status == 0:
            print(
                f' > ERROR: failed to deploy benchmark {benchmark_name}, failed to clean-up all pods')
            return EnvStatus.ERROR

        # Deploy new benchmark (concurrently, to speed-up deployment).
        fn_dpl_string = ""
        if (len(deployment_actions) == 1):
            fnct_name = list(deployment_actions.keys())[0]
            fn_dpl_string += f'kn service apply -f {self.benchmarks_[benchmark_name][fnct_name][0] + self.benchmarks_[benchmark_name][fnct_name][1]}'
        else:
            for fnct_name in deployment_actions.keys():
                fn_dpl_string += f'kn service apply -f {self.benchmarks_[benchmark_name][fnct_name][0] + self.benchmarks_[benchmark_name][fnct_name][1]}' + ' & '
            # 'wait' waits until all background processes are done.
            fn_dpl_string += 'wait'

        # Actual deployment.
        stdin, stdout, stderr = self.ssh_client_.exec_command(fn_dpl_string)

        # Wait until deployed.
        for fnct_name in deployment_actions.keys():
            timeout_cnt = 0
            while (True):
                stdin, stdout, stderr = self.ssh_client_.exec_command(
                    f"kn service list {fnct_name} | awk '{{print $6}}' ")
                ret = stdout.read().decode('UTF-8').split('\n')
                if (ret[0] == 'READY' and ret[1] == 'OK'):
                    print(
                        f' > function {benchmark_name}|{fnct_name} is deployed')
                    break

                if timeout_cnt == self.kDeployTimeout_s_:
                    print(
                        f' > ERROR: failed to deploy function {benchmark_name}|{fnct_name}, timeout')
                    return EnvStatus.ERROR

                timeout_cnt += 1
                time.sleep(1)

            url = None
            if (timeout_cnt < self.kDeployTimeout_s_):
                # Get the URL of deployed function.
                stdin, stdout, stderr = self.ssh_client_.exec_command(
                    f"kn service list {fnct_name} | awk '{{print $2}}' ")
                url = stdout.read().decode('UTF-8').split('\n')[1]

                self.function_urls_[fnct_name] = url

        print(
            f' > all functions from {benchmark_name} are deployed: ', self.function_urls_)
        return EnvStatus.SUCCESS

    def delete_all_deployments(self):
        # Delete previous deployments.
        _, stdout, _ = self.ssh_client_.exec_command(
            'kn service delete --all')
        exit_status = stdout.channel.recv_exit_status()
        if not exit_status == 0:
            print(f' > ERROR: failed to detele all deployed apps')
            return EnvStatus.ERROR

        return EnvStatus.SUCCESS

    # Invoke function @param function_name form benchmark @param benchmark_name with the default invoker
    # invoke_params: {'port': 80,
    #                 'duration': 10,
    #                 'rps': 1
    #                }
    def invoke_application(self, benchmark_name, function_name, invoke_params):
        url = self.function_urls_[function_name].replace("http://", "")
        stdin, stdout, stderr = self.ssh_client_.exec_command(
            '''echo '[ { "hostname": "''' + url + '''" } ]' > endpoints.json''')

        # Invoke.
        stdin, stdout, stderr = self.ssh_client_.exec_command(f'./vSwarm/tools/invoker/invoker -port {invoke_params["port"]} \
                                                                                               -dbg \
                                                                                               -time {invoke_params["duration"]} \
                                                                                               -rps {invoke_params["rps"]}')
        # Get stat filename.
        stdout = stdout.read().decode('UTF-8').split('\n')
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

        # Print some stat.
        return (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename

    # Fetch latency statistics.
    def get_latencies(self, latency_stat_filename):
        lat = []
        self.scp.get(remote_path=latency_stat_filename,
                     local_path='tmp/',
                     recursive=False)
        with open(f'tmp/{latency_stat_filename}') as f:
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
