import pandas as pd
import argparse
import pickle

from pprint import pprint

def main(args):
    data_file = args.data
    with open(data_file, 'rb') as handle:
        data = pickle.load(handle)
    df = pd.DataFrame(data)
    df.columns = ['Benchmark', 'RPS', 'Duration (s)', 'Requests Issued', 'Requests Completed', 'Real RPS', 'Target RPS', '50th', '90th', '99th', '99.9th']
    print(df.head(10))
    return df

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--data')
    args = parser.parse_args()
    main(args)