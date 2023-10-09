import pickle
import pandas as pd
import argparse
from data_processing import make_dir
import matplotlib.pyplot as plt

def plot_reward(df):
    x = df['step']
    y = df['reward']
    plt.plot(x, y)
    plt.title('Reward vs. Step')
    plt.xlabel('Step')
    plt.ylabel('Reward')
    plt.savefig('rewards.png')

def plot_replicas(df):
    x = df['step']
    ys = [df[df.columns[i]] for i in range(7, len(df.columns))]
    colors = ['r', 'b', 'g']
    for i in range(len(ys)):
        y = ys[i]
        col = colors[i]
        plt.plot(x, y, color=col)
    plt.xlabel('Step')
    plt.ylabel('Replicas')
    plt.title('Replicas vs. Step for all benchmarks')
    plt.savefig('replicas.png')
    

def main(args):
    file = args.f
    id = file[-13:-7]
    with open(file, 'rb') as handle:
        data = pickle.load(handle)
        df = pd.DataFrame(data)
    make_dir('./rl-csv-data')
    df.to_csv(f'./rl-csv-data/{id}.csv', columns=df.columns)
    plot_reward(df)
    plot_replicas(df)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--f')
    args = parser.parse_args()
    main(args)