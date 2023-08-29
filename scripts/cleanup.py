from subprocess import run

def main():
    run('''kubectl delete deployment --all''', shell=True)
    run('''kubectl delete service --all''', shell=True)
    run('''kubectl delete hpa --all''', shell=True)
    run('''kubectl apply -f ~/vSwarm/benchmarks/hotel-app/yamls/knative/database.yaml''', shell=True)
    run('''kubectl apply -f ~/vSwarm/benchmarks/hotel-app/yamls/knative/memcached.yaml''', shell=True)
if __name__ == '__main__':
    main()