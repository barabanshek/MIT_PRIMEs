import pandas as pd
import argparse
import pickle
import os
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from scipy import stats
from pathlib import Path
from pprint import pprint

def first_index(arr):
    return arr[0]

def standardize_format(entry):
    try:
        length = len(entry)
        if length == 1:
            return entry[0]
        # Skip chained functions.
        else:
            return 'skip'
    except:
        return entry

def compute_rps_deltas(reals, targets):
    deltas = []
    for real, target in zip(reals, targets):
        # Compute percent difference.
        deltas.append(np.abs(real - target)/np.mean([real, target]))
    return deltas

def make_dir(dir_name):
    Path(dir_name).mkdir(parents=True, exist_ok=True)

class Data:
    def __init__(self, df, data_id):
        self.df = df
        self.data_id = data_id
        self.table = {}
        # Clean data with 0 CPU utilization.
        index = self.df[self.df['cpu_util'].map(standardize_format) == 0].index
        self.df.drop(index, inplace=True)
        
    def get_cleaned_data(self, folder='./data-analysis'):
        make_dir(folder)
        cleaned_data_file = f"{folder}/cleaned_data_{self.data_id}.csv"
        self.df.to_csv(cleaned_data_file, columns=self.df.columns)
        print("Cleaned.")

    def plot_data(self, xlabel, ylabel, save_folder, title):
        xs = []
        ys = []
        for m1, m2 in zip(self.df[xlabel], self.df[ylabel]):
            if standardize_format(m1) != 'skip' and standardize_format(m2) != 'skip':
                xs.append(standardize_format(m1))
                ys.append(standardize_format(m2))

        plt.scatter(xs, ys)
        plt.title(title)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.plot(np.unique(xs), np.poly1d(np.polyfit(xs, ys, 1))(np.unique(xs)), color='r')
        
        make_dir(save_folder)
        plt.savefig(f'{save_folder}/{self.data_id}_{xlabel}-{ylabel}_plot.png')
        print('Done plotting.')

    def get_correlations(self, col1, col2, metric='pearson'):
        xs = []
        ys = []
        for m1, m2 in zip(self.df[col1], self.df[col2]):
            if standardize_format(m1) != 'skip' and standardize_format(m2) != 'skip':
                xs.append(standardize_format(m1))
                ys.append(standardize_format(m2))
        # print(len(xs), len(ys))
        # print(ys)
        if metric == 'pearson':
            stat = stats.pearsonr(xs, ys)
        elif metric == 'spearman':
            stat = stats.spearmanr(xs, ys)
        elif metric == 'kendalltau':
            stat = stats.kendalltau(xs, ys)

        return round(stat.statistic, 5)        
        # print(f'Correlation using metric {metric}: {round(stat.statistic, 5)}')

    def get_correlation_table(self, metric='pearson', ignored_columns=[], abs=False):
        correlations_df = self.df.drop(columns=ignored_columns, inplace=False)
        for col1 in correlations_df.columns:
            if col1 not in ignored_columns:
                self.table['column'] = [col2 for col2 in correlations_df.columns]
            if abs:
                self.table[col1] = map(np.abs, [self.get_correlations(col1, col2, metric=metric) for col2 in correlations_df.columns])
            else:
                self.table[col1] = [self.get_correlations(col1, col2, metric=metric) for col2 in correlations_df.columns]
        table_df = pd.DataFrame(data=self.table, columns=correlations_df.columns, index=self.table['column'])
        return table_df
    
    def get_heatmap(self, ignored_columns, metric='pearson', abs=False):
        heatmap_dims = (10, 10)
        fig, ax = plt.subplots(figsize=heatmap_dims)
        table_df = self.get_correlation_table(metric=metric, ignored_columns=ignored_columns, abs=abs)
        heatmap = sns.heatmap(table_df, ax=ax, robust=True, annot=True)
        plt.xticks(rotation=30)
        if abs:
            plt.title(f"Magnitude of Pearson Coefficients for Experiment '{self.data_id}'\n")
        else:
            plt.title(f"Pearson Coefficients for Experiment '{self.data_id}'\n")
        fig = heatmap.get_figure()
        make_dir('./heatmaps')
        if abs:
            fig.savefig(f'./heatmaps/{self.data_id}_abs_{metric}_correlations.png')
        else:
            fig.savefig(f'./heatmaps/{self.data_id}_{metric}_correlations.png')

        print("Heatmap saved.")

def main(args):
    data_file = args.f
    metric = args.m
    data_id = data_file[10:20]
    with open(data_file, 'rb') as handle:
        data = pickle.load(handle)
        df = pd.DataFrame(data)
    with open(f'./data/successes_{data_id}.pickle', 'rb') as handle:
        successes = pickle.load(handle)
        print(f'Benchmarks: {len(successes)}')
        print(f'Successes: {sum(successes)}')
    pd.set_option('display.max_columns', None)
    # remove RPS column
    df.columns = ['timestamp',
                  'benchmark', 
                  'cpu_util',
                  'mem_util',
                  'replicas',
                  'cpu_requests', 'cpu_limits', 'mem_requests', 'mem_limits',
                  'duration', 
                  'issued', 
                  'completed', 
                  'rps_real', 
                  'rps_target', 
                  '50th', '90th', '99th', '99.9th', 
                  'avg_cpu_idle', 'avg_cpu_user', 'avg_cpu_system',
                              'avg_mem_free',
                              'avg_net_transmit (bps)', 'avg_net_receive (bps)']
    df['rps_delta'] = compute_rps_deltas(df['rps_real'], df['rps_target'])
    folder = './data-analysis'
    make_dir(folder)
    df.to_csv(f"{folder}/data_{data_id}.csv", columns=df.columns)
    data_object = Data(df, data_id)
    data_object.get_cleaned_data(folder)

    ignored_columns = ['timestamp', 
                       'benchmark', 
                       'cpu_requests', 'cpu_limits', 'mem_requests', 'mem_limits',
                       'avg_cpu_idle', 
                       'avg_cpu_user', 
                       'avg_cpu_system',
                        'avg_mem_free',
                        'avg_net_transmit (bps)', 
                        'avg_net_receive (bps)']

    data_object.get_heatmap(ignored_columns=ignored_columns, metric=metric, abs=args.a)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--f')
    parser.add_argument('-m', default='pearson')
    parser.add_argument('-a', action='store_true')
    args = parser.parse_args()
    main(args)