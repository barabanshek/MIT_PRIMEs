import pandas as pd
import argparse
import pickle

from pprint import pprint

def main():
    data_file = 'data.pickle'
    with open(data_file, 'rb') as handle:
        data = pickle.load(handle)
    df = pd.DataFrame(data)
    pd.set_option('display.max_columns', None)
    df.columns = ['Timestamp',
                  'Benchmark', 
                  'Average CPU (%)',
                  'Average Mem (%)',
                  'Replicas',
                  'RPS', 
                  'Duration (s)', 
                  'Requests Issued', 
                  'Requests Completed', 
                  'Real RPS', 
                  'Target RPS', 
                  '50th', '90th', '99th', '99.9th', 
                  'avg_cpu_idle', 'avg_cpu_user', 'avg_cpu_system',
                              'avg_mem_free',
                              'avg_net_transmit (bps)', 'avg_net_receive (bps)']
    print(df)
    return df

if __name__ == "__main__":
    main()