# MIT_PRIMEs

## Prepare environment
1. Change the server_configs.json to update worker and master nodes, and the SSH keys to access the nodes from your local
2. Setup pypthon environment: `cd scripts; conda create --name rl4serverless python=3.9; conda activate rl4serverless; pip install -r requirements.txt`
3. Install prometheus-api-client: `conda activate rl4serverless; pip install prometheus-api-client kubernetes`

## Setup Kubectl (not necessary)
```
echo "$(cat kubectl.sha256)  kubectl" | sha256sum --check
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
kubectl version --client
```

## Set up all nodes
1. `python3 setup_testbed.py --serverconfig server_configs.json`
2. Wait until
All nodes are set, but please check the logs and also execute `watch kubectl get nodes`and `watch kubectl get pods --all-namespaces` on the master node to see if things are OK

## Launch experiments for RL
1. `pip install gym tqdm wandb`

