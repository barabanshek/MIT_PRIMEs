from online_net import *
from rl_env import *
import threading

iterations = 100
episodes = 100


def main(args):
    RLenv = RLEnv(args)
    agent = q_net()
    oldstate = RLenv.states
    newstate
    rewards = []
    actions = []
    states = []
    for iii in range(iterations):
        for jjj in range(episodes):
            action = agent.getaction(oldstate)
            newstate, reward = RLenv.step(action)
            agent.updateQ(oldstate, action, reward)
            rewards.append(reward)
            actions.append(action)
            states.append(oldstate)
            oldstate = newstate


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--config')
    args = parser.parse_args()
    main(args)