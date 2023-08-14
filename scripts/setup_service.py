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

    def __init__(self, service_name, svc_file):
        self.service_name = service_name
        self.svc_file = svc_file

    def create_service(self):

        # Create Service
        os.system(f'kubectl apply -f {self.svc_file}')

        print(f"\n[INFO] service with manifest `{self.svc_file}` created.")

    def get_service_ip(self):
        # Get Cluster IP
        ip_cmd = f"kubectl get service/{self.service_name} -o jsonpath='{{.spec.clusterIP}}'"
        ip = str(run(ip_cmd, capture_output=True, shell=True, universal_newlines=True).stdout)

        return ip


    def delete_service(self):
        # Delete deployment

        # Delete Service
        os.system(f'kubectl delete -f {self.svc_file}')

        print(f"\n[INFO] service with manifest `{self.svc_file}` deleted.")