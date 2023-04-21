import os
from paramiko import SSHClient, RSAKey, AutoAddPolicy
from scp import SCPClient, SCPException
import threading
import time
import re
import yaml
from enum import Enum
import csv



class EnvStatus(Enum):
    SUCCESS = 0
    ERROR = 1

class Env:
    # Benchmarks
    # {"name": {"fn_name": "path to .yaml"}}
    benchmarks_ = {
        "fibonacci": {
                "fibonacci-python": ["~/vSwarm/benchmarks/fibonacci/yamls/knative/", "kn-fibonacci-python.yaml"]
                }
        }

    # Name of the worker nodes as reported by `kubectl get nodes`
    worker_nodes_ = {
        1: "node-1.niklz-155204.ragger-pg0.utah.cloudlab.us",
        2: "node-2.niklz-155204.ragger-pg0.utah.cloudlab.us",
        3: "node-3.niklz-155204.ragger-pg0.utah.cloudlab.us",
        4: "node-4.niklz-155204.ragger-pg0.utah.cloudlab.us",
    }

    # Just hostnames of the servers
    hostnames_ = ["hp030.utah.cloudlab.us", "hp036.utah.cloudlab.us", "hp004.utah.cloudlab.us", "hp012.utah.cloudlab.us", "hp037.utah.cloudlab.us"]

    # Some consts
    kDeployTimeout_s_ = 30

    def __init__(self, master_node, port, user_name, ssh_key_filename, enable_strict_error_checking = False):
        k = RSAKey.from_private_key_file(ssh_key_filename)

        self.ssh_client_ = SSHClient()
        self.ssh_client_.set_missing_host_key_policy(AutoAddPolicy())
        self.ssh_client_.connect(self.hostnames_[master_node], port, user_name, pkey = k)
        self.scp = SCPClient(self.ssh_client_.get_transport())

        self.enable_strict_error_checking_ = enable_strict_error_checking

    def enable_env(self, benchmark_name):
        pass

    # Change parameters and deploy benchmark @param benchmark_name
    # @param deployment_actions:
    #   {"function_name": [node, C]}
    def deploy_application(self, benchmark_name, deployment_actions):
        #
        self.function_urls_ = {}

        # Change .yaml deployment config for all functions
        for fnct_name, depl_action in deployment_actions.items():
            # open .yaml and change config
            with open(f'yamls/{self.benchmarks_[benchmark_name][fnct_name][1]}') as f:
                yaml_dict = yaml.safe_load(f.read())
                yaml_dict['spec']['template']['metadata']['annotations']['autoscaling.knative.dev/min-scale'] = str(depl_action[1])
                yaml_dict['spec']['template']['metadata']['annotations']['autoscaling.knative.dev/max-scale'] = str(depl_action[1])
                yaml_dict['spec']['template']['spec']['affinity']['nodeAffinity'] \
                         ['requiredDuringSchedulingIgnoredDuringExecution']['nodeSelectorTerms'][0] \
                         ['matchExpressions'][0]['values'][0] = self.worker_nodes_[depl_action[0]]
                with open(f'tmp/{self.benchmarks_[benchmark_name][fnct_name][1]}', 'w+') as f_dpl:
                    yaml.dump(yaml_dict, f_dpl)

            # Send config to server
            try:
                self.scp.put(f'tmp/{self.benchmarks_[benchmark_name][fnct_name][1]}',
                            remote_path=self.benchmarks_[benchmark_name][fnct_name][0] + self.benchmarks_[benchmark_name][fnct_name][1],
                            recursive=False)
                print(f' > configuration for {benchmark_name}|{fnct_name} is sent')
            except:
                print(f' > ERROR: failed to send configuration for {benchmark_name}|{fnct_name}')
                return EnvStatus.ERROR

        # (Re)-deploy the benchmark
        for fnct_name, depl_action in deployment_actions.items():
            stdin, stdout, stderr = self.ssh_client_.exec_command(f'kn service delete {fnct_name}')
            if self.enable_strict_error_checking_:
                err = stderr.read().decode('UTF-8')
                if not err == "":
                    print(f' > ERROR: failed to deploy function {benchmark_name}|{fnct_name}, failed to delete prev. deployment, error was: ', err)
                    return EnvStatus.ERROR

            stdin, stdout, stderr = self.ssh_client_.exec_command(f'vSwarm/tools/kn_deploy.sh {self.benchmarks_[benchmark_name][fnct_name][0] + self.benchmarks_[benchmark_name][fnct_name][1]}')
            if self.enable_strict_error_checking_:
                err = stderr.read().decode('UTF-8')
                if not err == "":
                    print(f' > ERROR: failed to deploy function {benchmark_name}|{fnct_name}, failed to execute deployment script, error was: ', err)
                    return EnvStatus.ERROR

            # Wait until deployed
            timeout_cnt = 0
            while (True):
                stdin, stdout, stderr = self.ssh_client_.exec_command("kn service list --all-namespaces | awk '{print $7}'")
                ret = stdout.read().decode('UTF-8').split('\n')
                if (ret[0] == 'READY' and ret[1] == 'OK'):
                    print(f' > function {benchmark_name}|{fnct_name} is deployed')
                    break

                if timeout_cnt == self.kDeployTimeout_s_:
                    print(f' > ERROR: failed to deploy function {benchmark_name}|{fnct_name}, timeout')
                    return EnvStatus.ERROR

                timeout_cnt += 1
                time.sleep(1)

            if (timeout_cnt < self.kDeployTimeout_s_):
                # Get the URL of deployed function
                stdin, stdout, stderr = self.ssh_client_.exec_command("kn service list --all-namespaces | awk '{print $3}'")
                url = stdout.read().decode('UTF-8').split('\n')[1]

                self.function_urls_[fnct_name] = url

        print(f' > all functions from {benchmark_name} are deployed: ', self.function_urls_)
        return EnvStatus.SUCCESS

    # Invoke function @param function_name form bencharm @param benchmark_name with the default invoker
    # invoke_params: {'port': 80,
    #                 'duration': 10,
    #                 'rps': 1
    #                }
    def invoke_application(self, benchmark_name, function_name, invoke_params):
        url = self.function_urls_[function_name].replace("http://", "")
        stdin, stdout, stderr = self.ssh_client_.exec_command('''echo '[ { "hostname": "''' + url + '''" } ]' > endpoints.json''')

        # Invoke
        stdin, stdout, stderr = self.ssh_client_.exec_command(f'./vSwarm/tools/invoker/invoker -port {invoke_params["port"]} \
                                                                                               -dbg \
                                                                                               -time {invoke_params["duration"]} \
                                                                                               -rps {invoke_params["rps"]}')
        # Get stat filename
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
            m = re.search('target RPS: ([0-9]*\.?[0-9]*) \/ ([0-9]*\.?[0-9]*)', line)
            if m:
                stat_real_rps = (float)(m.group(1))
                stat_target_rps = (float)(m.group(2))

        # Print some stat
        return (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename

    # Fetch latency statistics
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

    def get_env_state(self):
        pass


#
# Try it
#
env = Env(0, 22, 'niklz', '/Users/nikita/.ssh/id_rsa')

for c in [1, 1, 2, 3, 4, 5, 6, 7]:
    print(c, ":")
    env.deploy_application("fibonacci", {"fibonacci-python": [2, c]})

    (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename = \
                    env.invoke_application("fibonacci", "fibonacci-python", {'port': 80, 'duration': 10, 'rps': 700})
    print(f'    stat: {stat_issued}, {stat_completed}, {stat_real_rps}, {stat_target_rps}, latency file: {stat_lat_filename}')

    lat_stat = env.get_latencies(stat_lat_filename)
    lat_stat.sort()
    print('    50th: ', lat_stat[(int)(len(lat_stat) * 0.5)])
    print('    90th: ', lat_stat[(int)(len(lat_stat) * 0.90)])
    print('    99th: ', lat_stat[(int)(len(lat_stat) * 0.99)])
    print('    99.9th: ', lat_stat[(int)(len(lat_stat) * 0.999)])
