import pandas as pd
import argparse
from plotly.subplots import make_subplots
import plotly.graph_objects as go


def main(args):
    df = pd.read_csv(args.filename)

    fig = make_subplots(rows=1, cols=2)

    fig = px.line(df, x = 'rps', y = df.columns[1:], 
    labels = {
        "rps" : "rps",
        "value" : "latency",
        "variable" : "percent"
    }, 
    title=args.plottitle)
    
    fig.show()

#python3 plot.py --filename --plottitle

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--filename')
    parser.add_argument('--plottitle')
    args = parser.parse_args()
    main(args)
