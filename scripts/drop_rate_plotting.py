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
plt.plot(xs, ys)
plt.xlabel('rps')
plt.ylabel('drop rate')
print('done')
plt.savefig('drop_rates.pdf')