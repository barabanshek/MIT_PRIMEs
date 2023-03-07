import os
import time
import numpy as np
import pickle

instances = int(input("How many times do you want to run?\n"))
all_times = {}

def run(instances, delay):
    times = []
    for i in range(instances):
        start = time.time()
        os.system('curl https://k1d9e5uk0j.execute-api.us-east-1.amazonaws.com/Prod/hello/')
        t = round((time.time() - start), 2)
        times.append(t)
        if i != instances-1:
            time.sleep(1*delay)
    all_times[delay] = times
    

for i in [0, 1]:
    run(instances, i)    
with open('filename.pickle', 'wb') as handle:
    pickle.dump(all_times, handle, protocol=pickle.HIGHEST_PROTOCOL)