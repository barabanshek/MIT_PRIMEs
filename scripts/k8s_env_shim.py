from os import path
import os
import argparse
import yaml
import json
from pprint import pprint
from kubernetes import client, config

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

    # Create Deployment and Service.
    def setup(self):
        try:   
            self.deployment.create_deployment()
        except Exception as e:
            print('Previous Deployments may still be deleting...')
            print()
            print(f'ERROR: {e}')
            return 0

        self.service.create_service()
        print(f"Service can be invoked at IP: {self.service.get_service_ip()} at port {self.port}")

    
    # Invoke Service using invoker 
    def invoke_service(self):
        ip = self.service.get_service_ip()
        invoker_file = '~/vSwarm/tools/invoker'

        # Get invoker configs
        invoke_params = self.json_data['invoker_configs']

        # Setup hostname file
        os.system('''echo '[ { "hostname": "''' + ip + '''" } ]' > ''' + invoker_file + '''endpoints.json''')
        print(f"[INFO] Hostname file has been set up at {invoker_file}endpoints.json")

        # Invoke
        print("[INFO] Invoking with command " + f'{invoker_file}/invoker -dbg \
                                            -port {self.port} \
                                            -time {invoke_params["duration"]} \
                                            -rps {invoke_params["rps"]} \
                                            -endpointsFile {invoker_file}endpoints.json')
        os.system(f'{invoker_file}/invoker -dbg \
                                            -port {self.port} \
                                            -time {invoke_params["duration"]} \
                                            -rps {invoke_params["rps"]} \
                                            -endpointsFile {invoker_file}endpoints.json')

    # Scale number of replicas
    def scale_deployment(self, replicas):
        self.deployment.scale_deployment(replicas)

def main(args):
    env = Env(args.config)
    env.setup()
    env.invoke_service()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--config')
    args = parser.parse_args()
    main(args)