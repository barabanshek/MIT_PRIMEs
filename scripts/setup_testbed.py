import os
from paramiko import SSHClient, Ed25519Key, RSAKey, AutoAddPolicy
import threading
import time
import re
import json
import argparse


#
# Bash scripts
#
kInstallCmd_AllNodes = '''
    echo "Cleaning stuff"
    if [ -d "vhive" ]; then
        echo "Cleaning processes..."
        cd vhive
        sudo scripts/github_runner/clean_cri_runner.sh
        cd
        pkill -9 node_exporter
        pkill -9 prometheus
    fi
    echo "Cleaning dirs..."
    sudo rm -r *
    sudo rm -r /tmp/*

    echo "performance" | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

    git clone https://github.com/vhive-serverless/vhive.git
    cd vhive
    git checkout TAG_VHIVE_VERSION
    mkdir -p /tmp/vhive-logs
    ./scripts/cloudlab/setup_node.sh stock-only > >(tee -a /tmp/vhive-logs/setup_node.stdout) 2> >(tee -a /tmp/vhive-logs/setup_node.stderr >&2)

'''

kInstallCmd_WorkerNodes = '''
    cd vhive
    ./scripts/cluster/setup_worker_kubelet.sh stock-only > >(tee -a /tmp/vhive-logs/setup_worker_kubelet.stdout) 2> >(tee -a /tmp/vhive-logs/setup_worker_kubelet.stderr >&2)
    sudo screen -dmS containerd bash -c "containerd > >(tee -a /tmp/vhive-logs/containerd.stdout) 2> >(tee -a /tmp/vhive-logs/containerd.stderr >&2)"
    source /etc/profile && go build
    sudo screen -dmS vhive bash -c "./vhive > >(tee -a /tmp/vhive-logs/vhive.stdout) 2> >(tee -a /tmp/vhive-logs/vhive.stderr >&2)"

'''

kInstallCmd_MasterJoin = '''
    cd vhive
    sudo screen -dmS containerd bash -c "containerd > >(tee -a /tmp/vhive-logs/containerd.stdout) 2> >(tee -a /tmp/vhive-logs/containerd.stderr >&2)"
    ./scripts/cluster/create_multinode_cluster.sh stock-only > >(tee -a /tmp/vhive-logs/create_multinode_cluster.stdout) 2> >(tee -a /tmp/vhive-logs/create_multinode_cluster.stderr >&2)

'''

# kPostInstallCmd_ = '''
#     sudo chmod 666 ${pwd}.config/kn/config.yaml
# '''

kInstallCmd_MasterSetupvSwarm = '''
    git clone https://github.com/vhive-serverless/vSwarm.git
    echo "Y" | sudo apt install protobuf-compiler
    echo "Y" | sudo apt install golang-goprotobuf-dev

    echo 'export GOROOT=/usr/local/go' >> ~/.bashrc
    echo 'export GOPATH=$HOME/go' >> ~/.bashrc
    echo 'export GOROOTBIN=$GOROOT/bin' >> ~/.bashrc
    echo 'export GOBIN=$GOPATH/bin' >> ~/.bashrc
    echo 'export PATH=$PATH:$GOROOT:$GOPATH:$GOBIN:$GOROOTBIN' >> ~/.bashrc

    export GOROOT=/usr/local/go
    export GOPATH=$HOME/go
    export GOROOTBIN=$GOROOT/bin
    export GOBIN=$GOPATH/bin
    export PATH=$PATH:$GOROOT:$GOPATH:$GOBIN:$GOROOTBIN

    cd ~/vSwarm/tools/invoker
    go get google.golang.org/grpc/cmd/protoc-gen-go-grpc
    go install google.golang.org/grpc/cmd/protoc-gen-go-grpc
    make invoker

    kubectl patch ConfigMap config-features -n knative-serving -p '{"data":{"kubernetes.podspec-affinity":"enabled"}}'
    kubectl patch ConfigMap config-features -n knative-serving -p '{"data":{"kubernetes.podspec-tolerations":"enabled"}}'

'''

