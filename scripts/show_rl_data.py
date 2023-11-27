import pickle
import pandas as pd
import argparse
from data_processing import make_dir
import matplotlib.pyplot as plt
import numpy as np
    
# Plot all relevant metrics on a single plot.
def plot_all(df, id):
    fig, ax = plt.subplots(3, 1)
    X = df['step']
    # Plot reward.
    reward_y = df['reward']
    ax[0].plot(X, reward_y)
    ax[0].set_title('Reward vs. Step')
    ax[0].set_ylabel('Reward')
    # Plot replicas.
    # A bit hacky way to get the benchmarks, can fix later.
    replicas_ys = [df[df.columns[k]] for k in range(len(df.columns)-3, len(df.columns))]
    colors = ['r', 'b', 'g']
    for c in range(len(replicas_ys)):
        replicas_y = replicas_ys[c]
        col = colors[c]
        ax[1].plot(X, replicas_y, color=col)
    ax[1].set_ylabel('Replicas')
    ax[1].set_title('Replicas vs. Step for all benchmarks')
    # Plot mean latency.
    lat_y = df['mean_latency']
    ax[2].plot(X, lat_y)
    ax[2].set_title('Mean Latency (mu-s) vs. Step')
    ax[2].set_xlabel('Step')
    ax[2].set_ylabel('Mean Latency (mu-s)')
    # Save figure.
    fig.tight_layout()
    fig.set_figwidth(10.0)
    fig.set_figheight(10.0)
    make_dir(f'./rl-plots/run-{id}')
    plt.savefig(f'./rl-plots/run-{id}.png')
    
def main(args):
    file = args.f
    id = file[-13:-7]
    with open(file, 'rb') as handle:
        data = pickle.load(handle)
        df = pd.DataFrame(data)
    make_dir('./rl-csv-data')
    df.to_csv(f'./rl-csv-data/{id}.csv', columns=df.columns)
    # episodes = np.unique(np.array(df['episode']))
    plot_all(df, id)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--f')
    args = parser.parse_args()
    main(args)