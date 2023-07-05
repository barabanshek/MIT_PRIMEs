import pandas as pd
import argparse
import plotly.express as px
import numpy as np
import matplotlib.pyplot as plt

def main(args):
    df = pd.read_csv(args.filename)
    xs = [a for a in range(100,1200, 100)]
    y_fifty = []
    y_ninety = []
    y_ninetynine = []
    fifty_std = []
    ninety_std = []
    ninetynine_std = []
    avg1 = []
    avg2 = []
    avg3 = []
    for x in range(100, 1200, 100):
        fifty = df.loc[df['rps'] == x]['50%'].values.tolist()
        ninety = df.loc[df['rps'] == x]['90%'].values.tolist()
        ninetynine = df.loc[df['rps'] == x]['99%'].values.tolist()
        fifty_std.append(np.std(fifty))
        ninety_std.append(np.std(ninety))
        ninetynine_std.append(np.std(ninetynine))
        y_fifty.append(fifty[int((len(fifty)-1)/2)])
        y_ninety.append(ninety[int((len(ninety)-1)/2)])
        y_ninetynine.append(ninetynine[int((len(ninetynine)-1)/2)])
        avg1.append(np.average(fifty))
        avg2.append(np.average(ninety))
        avg3.append(np.average(ninetynine))

    #plt.errorbar(xs, y_fifty, yerr = fifty_std, label = "50%")
    #plt.errorbar(xs, y_ninety, yerr = ninety_std, label = "90%")
    #plt.errorbar(xs, y_ninetynine, yerr = ninetynine_std, label = "99%")
    plt.plot(xs, avg1, label = "50%")
    plt.plot(xs, avg2, label = "90%")
    plt.plot(xs, avg3, label = "99%")
    plt.xlabel("rps")
    plt.ylabel("latency (ms)")
    plt.title(args.title)
    plt.legend()
    plt.show()

#python3 plot.py --filename --title

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--filename')
    parser.add_argument('--title')
    args = parser.parse_args()
    main(args)
