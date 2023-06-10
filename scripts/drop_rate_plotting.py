import matplotlib.ticker as mtick
import matplotlib.pyplot as plt
import pickle
from matplotlib.pyplot import figure
import numpy as np
import seaborn as sns

with open('drop_rates.pickle', 'rb') as handle:
    drop_rates = pickle.load(handle)
drop_rates = dict(sorted(drop_rates.items()))
print(drop_rates)
sns.set_style('darkgrid')

xs = np.array(list(drop_rates.keys()))
ys = np.array(list(drop_rates.values()))

avgs = {}
uppers = {}
lowers = {}
for i in range(len(xs)):
    avgs[xs[i]] = np.mean(ys[i])
    uppers[xs[i]] = max(ys[i]) - avgs[xs[i]]
    lowers[xs[i]] = avgs[xs[i]] - min(ys[i]) 

print(lowers)
print(uppers)
avg_xs = np.array(list(avgs.keys()))
avg_ys = np.array(list(avgs.values()))
errors = np.array([[lowers[avg_xs[j]], uppers[avg_xs[j]]] for j in range(len(uppers))]).T

plt.errorbar(avg_xs, avg_ys, yerr=errors)

plt.xlabel('rps')
plt.ylabel('drop rate')
print('done')
plt.savefig('drop_rates.pdf')