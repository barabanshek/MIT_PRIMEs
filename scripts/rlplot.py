import pandas as pd
import argparse
import plotly.express as px
import numpy as np
import matplotlib.pyplot as plt

def main():
    df = pd.read_csv("results.csv")
    xs = [a for a in range(49)]
    y = df['containerConcurrency']
    plt.plot(xs, y)
    plt.xlabel("episode number")
    plt.ylabel("container concurrency")
    plt.show()

#python3 rlplot.py

if __name__ == "__main__":
    main()
