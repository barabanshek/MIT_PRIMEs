import pandas as pd
import argparse
import pickle
import os

from pprint import pprint

def main(args):
    data_file = args.f
    data_id = data_file[10:20]
    with open(data_file, 'rb') as handle:
        data = pickle.load(handle)
    with open(f'./data/successes_{data_id}.pickle', 'rb') as handle:
        successes = pickle.load(handle)
        print(f'Benchmarks: {len(successes)}')
        print(f'Successes: {sum(successes)}')
        df = pd.DataFrame(data)
    pd.set_option('display.max_columns', None)
    # remove RPS column
    df.columns = ['Timestamp',
                  'Benchmark', 
                  'Average CPU (%)',
                  'Average Mem (%)',
                  'Replicas',
                  'Duration (s)', 
                  'Requests Issued', 
                  'Requests Completed', 
                  'Real RPS', 
                  'Target RPS', 
                  '50th', '90th', '99th', '99.9th', 
                  'avg_cpu_idle', 'avg_cpu_user', 'avg_cpu_system',
                              'avg_mem_free',
                              'avg_net_transmit (bps)', 'avg_net_receive (bps)']
    # print(df)
    df.to_csv(f"data_{data_id}.csv", columns=df.columns)
    # os.remove(data_file)
    return df

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--f')
    args = parser.parse_args()
    main(args)