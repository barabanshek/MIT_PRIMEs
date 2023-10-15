import argparse
import pandas as pd
import pickle
from data_processing import Data, compute_rps_deltas

def main(args):
    benchmark = args.b
    data_file = args.f
    xlabel = args.x
    ylabel = args.y
    data_id = data_file[-17:-7]
    # Load pickle file
    with open(data_file, 'rb') as handle:
        data = pickle.load(handle)
        df = pd.DataFrame(data)
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
    folder = './data-plots'
    data_object = Data(df, data_id)

    pearson = data_object.get_correlations(benchmark, xlabel, ylabel, metric='pearson')

    if args.c:
        cleaned = 'cleaned'
        data_object.get_cleaned_data()
    else:
        cleaned = 'not cleaned'
    plot_title = f"{ylabel} vs. {xlabel} for benchmark '{benchmark}' ({cleaned})\nr={pearson}"
    data_object.plot_data(benchmark, xlabel, ylabel, folder, title=plot_title)

    print(f'Pearson coefficient: {pearson}')

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--f')
    parser.add_argument('-b')
    parser.add_argument('-x')
    parser.add_argument('-y')
    parser.add_argument('-c', action='store_true')
    args = parser.parse_args()
    main(args)