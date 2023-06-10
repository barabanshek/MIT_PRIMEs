##EpsilonGreedy Agent
import random
import numpy as np

class EpsilonGreedyAgent:
    num_actions: int
    epsilon: float = 0.1
    states: int
    def __post_init__(self):
        self.reset()

    def reset(self):
        self.action_counts = np.zeros(self.num_actions, self.states, dtype=int)
        self.Q = np.zeros(self.num_actions, self.states, dtype=float) 
    
    def update_Q(self, action, state, reward):
        self.action_counts[action] += 1
        self.Q[action][state] += (1.0 / self.action_counts[action][state]) * (reward - self.Q[action][state])
    
    def get_action(self, state):
        prob = np.random.random()
        selected_value = -1
        if prob>self.epsilon:
            selected_value = np.random.choice(np.where(self.Q[state] == self.Q[state].max())[0])
        else:
            selected_value = random.randint(0, self.num_actions-1)
        return selected_value