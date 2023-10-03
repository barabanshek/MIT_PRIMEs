import argparse
import yaml
import json
import random
from rl_env import *

from yaml.loader import SafeLoader
from os import path
from k8s_env_shim import Env
from pprint import pprint
from setup_service import Service
from setup_deployment import Deployment
import numpy as np

states = 4
actions = 27


class q_net:
    def __init__ (self):
        #cpu rounded to 40m, mem rounded to nearest 100Mi, 625 states and 27 actions per (+ / / -) actions
        self.q_table = np.random.rand((25, 25, 27))
        self.counter = np.zeros((25, 25, 27))
        self.epsilon = 0.1

    def updateQ(self, state, action, reward):
        self.q_table[state[0]][state[1]][action]=self.q_table[state[0]][state[1]][action]* self.counter[state[0]][state[1]][action]+reward
        self.counter[state[0]][state[1]][action] += 1
        self.q_table[state[0]][state[1]][action]/=self.counter[state[0]][state[1]][action]
    
    def getaction(self, state):
        temp = np.random.random()
        action = [0,0]
        if temp<self.epsilon:
            action[0] = (random.randint(0, 24))
            action[1] = (random.randint(0, 24))
        else:
            action = np.random.choice(np.where(self.q_table[state[0]][state[1]] == self.q_table[state[0]][state[1]].max())[0])
        
        return action






