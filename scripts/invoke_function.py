import time
import os
import re
import argparse
from multiprocessing import Process, Manager
import yaml
from subprocess import run
from os import path
from yaml import SafeLoader
import random

INVOKER_FILE = '~/vSwarm/tools/invoker/'

def create_service(service_file):

    # Create Service, Deployment, and HPA
    ret = run(f'kubectl apply -f {service_file}', shell=True, capture_output=True)
    if ret.returncode != 0:
        assert False, f"\n[ERROR] Failed to run command `kubectl apply -f {service_file}`\n[ERROR] Error message: {ret.stderr}"

    print(f"\n[UPDATE] service with manifest `{service_file}` created.")

def get_service_ip(name):
    # Get Cluster IP
    ip_cmd = f"kubectl get service/{name} -o jsonpath='{{.spec.clusterIP}}'"
    ret = run(ip_cmd, capture_output=True, shell=True, universal_newlines=True)
    if ret.returncode != 0:
        assert False, f"\n[ERROR] Failed to run command `kubectl get service/{name} -o jsonpath='{{.spec.clusterIP}}`\n[ERROR] Error message: {ret.stderr}"

    ip = ret.stdout

    return ip

# Invoke Service using invoker and return stats
def invoke_service(service_name, duration, rps, port):
    ip = get_service_ip(service_name)

    # Setup hostname file
    os.system('''echo '[ { "hostname": "''' + ip + '''" } ]' > ''' + INVOKER_FILE + f'''endpoints_{service_name}.json''')
    print(f"[INFO] Hostname file has been set up at {INVOKER_FILE}/endpoints_{service_name}.json")

    # Format the invoker command nicely
    invoker_cmd_join_list = [f'{INVOKER_FILE}/invoker',
                            '-dbg',
                            f'-port {port}',
                            f'-time {duration}',
                            f'-rps {rps}',
                            f'-latf {service_name}.csv',
                            f'-endpointsFile {INVOKER_FILE}/endpoints_{service_name}.json']
    invoker_cmd = ' '.join(invoker_cmd_join_list)

    # Run invoker while redirecting output to separate file
    print("[RUNNING] Invoking with command at second {}".format(time.time()), f'`{invoker_cmd}`\n')
    
    stdout = os.popen(invoker_cmd)

    # Find latency file and parse stats
    stat_issued = None
    stat_completed = None
    stat_real_rps = None
    stat_target_rps = None
    stat_lat_filename = None
    for line in stdout:
        m = re.search('The measured latencies are saved in (.*csv)', line)
        if m:
            stat_lat_filename = m.group(1)
        m = re.search('completed requests: ([0-9]*), ([0-9]*)', line)
        if m:
            stat_issued = (int)(m.group(1))
            stat_completed = (int)(m.group(2))
        m = re.search(
            'target RPS: ([0-9]*\.?[0-9]*) \/ ([0-9]*\.?[0-9]*)', line)
        if m:
            stat_real_rps = (float)(m.group(1))
            stat_target_rps = (float)(m.group(2))

    # Check if latency file exists and return stats.
    if stat_lat_filename == None:
        assert False, "[ERROR] stat_lat_filename was not found."
    else:
        print("stat_completed= ", stat_completed)
        return (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename

def is_ready(deployment_name):
    # Command to check rollout status
    status_cmd = f"kubectl rollout status deployment/{deployment_name}"
    # Run the command.
    ret = run(status_cmd, capture_output=True, shell=True, universal_newlines=True).stdout
    # Check if the output message shows successful rollout
    return ret == '''deployment "''' + deployment_name + '''" successfully rolled out\n'''

# Cleanup functions when done.
def cleanup(aggressive=False, delete_manifests=True):
    run('''kubectl delete deployment --all''', shell=True)
    run('''kubectl delete service --all''', shell=True)
    run('''kubectl delete hpa --all''', shell=True)
    if aggressive:
        run('''kubectl delete pods --all --grace-period=0 --force''', shell=True)
    run('''kubectl apply -f ~/vSwarm/benchmarks/hotel-app/yamls/knative/database.yaml''', shell=True)
    run('''kubectl apply -f ~/vSwarm/benchmarks/hotel-app/yamls/knative/memcached.yaml''', shell=True)
    run('''find . -name 'rps*.csv' -delete''', shell=True)
    print('Deleted all latency files.')

def scale(f, n):
    scale_cmd = f'kubectl scale deployment/{f} --replicas={n}'
    run(scale_cmd, shell=True)

def main(args):
    manifest = args.file
    duration = args.d
    rps = args.rps

    functions = ['fibonacci-python', 'hotel-app-profile', 'hotel-app-geo']
    services = {}
    for function in functions:
        file_name = f"k8s-yamls/{function}.yaml"
        create_service(file_name)
        with open(file_name) as f:
            dep, svc, hpa = yaml.load_all(f, Loader=SafeLoader)
        service_name = svc['metadata']['name']
        port = svc['spec']['ports'][0]['port']
        services[function] = (service_name, port)

    for i in range(50):
        rnd_l_s = random.sample(range(1, 10), 3)
        print(f'Iteration {i+1}, scaling: {rnd_l_s}')

        ppp = []
        for i in range(0,3):
            p = Process(target=scale, args=(functions[i], rnd_l_s[i]))
            ppp.append(p)
            p.start()
            # scale_cmd = f'kubectl scale deployment/{functions[i]} --replicas={rnd_l_s[i]}'
            # run(scale_cmd, shell=True)
        for p in ppp:
            p.join()

        for i in range(0,3):
            while not is_ready(functions[i]):
                continue

        # print(f'Finished scaling in {time.time() - start} seconds.')
        processes = []
        for f_name in functions:
            p = Process(target=invoke_service, args=(f_name, duration, rps, port))
            processes.append(p)
            p.start()
        for p in processes:
            p.join()
        # x = 5
        # print(f'Sleeping for {x} seconds...')
        # time.sleep(x)

        

if __name__ == "__main__":
    cleanup(True)
    exit(0)

    parser = argparse.ArgumentParser()
    # Config file for benchmarks
    parser.add_argument('--file')
    parser.add_argument('-d')
    parser.add_argument('-rps')
    #TODO: add -h argument
    args = parser.parse_args()
    main(args)
