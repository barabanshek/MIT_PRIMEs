import matplotlib.pyplot as plt
import pandas as pd

times = pd.read_csv("recorded_data.csv")
times = times.values.tolist()
x = []
y = []
counter = 1
#move data into lists
for temp in times:
    x.append(counter)
    y.append(temp[1])
    counter+=1
#sort data
z = y
z.sort()
z = [round(elem, 2) for elem in z]
z = [elem*1000 for elem in z]
count = 0
#create bar graph
x1 = []
y1 = []
pastelem = z[0]
x1.append(pastelem)
for temp in z:
    if temp == pastelem:
        count+=1
    else:
        pastelem = temp
        x1.append(temp)
        y1.append(count)
        count = 1
y1.append(count)
print(len(x1))
print(len(y1))
#draw percentile lines
ninetypercent = z[450]
ninetyninepercent = z[495]
plt.plot([ninetypercent, ninetypercent], [0, 25], color = 'gold')
plt.plot([ninetyninepercent, ninetyninepercent], [0, 25], color = 'green')
#graph
plt.bar(x1, y1, width = 25)
plt.xlabel("Response time in ms")
plt.ylabel("Number of requests")
#plt.scatter(x, z)
#plt.ylabel("delay in miliseconds")
plt.show()
