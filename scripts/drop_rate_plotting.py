import matplotlib.ticker as mtick
import matplotlib.pyplot as plt
import pickle
from matplotlib.pyplot import figure
import numpy as np
import seaborn as sns
import argparse

def main(args):
    benchmark = args.benchmark
    with open(f'./data/{benchmark}/{benchmark}_drop_rates.pickle', 'rb') as handle:
        drop_rates = pickle.load(handle)
    drop_rates = dict(sorted(drop_rates.items()))
    sns.set_style('darkgrid')

    xs = np.array(list(drop_rates.keys()))
    ys = np.array(list(drop_rates.values()))

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
    plt.title(f"Target RPS vs. Request Drop Rate for {benchmark}")
    plt.xlabel('Target RPS')
    plt.ylabel('Request Drop Rate')
    print('done')
    plt.savefig(f'./graphs/drop_rates/{benchmark}_drop_rates.pdf')

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--benchmark')
    args = parser.parse_args()

    main(args)