kInstallCmd_Prometheus = '''
    wget https://github.com/prometheus/node_exporter/releases/download/v1.5.0/node_exporter-1.5.0.linux-amd64.tar.gz
    tar -xvf node_exporter-1.5.0.linux-amd64.tar.gz
    wget https://github.com/prometheus/prometheus/releases/download/v2.43.0/prometheus-2.43.0.linux-amd64.tar.gz
    tar -xvf prometheus-2.43.0.linux-amd64.tar.gz

    cd prometheus-2.43.0.linux-amd64/
    echo "
global:
  scrape_interval: 1s

scrape_configs:
- job_name: node
  static_configs:
  - targets: ['$(hostname -i):9100']
        " > prometheus.yml

    cd
    cd node_exporter-1.5.0.linux-amd64/
    ./node_exporter > /dev/null 2>&1 &
    cd
    cd prometheus-2.43.0.linux-amd64/
    ./prometheus --config.file=./prometheus.yml > /dev/null 2>&1 &

    exit 0

'''


#
# ServerlessDeployer -- prepare all the nodes in the cluster for
# serverless experiments.
#
class ServerlessDeployer:
    def __init__(self, server_configs_json):
        # Parse server configuration.
        with open(server_configs_json, 'r') as f:
            json_data = json.load(f)
        self.server_nodes_ = json_data['servers']['hostnames']
        self.account_username_ = json_data['account']['username']
        self.account_ssh_key_filename_ = json_data['account']['ssh_key_filename']
        self.ssh_port_ = json_data['account']['port']
        self.vHiveVersion_ = json_data['sys']['vHive_version']

        # Init ServerlessDeployer.
        self.ssh_clients_master_ = None
        self.ssh_clients_workers_ = []
        self.lock_ = threading.Lock()

        if "ed25519" in self.account_ssh_key_filename_:
            k = Ed25519Key.from_private_key_file(self.account_ssh_key_filename_)
        elif "id_rsa" in self.account_ssh_key_filename_:
            k = RSAKey.from_private_key_file(self.account_ssh_key_filename_)
        else:
            print("Error: Unknown key type.")
            assert False

        for node_name, role in self.server_nodes_.items():
            ssh_client = SSHClient()
            ssh_client.set_missing_host_key_policy(AutoAddPolicy())
            ssh_client.connect(node_name, self.ssh_port_,
                               self.account_username_, pkey=k)

            if role == "master":
                self.ssh_clients_master_ = ssh_client
            elif role == "worker":
                self.ssh_clients_workers_.append(ssh_client)
            else:
                assert False, f'Unknown server role, check you {server_configs_json}'

        # Check configuration.
        if self.ssh_clients_master_ == None:
            assert False, "Please, specify the master node"
        if self.ssh_clients_workers_ == []:
            assert False, "The testbed must have at least one worker node"

        # Open log file.
        self.log_file_ = open(json_data['sys']['log_filename'], "w+")

    # Thread-safe logging into the log file.
    def __log(self, stdout, stderr):
        self.lock_.acquire()

        self.log_file_.write("STDOUT: ")
        self.log_file_.write(stdout.read().decode('UTF-8'))
        self.log_file_.write("STDERR: ")
        self.log_file_.write(stderr.read().decode('UTF-8'))

        self.lock_.release()

    def __setup_all_nodes(self, ssh_cli):
        # Check the right vHive version.
        install_cmd = kInstallCmd_AllNodes.replace(
            "TAG_VHIVE_VERSION", self.vHiveVersion_)
        _, stdout, stderr = ssh_cli.exec_command(install_cmd)
        exit_status = stdout.channel.recv_exit_status()
        self.__log(stdout, stderr)

        if not exit_status == 0:
            print("Error when setting-up all nodes, please, check the script log")
            assert False    # crash immediately

    def __setup_worker_nodes(self, ssh_cli):
        _, stdout, stderr = ssh_cli.exec_command(kInstallCmd_WorkerNodes)
        exit_status = stdout.channel.recv_exit_status()
        self.__log(stdout, stderr)

        if not exit_status == 0:
            print("Error when setting-up worker nodes, please, check the script log")
            assert False    # crash immediately

    def __install_prometheus(self, ssh_cli):
        _, stdout, stderr = ssh_cli.exec_command(kInstallCmd_Prometheus)
        exit_status = stdout.channel.recv_exit_status()
        self.__log(stdout, stderr)

        if not exit_status == 0:
            print("Error wheninstalling Prometheus, please, check the script log")
            assert False    # crash immediately

    # Execute the same @param script on @param nodes concurrently and independently
    def __execute_script_in_parallel(self, nodes, script):
        threads = []
        for ssh_cli in nodes:
            t = threading.Thread(target=script, args=(ssh_cli,))
            t.start()
            threads.append(t)
        for t in threads:
            t.join()

    def deploy(self):
        #
        print("Setting-up all nodes...")
        self.__execute_script_in_parallel([self.ssh_clients_master_] + self.ssh_clients_workers_,
                                          self.__setup_all_nodes)

        #
        print("Setting-up worker nodes...")
        self.__execute_script_in_parallel(
            self.ssh_clients_workers_, self.__setup_worker_nodes)

        # Start joining procedure.
        print("Setting-up Master...")
        stdin_m, stdout_m, stderr_m = self.ssh_clients_master_.exec_command(
            kInstallCmd_MasterJoin)

        # Wait until it prints the "join" string.
        # Wait a bit.
        time.sleep(5)
        join_string = ""
        while (True):
            _, stdout, stderr = self.ssh_clients_master_.exec_command(
                "cat /tmp/vhive-logs/create_multinode_cluster.stdout")
            exit_status = stdout.channel.recv_exit_status()
            assert exit_status == 0, "Can not happen"

            lines = stdout.read().decode('UTF-8')
            x = re.search("(kubeadm.*)\\\\", lines)
            if not x == None:
                join_string = "sudo "
                join_string += x.group(1)
                x1 = re.search("(--discovery-token-ca-cert-hash.*) ", lines)
                join_string += x1.group(1)
                break

            time.sleep(1)

        print("...join string: ", join_string)

        # Join on all workers (sequentialy, this is important).
        print("Joining all workers...")
        p_bar = 0
        for ssh_cli in self.ssh_clients_workers_:
            _, stdout, stderr = ssh_cli.exec_command(join_string)
            exit_status = stdout.channel.recv_exit_status()
            self.__log(stdout, stderr)
            if not exit_status == 0:
                print(
                    "Failed to join cluster, try to re-run the script OR check the error log")
                assert False
            else:
                p_bar += 1
                print(f'  {p_bar}/{len(self.ssh_clients_workers_)}')
        print("")

        # Answer 'yes' to the master and wait until it finishes.
        stdin_m.channel.send('y\n')
        stdin_m.channel.shutdown_write()
        exit_status = stdout_m.channel.recv_exit_status()
        self.__log(stdout_m, stderr_m)
        if not exit_status == 0:
            print(
                "Error after workers have joined the cluster, try to re-run the script OR check the error log")
            assert False

        # Do some post-install
        print("Post-installation...")
        # _, stdout, stderr = self.ssh_clients_master_.exec_command(
        #     kPostInstallCmd_)
        exit_status = stdout.channel.recv_exit_status()
        # TODO: this might fail sometimes, investigate and fix later.
        # assert exit_status == 0, "Error during post-installation"

        #
        print("Installing vSwarm...")
        _, stdout, stderr = self.ssh_clients_master_.exec_command(
            kInstallCmd_MasterSetupvSwarm)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status == 0:
            print("vSwarm is installed!")
        else:
            print("Error when installing vSwarm, try to do it manually")

        #
        print("Installing Prometheus on all nodes...")
        self.__execute_script_in_parallel([self.ssh_clients_master_] + self.ssh_clients_workers_,
                                          self.__install_prometheus)

        print("All nodes are set, but please check the logs and also execute `watch kubectl get nodes`"
              "and `watch kubectl get pods --all-namespaces` on the master node to see if things are OK")


#
# Example cmd:
#    python3 setup_testbed.py --serverconfig server_configs.json
#
def main(args):
    deployer = ServerlessDeployer(args.serverconfig)
    deployer.deploy()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--serverconfig')
    args = parser.parse_args()

    if args.serverconfig == None:
        assert False, "Please, specify the server configuration json filename"

    main(args)
