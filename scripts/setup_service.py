from os import path
from subprocess import run
from pprint import pprint

class Service:

    def __init__(self, service_name, service_file, port):
        self.service_name = service_name
        self.service_file = service_file
        self.port = port

    def create_service(self):

        # Create Service
        ret = run(f'kubectl apply -f {self.service_file}', shell=True, capture_output=True).stdout

        print(f"\n[UPDATE] service with manifest `{self.service_file}` created.")

    def get_service_ip(self):
        # Get Cluster IP
        ip_cmd = f"kubectl get service/{self.service_name} -o jsonpath='{{.spec.clusterIP}}'"
        ip = str(run(ip_cmd, capture_output=True, shell=True, universal_newlines=True).stdout)

        return ip


    def delete_service(self):
        # Delete deployment

        # Delete Service
        run(f'kubectl delete -f {self.service_file}', shell=True)

        print(f"\n[DELETED] service with manifest `{self.service_file}` deleted.")