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


def create_deployment_object(dep):
    # Configureate Pod template container
    conts = dep['spec']['template']['spec']['containers']
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
        metadata=client.V1ObjectMeta(labels=dep['metadata']['labels']),
        spec=client.V1PodSpec(containers=containers),
    )

    # Create the specification of deployment
    spec = client.V1DeploymentSpec(
        replicas=dep['spec']['replicas'], template=template, selector=dep['spec']['selector'])

    # Instantiate the deployment object
    deployment = client.V1Deployment(
        dep['apiVersion'],
        kind="Deployment",
        metadata=client.V1ObjectMeta(name=deployment_name),
        spec=spec,
    )
    return deployment

def create_deployment(api, deployment):
    # Create deployment
    resp = api.create_namespaced_deployment(
        body=deployment, namespace="default"
    )

    print("\n[INFO] deployment `nginx-deployment` created.\n")
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

# ignore for now
def update_deployment(api, deployment):
    # Update container image
    deployment.spec.template.spec.containers[0].image = "nginx:1.16.0"

    # patch the deployment
    resp = api.patch_namespaced_deployment(
        name=deployment_name, namespace="default", body=deployment
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

def scale_deployment(api, deployment, replicas):
    # Update container scale
    deployment.spec.replicas = replicas

    # patch the deployment
    resp = api.patch_namespaced_deployment_scale(
        name=deployment_name, namespace="default", body=deployment
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

# buggy
def restart_deployment(api, deployment):
    # update `spec.template.metadata` section
    # to add `kubectl.kubernetes.io/restartedAt` annotation
    deployment.spec.template.metadata.annotations = {
        "kubectl.kubernetes.io/restartedAt": datetime.datetime.utcnow()
        .replace(tzinfo=pytz.UTC)
        .isoformat()
    }

    # patch the deployment
    resp = api.patch_namespaced_deployment(
        name=deployment_name, namespace="default", body=deployment
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


def delete_deployment(api):
    # Delete deployment
    resp = api.delete_namespaced_deployment(
        name=deployment_name,
        namespace="default",
        body=client.V1DeleteOptions(
            propagation_policy="Foreground", grace_period_seconds=5
        ),
    )
    print(f"\n[INFO] deployment `{deployment_name}` deleted.")


def main(args):
    # Configs can be set in Configuration class directly or using helper
    # utility. If no argument provided, the config will be loaded from
    # default location.
    config.load_kube_config()
    apps_v1 = client.AppsV1Api()
    global deployment_name
    deployment_name = args.deploymentname
    depl_file = args.f

    # Uncomment the following lines to enable debug logging
    # c = client.Configuration()
    # c.debug = True
    # apps_v1 = client.AppsV1Api(api_client=client.ApiClient(configuration=c))

    # Create a deployment object with client-python API. The deployment we
    # created is same as the `nginx-deployment.yaml` in the /examples folder.

    # read yaml file to get JSON formatted version of the deployment

    with open(path.join(path.dirname(__file__), depl_file)) as f:
        dep = yaml.safe_load(f)

    deployment = create_deployment_object(dep)
    
    try:
        # return deployment object
        create_deployment(apps_v1, deployment)
    except Exception as e:
        print("Deployment may already exist, please delete existing deployment with \'kubectl delete -f <DEPLOYMENT_FILE>\'")
        print(e)
        return 0

    scale_deployment(apps_v1, deployment, 5)
    time.sleep(5)
    scale_deployment(apps_v1, deployment, 10)
    time.sleep(5)
    scale_deployment(apps_v1, deployment, 15)
    time.sleep(30)

    # deployment = create_deployment(apps_v1, dep)
    # scale_deployment(apps_v1, deployment, 3)
    # scale_deployment(apps_v1, deployment, 3)

    restart_deployment(apps_v1, deployment)

    delete_deployment(apps_v1)
    # except Exception as e:
    #     delete_deployment(apps_v1)
    #     print("Exception occurred: %s\n" % e)
    #     return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--deploymentname')
    parser.add_argument('--f')
    args = parser.parse_args()
    main(args)