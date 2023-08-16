import datetime
import pytz

from os import path
from subprocess import run
from pprint import pprint
from kubernetes import client

class Deployment:

    def __init__(self, dep, api):
        # k8s API
        self.api = api
        # deployment as a json formatted dict
        self.dep = dep
        # name of deployment
        self.deployment_name = dep['metadata']['name']

        # namespace of deployment
        self.namespace = dep['metadata']['namespace']

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
            metadata=client.V1ObjectMeta(name=self.deployment_name, namespace=self.namespace),
            spec=spec,
        )


    def create_deployment(self):
        # Create deployment
        resp = self.api.create_namespaced_deployment(
            body=self.deployment_object, namespace="default"
        )

        print(f"\n[UPDATE] deployment `{self.deployment_name}` created.\n")
        print("%s\t%s\t\t\t%s\t%s" % ("NAMESPACE", "NAME", "REVISION", "IMAGE"))
        # print(
        #     "%s\t\t%s\t%s\t\t%s\n"
        #     % (
        #         resp.metadata.namespace,
        #         resp.metadata.name,
        #         resp.metadata.generation,
        #         resp.spec.template.spec.containers[0].image,
        #     )
        # )
        return resp
    
    # Check if all pods are ready.
    def is_ready(self):
        # Command to check rollout status
        status_cmd = f"kubectl rollout status deployment/{self.deployment_name}"
        # Run the command.
        ret = run(status_cmd, capture_output=True, shell=True, universal_newlines=True).stdout
        # Check if the output message shows successful rollout
        return ret == '''deployment "''' + self.deployment_name + '''" successfully rolled out\n'''

    def get_deployment_object(self):
        return self.deployment_object

    # Ignore for now -- we don't need this yet
    # def update_deployment(self):
    #     # Update container image
        # self.deployment_object.spec.template.spec.containers[0].image = "nginx:1.16.0"

    #     # patch the deployment
    #     resp = self.api.patch_namespaced_deployment(
    #         name=self.deployment_name, namespace="default", body=self.deployment_object
    #     )

    #     print("\n[INFO] deployment's container image updated.\n")
    #     print("%s\t%s\t\t\t%s\t%s" % ("NAMESPACE", "NAME", "REVISION", "IMAGE"))
    #     print(
    #         "%s\t\t%s\t%s\t\t%s\n"
    #         % (
    #             resp.metadata.namespace,
    #             resp.metadata.name,
    #             resp.metadata.generation,
    #             resp.spec.template.spec.containers[0].image,
    #         )
    #     )

    # Scale the number of replicas in the Deployment.
    def scale_deployment(self, replicas):
        # Update container scale
        self.deployment_object.spec.replicas = replicas

        # patch the deployment
        resp = self.api.patch_namespaced_deployment_scale(
            name=self.deployment_name, namespace=self.namespace, body=self.deployment_object
        )

        print("\n[UPDATE] deployment's container replicas scaled.\n")
        # print("%s\t%s\t\t\t%s\t%s" % ("NAMESPACE", "NAME", "REVISION", "REPLICAS"))
        # print(
        #     "%s\t\t%s\t%s\t\t%s\n"
        #     % (
        #         resp.metadata.namespace,
        #         resp.metadata.name,
        #         resp.metadata.generation,
        #         resp.spec.replicas,
        #     )
        # )

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
            name=self.deployment_name, namespace=self.namespace, body=self.deployment_object
        )

        print(f"\n[RESTART] deployment `{self.deployment_name}` restarted.\n")
        # print("%s\t\t\t%s\t%s" % ("NAME", "REVISION", "RESTARTED-AT"))
        # print(
        #     "%s\t%s\t\t%s\n"
        #     % (
        #         resp.metadata.name,
        #         resp.metadata.generation,
        #         resp.spec.template.metadata.annotations,
        #     )
        # )

    # Delete the Deployment.
    def delete_deployment(self):
        # Delete deployment
        resp = self.api.delete_namespaced_deployment(
            name=self.deployment_name,
            namespace=self.namespace,
            body=client.V1DeleteOptions(
                propagation_policy="Foreground", grace_period_seconds=5
            ),
        )
        print(f"\n[DELETED] deployment `{self.deployment_name}` deleted.")
