import matplotlib.ticker as mtick
import matplotlib.pyplot as plt
import pickle
from matplotlib.pyplot import figure
import numpy as np
import seaborn as sns

sns.set_style('darkgrid')
with open('tail_lats_50.pickle', 'rb') as handle:
    tail_lats_50 = pickle.load(handle)

with open('tail_lats_95.pickle', 'rb') as handle:
    tail_lats_95 = pickle.load(handle)

with open('tail_lats_99.pickle', 'rb') as handle:
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

    avgs = {}
    uppers = {}
    lowers = {}
    print(xs)
    print(ys)
    for j in range(len(xs)):
        avgs[xs[j]] = np.mean(ys[j])
        uppers[xs[j]] = max(ys[j]) - avgs[xs[j]]
        lowers[xs[j]] = avgs[xs[j]] - min(ys[j]) 

    avg_xs = np.array(list(avgs.keys()))
    avg_ys = np.array(list(avgs.values()))
    errors = np.array([[lowers[avg_xs[j]], uppers[avg_xs[j]]] for j in range(len(uppers))]).T
    ax.errorbar(avg_xs, avg_ys, yerr=errors, ecolor='r')
    ax.set_title(f'{pct}th percentile latencies vs. RPS')
    ax.set_ylabel(f'Average {pct}% pct latency [microseconds]')
    ax.set_xlabel('RPS')

fig = plt.gcf()
fig.set_size_inches(18.5, 10.5)
fig.suptitle('Latencies for 50th, 95th, and 99th percentiles', fontsize=20)

plt.savefig('qos.pdf')

plt.xlabel('rps')
plt.ylabel('Average 99th pct latency [microseconds]')