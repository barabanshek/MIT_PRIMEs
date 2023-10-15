import os
import pickle
import re

def main():
  # print(re.findall(r'rps', 'rps979.03_fibonacci-python-abcdeabcde.csv'))
  with open('successes.pickle', 'rb') as handle:
    data = pickle.load(handle)
    print(f'Benchmarks: {len(data)}')
    print(f'Successes: {sum(data)}')

if __name__ == "__main__":
  main()