import pandas as pd
import argparse
import pickle
import os
import matplotlib.pyplot as plt

from scipy import stats

from pprint import pprint

def first_index(arr):
    return arr[0]

def plot_data(xs, ys, xlabel, ylabel):
    plt.scatter(xs, ys)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.savefig('plot.png')

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
    
class Data:
    def __init__(self, df, data_id):
        self.df = df
        self.data_id = data_id
        self.table = {}
        # Clean data with 0 CPU utilization.
        index = self.df[self.df['cpu_util'].map(standardize_format) == 0].index
        self.df.drop(index, inplace=True)
        print("Cleaned.")
        cleaned_data_file = f"cleaned_data_{self.data_id}.csv"
        self.df.to_csv(cleaned_data_file, columns=self.df.columns)

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

    def get_correlation_table(self, ignored_columns=[]):
        for col1 in self.df.columns:
            if col1 not in ignored_columns:
                self.table['column'] = [col2 for col2 in self.df.columns if col2 not in ignored_columns]
                self.table[col1] = [self.get_correlations(col1, col2) for col2 in self.df.columns if col2 not in ignored_columns]
        table_df = pd.DataFrame(data=self.table)
        return table_df

def main(args):
    data_file = args.f
    data_id = data_file[10:20]
    with open(data_file, 'rb') as handle:
        data = pickle.load(handle)
        df = pd.DataFrame(data)
    # with open(f'./data/successes_{data_id}.pickle', 'rb') as handle:
    #     successes = pickle.load(handle)
    #     print(f'Benchmarks: {len(successes)}')
    #     print(f'Successes: {sum(successes)}')
    pd.set_option('display.max_columns', None)
    # remove RPS column
    df.columns = ['timestamp',
                  'benchmark', 
                  'cpu_util',
                  'mem_util',
                  'replicas',
                  'duration', 
                  'issued', 
                  'completed', 
                  'rps_real', 
                  'rps_target', 
                  '50th', '90th', '99th', '99.9th', 
                  'avg_cpu_idle', 'avg_cpu_user', 'avg_cpu_system',
                              'avg_mem_free',
                              'avg_net_transmit (bps)', 'avg_net_receive (bps)']
    df['rps_delta'] = df['rps_real'] - df['rps_target']
    df.to_csv(f"data_{data_id}.csv", columns=df.columns)
    data_object = Data(df, data_id)
    # col1 = 'rps_delta'
    # col2 = '50th'
    table_df = data_object.get_correlation_table(ignored_columns=['timestamp', 'benchmark'])
    table_df.to_csv(f"correlation_table_{data_id}.csv", columns=table_df.columns)
    table_df.style.background_gradient(cmap ='viridis')\
            .set_properties(**{'font-size': '20px'})
    table_df.style.background_gradient(cmap ='viridis')\
        .to_excel('./correlations.xlsx', engine='openpyxl')
    print("Heatmap saved.")
    # print(df)
    # xs = [standardize_format(cpu) for cpu in df[col1]]
    # ys = [standardize_format(rep) for rep in df[col2]]
    # pearson = stats.pearsonr(xs, ys)
    # spearman = stats.spearmanr(xs, ys)
    # kendalltau = stats.kendalltau(xs, ys)
    # print(pearson.statistic)
    # print(spearman.statistic)
    # print(kendalltau.statistic)
    # plot_data(xs, ys, 'Average CPU %', 'Replicas')

    # plot_data(xs, ys, col1, col2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--f')
    args = parser.parse_args()
    main(args)