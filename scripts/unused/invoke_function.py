import time
import os
import re
import argparse
import yaml
from subprocess import run
from os import path
from yaml import SafeLoader

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
    os.system('''echo '[ { "hostname": "''' + ip + '''" } ]' > ''' + INVOKER_FILE + '''endpoints.json''')
    print(f"[INFO] Hostname file has been set up at {INVOKER_FILE}/endpoints.json")

    # Format the invoker command nicely
    invoker_cmd_join_list = [f'{INVOKER_FILE}/invoker',
                            '-dbg',
                            f'-port {port}',
                            f'-time {duration}',
                            f'-rps {rps}',
                            f'-latf {service_name}.csv',
                            f'-endpointsFile {INVOKER_FILE}/endpoints.json']
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
        return (stat_issued, stat_completed), (stat_real_rps, stat_target_rps), stat_lat_filename

def main(args):
    manifest = args.file
    duration = args.d
    rps = args.rps

    create_service(manifest)
    time.sleep(10)

    with open(path.join(path.dirname(__file__), manifest)) as f:
        dep, svc, hpa = yaml.load_all(f, Loader=SafeLoader)
    service_name = svc['metadata']['name']
    port = svc['spec']['ports'][0]['port']


    ret = invoke_service(service_name, duration, rps, port)
    print(ret)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # Config file for benchmarks
    parser.add_argument('--file')
    parser.add_argument('-d')
    parser.add_argument('-rps')
    #TODO: add -h argument
    args = parser.parse_args()
    main(args)