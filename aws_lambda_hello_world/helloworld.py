import time
import os
import csv
#"http://127.0.0.1:3000/"
print("interval:")
interval = int(input())
print("iterations:")
iterations = int(input())
delays = {}
def a(interval2, iterations2):
    temp = []
    for i in range(iterations2):
        start = time.perf_counter()
        os.system("curl http://127.0.0.1:3000/hello")
        end = time.perf_counter()
        elapsed = end-start
        temp.append(str(elapsed))
        time.sleep(interval2)
    delays.update({interval2:temp})
a(interval, iterations)
with open("recorded_data.csv", "w", newline = '') as file:
    writer = csv.writer(file)
    writer.writerow(["interval", "time"])
    for x in delays[interval]:
        writer.writerow([interval, x])

print(delays)