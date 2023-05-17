import time
import os
import csv
#"http://127.0.0.1:3000/"
print("interval:")
interval = int(input())
print("iterations:")
iterations = int(input())
delays = {}

#define function to request
def a(interval2, iterations2):
    temp = []
    for i in range(iterations2):
        start = time.perf_counter()
        os.system("curl https://9wfkyhs07f.execute-api.ap-northeast-1.amazonaws.com/Prod/hello/")
        end = time.perf_counter()
        elapsed = end-start
        temp.append(str(elapsed))
        time.sleep(interval2)
    delays.update({interval2:temp})

a(interval, iterations)

#write the file
with open("recorded_data.csv", "w", newline = '') as file:
    writer = csv.writer(file)
    writer.writerow(["interval", "time"])
    for x in delays[interval]:
        writer.writerow([interval, x])

print(delays)
