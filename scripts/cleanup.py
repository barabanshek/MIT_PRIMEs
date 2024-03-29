from subprocess import run
import os
import argparse

def delete_files_in_directory(directory_path):
  try:
    files = os.listdir(directory_path)
    for file in files:
      file_path = os.path.join(directory_path, file)
      if os.path.isfile(file_path):
        os.remove(file_path)
    print("All files deleted successfully.")
  except OSError:
    print("Error occurred while deleting files.")


def main(args):
  run('''kubectl delete deployment --all''', shell=True)
  run('''kubectl delete service --all''', shell=True)
  run('''kubectl delete hpa --all''', shell=True)
  if args.a:
      run('''kubectl delete pods --all --grace-period=0 --force''', shell=True)
  run('''kubectl apply -f ~/vSwarm/benchmarks/hotel-app/yamls/knative/database.yaml''', shell=True)
  run('''kubectl apply -f ~/vSwarm/benchmarks/hotel-app/yamls/knative/memcached.yaml''', shell=True)
  delete_files_in_directory('./k8s-yamls/tmp/')
  run('''find . -name 'rps*.csv' -delete''', shell=True)
  print('Deleted all latency files.')
# Use `-a` for aggressive cleanup.
if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('-a', action='store_true')
  args = parser.parse_args()
  main(args)