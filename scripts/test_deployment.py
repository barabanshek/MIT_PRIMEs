"""
The example covers the following:
    - Creation of a deployment using AppsV1Api
    - update/patch to perform rolling restart on the deployment
    - deletetion of the deployment
"""

from os import path

import datetime

import pytz
import argparse
import yaml
import time

from pprint import pprint

from kubernetes import client, config

class Deployment:

    def __init__(self, api, dep, deployment_name):
        # k8s API
        self.api = api
        # deployment as a json formatted dict
        self.dep = dep
        # name of deployment
        self.deployment_name = deployment_name

        # Create deployment V1Deployment object
        conts = self.dep['spec']['template']['spec']['containers']
        ports = []
        for i in range(len(conts)):
            try:
                for j in range(len(conts[i]['ports'])):
                    ports.append(client.V1ContainerPort(name=conts[i]['ports'][j]['name'], container_port=conts[i]['ports'][j]['containerPort']))
            except:
                continue
        containers = [client.V1Container(
            args=conts[i]['args'],
            name=conts[i]['name'],
            image=conts[i]['image'],
            ports=ports,
        ) for i in range(len(conts))]

        # Create and configure a spec section
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels=self.dep['metadata']['labels']),
            spec=client.V1PodSpec(containers=containers),
        )

        # Create the specification of deployment
        spec = client.V1DeploymentSpec(
            replicas=self.dep['spec']['replicas'], template=template, selector=self.dep['spec']['selector'])

        # Instantiate the deployment object
        self.deployment_object = client.V1Deployment(
            self.dep['apiVersion'],
            kind="Deployment",
            metadata=client.V1ObjectMeta(name=self.deployment_name, namespace=self.dep['metadata']['namespace']),
            spec=spec,
        )


    def create_deployment(self):
        # Create deployment
        resp = self.api.create_namespaced_deployment(
            body=self.deployment_object, namespace="default"
        )

        print(f"\n[INFO] deployment `{self.deployment_name}` created.\n")
        print("%s\t%s\t\t\t%s\t%s" % ("NAMESPACE", "NAME", "REVISION", "IMAGE"))
        print(
            "%s\t\t%s\t%s\t\t%s\n"
            % (
                resp.metadata.namespace,
                resp.metadata.name,
                resp.metadata.generation,
                resp.spec.template.spec.containers[0].image,
            )
        )
        return resp

    def get_deployment_object(self):
        return self.deployment_object

    # Ignore for now -- we don't need this yet
    def update_deployment(self):
        # Update container image
        self.deployment_object.spec.template.spec.containers[0].image = "nginx:1.16.0"

        # patch the deployment
        resp = self.api.patch_namespaced_deployment(
            name=self.deployment_name, namespace="default", body=self.deployment_object
        )

        print("\n[INFO] deployment's container image updated.\n")
        print("%s\t%s\t\t\t%s\t%s" % ("NAMESPACE", "NAME", "REVISION", "IMAGE"))
        print(
            "%s\t\t%s\t%s\t\t%s\n"
            % (
                resp.metadata.namespace,
                resp.metadata.name,
                resp.metadata.generation,
                resp.spec.template.spec.containers[0].image,
            )
        )

    # Scale the number of replicas in the Deployment.
    def scale_deployment(self, replicas):
        # Update container scale
        self.deployment_object.spec.replicas = replicas

        # patch the deployment
        resp = self.api.patch_namespaced_deployment_scale(
            name=self.deployment_name, namespace="default", body=self.deployment_object
        )

        print("\n[INFO] deployment's container replicas scaled.\n")
        print("%s\t%s\t\t\t%s\t%s" % ("NAMESPACE", "NAME", "REVISION", "REPLICAS"))
        print(
            "%s\t\t%s\t%s\t\t%s\n"
            % (
                resp.metadata.namespace,
                resp.metadata.name,
                resp.metadata.generation,
                resp.spec.replicas,
            )
        )

    # Restart the Deployment
    def restart_deployment(self):
        # update `spec.template.metadata` section
        # to add `kubectl.kubernetes.io/restartedAt` annotation
        self.deployment_object.spec.template.metadata.annotations = {
            "kubectl.kubernetes.io/restartedAt": datetime.datetime.utcnow()
            .replace(tzinfo=pytz.UTC)
            .isoformat()
        }

        # patch the deployment
        resp = self.api.patch_namespaced_deployment(
            name=self.deployment_name, namespace="default", body=self.deployment_object
        )

        print("\n[INFO] deployment `nginx-deployment` restarted.\n")
        print("%s\t\t\t%s\t%s" % ("NAME", "REVISION", "RESTARTED-AT"))
        print(
            "%s\t%s\t\t%s\n"
            % (
                resp.metadata.name,
                resp.metadata.generation,
                resp.spec.template.metadata.annotations,
            )
        )

    # Delete the Deployment.
    def delete_deployment(self):
        # Delete deployment
        resp = self.api.delete_namespaced_deployment(
            name=self.deployment_name,
            namespace="default",
            body=client.V1DeleteOptions(
                propagation_policy="Foreground", grace_period_seconds=5
            ),
        )
        print(f"\n[INFO] deployment `{self.deployment_name}` deleted.")


def main(args):
    # Configs can be set in Configuration class directly or using helper
    # utility. If no argument provided, the config will be loaded from
    # default location.
    config.load_kube_config()
    apps_v1 = client.AppsV1Api()
    dname = args.deploymentname
    depl_file = args.f

    # Uncomment the following lines to enable debug logging
    # c = client.Configuration()
    # c.debug = True
    # apps_v1 = client.AppsV1Api(api_client=client.ApiClient(configuration=c))

    # Read yaml file to get JSON formatted version of the deployment
    with open(path.join(path.dirname(__file__), depl_file)) as f:
        dep = yaml.safe_load(f)


    # Create Deployment object (not to be confused with V1Deployment object from the API)
    deployment = Deployment(apps_v1, dep, dname)
    
    # Try to create the Deployment if it doesn't already exist.
    try:
        deployment.create_deployment()
    except Exception as e:
        print('Previous Deployments may still be deleting...')
        print()
        print(f'ERROR: {e}')
        return 0

    deployment.scale_deployment(5)
    time.sleep(20)
    deployment.scale_deployment(10)
    time.sleep(20)
    deployment.scale_deployment(15)
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--deploymentname')
    parser.add_argument('--f')
    args = parser.parse_args()
    main(args)