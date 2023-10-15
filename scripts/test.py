import os
import pickle
from itertools import product
import numpy as np
from subprocess import run
import time
import torch
from dqn_main import DQN, ReplayMemory, Transition
def main():
  model = torch.jit.load('saved_models/gmkavb/target_net.pth')
  model.eval()
  with open('saved_models/gmkavb/replay_buffer.pickle', 'rb') as handle:
    buffer = pickle.load(handle)
  print(len(buffer.memory))
if __name__ == "__main__":
  main()