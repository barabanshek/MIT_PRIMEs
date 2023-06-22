import matplotlib.ticker as mtick
import matplotlib.pyplot as plt
import pickle
from matplotlib.pyplot import figure
import numpy as np
import seaborn as sns
import argparse

def main(args):
    benchmark = args.benchmark
    with open(f'./data/{benchmark}/{benchmark}_rps_deltas.pickle', 'rb') as handle:
        rps_deltas = pickle.load(handle)
    rps_deltas = dict(sorted(rps_deltas.items()))
    sns.set_style('darkgrid')

    xs = np.array(list(rps_deltas.keys()))
    ys = np.array(list(rps_deltas.values()))

    medians = {}
    uppers = {}
    lowers = {}
    for i in range(len(xs)):
        medians[xs[i]] = np.median(ys[i])
        std = np.std(ys[i])
        uppers[xs[i]] = std
        lowers[xs[i]] = std

    median_xs = np.array(list(medians.keys()))
    median_ys = np.array(list(medians.values()))
    val_dict = {}
    for i in range(len(median_xs)):
        val_dict[median_xs[i]] = median_ys[i]
    print(f'ALL RPS DELTA MEDIAN VALUES: {val_dict}')
    errors = np.array([[lowers[median_xs[j]], uppers[median_xs[j]]] for j in range(len(uppers))]).T

    plt.errorbar(median_xs, median_ys, yerr=errors)
    plt.title(f"Target RPS vs. Difference between Effective RPS \nand Target RPS for {benchmark}")

    plt.xlabel('Target RPS')
    plt.ylabel('Effective RPS - Target RPS')
    print('done')
    plt.savefig(f'./graphs/rps_deltas/{benchmark}_rps_deltas.pdf')

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--benchmark')
    args = parser.parse_args()

    main(args)