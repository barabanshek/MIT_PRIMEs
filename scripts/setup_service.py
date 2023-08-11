from os import path
import os

import datetime

import pytz
import argparse
import yaml
import time

from subprocess import run
from pprint import pprint

from kubernetes import client, config

class Service:

    def __init__(self, service_name, depl_file):
        self.service_name = service_name
        self.depl_file = depl_file

    def create_service(self):

        # Create Service
        os.system(f'kubectl apply -f {self.depl_file}')

        print(f"\n[INFO] service with manifest `{self.depl_file}` created.")

    def get_service_ip(self, port):
        # Get Cluster IP
        ip_cmd = f"kubectl get service/{self.service_name} -o jsonpath='{{.spec.clusterIP}}'"
        ip = str(run(ip_cmd, capture_output=True, shell=True, universal_newlines=True).stdout) + ':' + str(port)

        return ip


    def delete_service(self):
        # Delete deployment

        # Delete Service
        os.system(f'kubectl delete -f {self.depl_file}')

        print(f"\n[INFO] service with manifest `{self.depl_file}` deleted.")


def main(args):
    # Configs can be set in Configuration class directly or using helper
    # utility. If no argument provided, the config will be loaded from
    # default location.
    config.load_kube_config()
    apps_v1 = client.AppsV1Api()
    service_name = args.servicename
    depl_file = args.f

    service = Service(service_name, depl_file)

    # Uncomment the following lines to enable debug logging
    # c = client.Configuration()
    # c.debug = True
    # apps_v1 = client.AppsV1Api(api_client=client.ApiClient(configuration=c))

    # Create a deployment object with client-python API. The deployment we
    # created is same as the `nginx-deployment.yaml` in the /examples folder.

    # read yaml file to get JSON formatted version of the deployment

    with open(path.join(path.dirname(__file__), depl_file)) as f:
        dep = yaml.safe_load(f)

    port = dep['spec']['ports'][0]['port']
    service.create_service()
    print(service.get_service_ip(port))



    # deployment = create_deployment(apps_v1, dep)
    # scale_deployment(apps_v1, deployment, 3)
    # scale_deployment(apps_v1, deployment, 3)

    # restart_deployment(apps_v1, deployment)

    # delete_deployment(apps_v1)
    # except Exception as e:
    #     delete_deployment(apps_v1)
    #     print("Exception occurred: %s\n" % e)
    #     return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--servicename')
    parser.add_argument('--f')
    args = parser.parse_args()
    main(args)