import matplotlib.ticker as mtick
import matplotlib.pyplot as plt
import pickle
from matplotlib.pyplot import figure
import numpy as np
import seaborn as sns

sns.set_style('darkgrid')
with open('tail_lats.pickle', 'rb') as handle:
    tail_lats = pickle.load(handle)

    tail_lats = dict(sorted(tail_lats.items()))
    print(tail_lats)

xs = np.array(list(tail_lats.keys()))
ys = np.array(list(tail_lats.values()))

avgs = {}
uppers = {}
lowers = {}
print(xs)
print(ys)
for i in range(len(xs)):
    avgs[xs[i]] = np.mean(ys[i])
    uppers[xs[i]] = max(ys[i]) - avgs[xs[i]]
    lowers[xs[i]] = avgs[xs[i]] - min(ys[i]) 

print(lowers)
print(uppers)
avg_xs = np.array(list(avgs.keys()))
avg_ys = np.array(list(avgs.values()))
errors = np.array([[lowers[avg_xs[j]], uppers[avg_xs[j]]] for j in range(len(uppers))]).T

plt.errorbar(avg_xs, avg_ys, yerr=errors, ecolor='r')
plt.xlabel('rps')
plt.ylabel('Average 99th pct latency [microseconds]')
print('done')
plt.savefig('qos.pdf')
