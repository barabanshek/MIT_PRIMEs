import matplotlib.pyplot as plt
import pickle
from matplotlib.pyplot import figure
import numpy as np
# import pylustrator
# pylustrator.start()

with open('filename.pickle', 'rb') as handle:
    all_times = pickle.load(handle)

max_time = max([max(i) for i in all_times.values()])
max_instances = max([len(i) for i in all_times.values()])

plt.tight_layout()
plt.figure(figsize=(20, 6), dpi=80)

figure, axis = plt.subplots(1, len(all_times.keys()))

for ind, i in zip(range(len(all_times.keys())), all_times.keys()):
    axis[ind].hist(all_times[i], rwidth=0.9)
    axis[ind].set_xticks(np.arange(0, max_time+0.2, 0.2))
    axis[ind].set_yticks(np.arange(0, max_instances+1, 1))
    axis[ind].set_title(f"{i} min delay")
    axis[ind].set_ylabel('Instances')
    axis[ind].set_xlabel('Execution time (s)')


fig = plt.gcf()
fig.set_size_inches(18.5, 10.5)
fig.suptitle("Execution times for pinging Hello World", fontsize=20)

plt.savefig('foo.pdf', bbox_inches='tight')
