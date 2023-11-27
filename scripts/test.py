import os
import pickle
from itertools import product
import numpy as np
from subprocess import run
import time
import torch
from dqn_main import DQN, ReplayMemory, Transition
def main():
  a = np.array([1,2])
  b = np.array([2,3])
  x = np.concatenate((a, b))
  print(x)
if __name__ == "__main__":
  main()