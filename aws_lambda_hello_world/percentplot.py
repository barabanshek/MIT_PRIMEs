import matplotlib.pyplot as plt
import pandas as pd
times = pd.read_csv("recorded_data.csv")
times = times.values.tolist()
times.sort()
#round to 3 sig figs convert to miliseconds
times = [round(temp[1], 2)*1000 for temp in times]
percents = [x/5 for x in range(500)]
plt.scatter(times, percents)
plt.xlabel("Time in ms")
plt.ylabel("Percent %")
plt.savefig("percentplot.png")
plt.show()

