import matplotlib.ticker as mtick
import matplotlib.pyplot as plt
import pickle
from matplotlib.pyplot import figure
import numpy as np
import seaborn as sns

with open('tail_lats.pickle', 'rb') as handle:
    tail_lat = pickle.load(handle)
tail_lat = dict(sorted(tail_lat.items()))
print(tail_lat)
sns.set_style('darkgrid')
xs = np.array(list(tail_lat.keys()))
ys = np.array(list(tail_lat.values()))
plt.plot(xs, ys)
plt.xlabel('rps')
plt.ylabel('99th pct latency [microseconds]')
print('done')
plt.savefig('qos.pdf')
