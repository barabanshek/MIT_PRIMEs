from os import path
from subprocess import run
from pprint import pprint
import os

class Service:

    def __init__(self, name, service_file, port):
        self.name = name
        self.service_file = service_file
        self.port = port

    def create_service(self):

        # Create Service, Deployment, and HPA
        ret = run(f'kubectl apply -f {self.service_file}', shell=True, capture_output=True)
        if ret.returncode != 0:
            assert False, f"\n[ERROR] Failed to run command `kubectl apply -f {self.service_file}`\n[ERROR] Error message: {ret.stderr}"

        print(f"\n[UPDATE] service with manifest `{self.service_file}` created.")

    def get_service_ip(self):
        # Get Cluster IP
        ip_cmd = f"kubectl get service/{self.name} -o jsonpath='{{.spec.clusterIP}}'"
        ret = run(ip_cmd, capture_output=True, shell=True, universal_newlines=True)
        if ret.returncode != 0:
            assert False, f"\n[ERROR] Failed to run command `kubectl get service/{self.name} -o jsonpath='{{.spec.clusterIP}}`\n[ERROR] Error message: {ret.stderr}"

        ip = ret.stdout

        return ip


    def delete_service(self):
        # Delete deployment

        # Delete Service
        ret = run(f'kubectl delete -f {self.service_file}', capture_output=True, shell=True)
        if ret.returncode != 0:
            assert False, f"\n[ERROR] Failed to run command `kubectl delete -f {self.service_file}`\n[ERROR] Error message: {ret.stderr}"

        print(f"\n[DELETED] service with manifest `{self.service_file}` deleted.")
        os.remove(self.service_file)
        print(f"\n[DELETED] manifest `{self.service_file}` deleted.")