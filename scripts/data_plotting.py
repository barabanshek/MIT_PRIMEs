import matplotlib.ticker as mtick
import matplotlib.pyplot as plt
import pickle
from matplotlib.pyplot import figure
import numpy as np
import seaborn as sns
import argparse


def main(args):
    benchmark = args.benchmark
    sns.set_style('darkgrid')
    with open(f'./data/{benchmark}/{benchmark}_tail_lats_50.pickle', 'rb') as handle:
        tail_lats_50 = pickle.load(handle)

    with open(f'./data/{benchmark}/{benchmark}_tail_lats_95.pickle', 'rb') as handle:
        tail_lats_95 = pickle.load(handle)

    with open(f'./data/{benchmark}/{benchmark}_tail_lats_99.pickle', 'rb') as handle:
        tail_lats_99 = pickle.load(handle)

    tail_lats_50 = dict(sorted(tail_lats_50.items()))
    tail_lats_95 = dict(sorted(tail_lats_95.items()))
    tail_lats_99 = dict(sorted(tail_lats_99.items()))

    all_tail_lats = [tail_lats_50, tail_lats_95, tail_lats_99]
    pcts = [50, 95, 99]

    plt.tight_layout()
    plt.figure(figsize=(20, 6), dpi=80)

    figure, axis = plt.subplots(1, len(all_tail_lats))

    for i, tail_lats, pct in zip(range(len(all_tail_lats)), all_tail_lats, pcts):
        ax = axis[i]

        xs = np.array(list(tail_lats.keys()))
        ys = np.array(list(tail_lats.values()))
        print(xs)
        print(ys)

        medians = {}
        uppers = {}
        lowers = {}
        for j in range(len(xs)):
            medians[xs[j]] = np.median(ys[j])
            std = np.std(ys[j])
            uppers[xs[j]] = std
            lowers[xs[j]] = std

        median_xs = np.array(list(medians.keys()))
        median_ys = np.array(list(medians.values()))
        val_dict = {}
        for i in range(len(median_xs)):
            val_dict[median_xs[i]] = median_ys[i]
        print(f'ALL {pct}th PERCENTILE MEDIAN VALUES: {val_dict}')
        errors = np.array([[lowers[median_xs[j]], uppers[median_xs[j]]] for j in range(len(uppers))]).T
        # ax.errorbar(median_xs, median_ys, yerr=errors, ecolor='r')
        ax.errorbar(median_xs, median_ys)
        ax.set_title(f'{pct}th percentile latencies vs. RPS')
        ax.set_ylabel(f'Average {pct}% pct latency [milliseconds]')
        ax.set_xlabel('RPS')

    fig = plt.gcf()
    fig.set_size_inches(18.5, 10.5)
    fig.suptitle(f'Latencies for 50th, 95th, and 99th percentiles for {benchmark}', fontsize=20)

    plt.savefig(f'./graphs/latencies/{benchmark}_QoS.pdf')

    plt.xlabel('rps')
    plt.ylabel('Average 99th pct latency [milliseconds]')

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--benchmark')
    args = parser.parse_args()

    main(args)
