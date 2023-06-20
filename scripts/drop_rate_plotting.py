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

medians = {}
uppers = {}
lowers = {}
for i in range(len(xs)):
    medians[xs[i]] = np.median(ys[i])
    std = np.std(ys[i])
    uppers[xs[i]] = std
    lowers[xs[i]] = std

print(lowers)
print(uppers)
median_xs = np.array(list(medians.keys()))
median_ys = np.array(list(medians.values()))
errors = np.array([[lowers[median_xs[j]], uppers[median_xs[j]]] for j in range(len(uppers))]).T

plt.errorbar(median_xs, median_ys, yerr=errors)

plt.xlabel('rps')
plt.ylabel('drop rate')
print('done')
plt.savefig('drop_rates.pdf')