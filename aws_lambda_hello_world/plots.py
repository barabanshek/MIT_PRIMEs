import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

times = pd.read_csv("recorded_data.csv")
print(times)
times = times.values.tolist()
x = []
y = []
counter = 1
for temp in times:
    x.append(counter)
    y.append(temp[1])
    counter+=1
print(y)
#print(times)
plt.scatter(x, y)
plt.show()