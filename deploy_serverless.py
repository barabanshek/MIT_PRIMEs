import os
from paramiko import SSHClient, RSAKey, AutoAddPolicy
import threading
import time
import re

# Credentials
kSSHKey = "/Users/nikita/.ssh/id_rsa"
kUsername = "niklz"
kNodes = ["ms0836.utah.cloudlab.us", "ms0813.utah.cloudlab.us", "ms0805.utah.cloudlab.us"]
kMasterNode = 0
kWorkerNodes = [1, 2]


# SSH comands
kInstallCmd_AllNodes = '''
    echo "Cleaning stuff"
    if [ -d "vhive" ]; then
        echo "Cleaning processes..."
        cd vhive
        sudo scripts/github_runner/clean_cri_runner.sh
        cd
    fi
    echo "Cleaning dirs..."
    sudo rm -r *
    sudo rm -r /tmp/*

    git clone --depth=1 https://github.com/vhive-serverless/vhive.git
    cd vhive
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

kInstallCmd_MasterJoin_1 = '''
    cd vhive
    sudo screen -dmS containerd bash -c "containerd > >(tee -a /tmp/vhive-logs/containerd.stdout) 2> >(tee -a /tmp/vhive-logs/containerd.stderr >&2)"
    echo "Y" | ./scripts/cluster/create_multinode_cluster.sh stock-only > >(tee -a /tmp/vhive-logs/create_multinode_cluster.stdout) 2> >(tee -a /tmp/vhive-logs/create_multinode_cluster.stderr >&2)

'''

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
'''

class Deployer:
    def __init__(self):
        self.ssh_clients_ = []
        self.lock_ = threading.Lock()

        port = 22
        k = RSAKey.from_private_key_file(kSSHKey)
        for node in kNodes:
            ssh_client = SSHClient()
            ssh_client.set_missing_host_key_policy(AutoAddPolicy())
            ssh_client.connect(node, port, kUsername, pkey = k)

            self.ssh_clients_.append(ssh_client)

    def save_print(self, stdout, stderr):
        self.lock_.acquire()
        print(stdout.read().decode('UTF-8'))
        print(stderr.read().decode('UTF-8'))
        self.lock_.release()

    def setup_node(self, i):
        stdin, stdout, stderr = self.ssh_clients_[i].exec_command(kInstallCmd_AllNodes)
        self.save_print(stdout, stderr)

    def setup_node_worker_1(self, i):
        stdin, stdout, stderr = self.ssh_clients_[i].exec_command(kInstallCmd_WorkerNodes)
        self.save_print(stdout, stderr)

    def setup_node_master(self):
        stdin, stdout, stderr = self.ssh_clients_[kMasterNode].exec_command(kInstallCmd_MasterJoin_1)
        self.save_print(stdout, stderr)

    def setup_all_nodes(self):
        #
        print("Setting-up nodes, initial...")
        threads = []
        for node_i in range(len(self.ssh_clients_)):
            t = threading.Thread(target=self.setup_node, args=(node_i,))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        #
        print("Setting-up nodes, workers, first phase...")
        threads = []
        for node_i in kWorkerNodes:
            t = threading.Thread(target=self.setup_node_worker_1, args=(node_i,))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        #
        print("Setting-up Master...")
        master_thread = threading.Thread(target=self.setup_node_master)
        master_thread.start()

        # Wait until it prints the line
        join_string = ""
        while(True):
            stdin, stdout, stderr = self.ssh_clients_[kMasterNode].exec_command("cat /tmp/vhive-logs/create_multinode_cluster.stdout")
            lines = stdout.read().decode('UTF-8')
            x = re.search("(kubeadm.*)\\\\", lines)
            if not x == None:
                join_string = "sudo "
                join_string += x.group(1)
                x1 = re.search("(--discovery-token-ca-cert-hash.*) ", lines)
                join_string += x1.group(1)
                break

            time.sleep(1)
        print("Join string: ", join_string)

        # Join on all workers (sequentialy to be careful, but can be parallel)
        print("Joining all workers...")
        for node_i in kWorkerNodes:
            stdin, stdout, stderr = self.ssh_clients_[node_i].exec_command(join_string)
            print(stdout.read().decode('UTF-8'))

        #
        print("Installing vSwarm...")
        stdin, stdout, stderr = self.ssh_clients_[kMasterNode].exec_command(kInstallCmd_MasterSetupvSwarm)
        print(stdout.read().decode('UTF-8'))

        print("All nodes are set, but please check the logs and also execute `watch kubectl get nodes` and `watch kubectl get pods --all-namespaces` on the master node to see if things are OK")


#
#
#
def main():
    deployer = Deployer()
    deployer.setup_all_nodes()

if __name__ == "__main__":
    main()
