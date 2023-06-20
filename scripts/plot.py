import pandas as pd
import argparse
import plotly.express as px
import numpy as np
import matplotlib.pyplot as plt

def main(args):
    df = pd.read_csv(args.filename)
    xs = [a for a in range(1,11)]
    y_fifty = []
    y_ninety = []
    y_ninetynine = []
    fifty_std = []
    ninety_std = []
    ninetynine_std = []
    for x in range(1, 11):
        fifty = df.loc[df['rps'] == x]['50%'].values.tolist()
        ninety = df.loc[df['rps'] == x]['90%'].values.tolist()
        ninetynine = df.loc[df['rps'] == x]['99%'].values.tolist()
        fifty_std.append(np.std(fifty))
        ninety_std.append(np.std(ninety))
        ninetynine_std.append(np.std(ninetynine))
        y_fifty.append(fifty[2])
        y_ninety.append(ninety[2])
        y_ninetynine.append(ninetynine[2])

    plt.errorbar(xs, y_fifty, yerr = fifty_std, label = "50%")
    plt.errorbar(xs, y_ninety, yerr = ninety_std, label = "90%")
    plt.errorbar(xs, y_ninetynine, yerr = ninetynine_std, label = "99%")
    plt.legend()
    plt.show()

#python3 plot.py --filename --title

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--filename')
    args = parser.parse_args()
    main(args)
