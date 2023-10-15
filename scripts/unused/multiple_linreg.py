import argparse
import pandas as pd
import pickle
from data_processing import Data, compute_rps_deltas
import numpy as np

def main(args):
    benchmark = args.b
    data_file = args.f
    xlabel1 = args.x1
    xlabel2 = args.x2
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
    data_object = Data(df, data_id)

    linreg, x_test, y_test = data_object.get_multiple_regression(benchmark, xlabel1, xlabel2, ylabel)
    
    from sklearn.metrics import r2_score
    y_test_ = linreg.predict(x_test)
    mae = np.mean(np.absolute(y_test_ - y_test))
    mse = np.mean((y_test_ - y_test)** 2)
    r2 = r2_score(y_test_, y_test)
    print(mae, mse, r2)
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--f')
    parser.add_argument('-b')
    parser.add_argument('-x1')
    parser.add_argument('-x2')
    parser.add_argument('-y')
    args = parser.parse_args()
    main(args)