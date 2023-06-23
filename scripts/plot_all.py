import argparse
import os

def main(args):
    benchmark = args.benchmark
    data_plot = f"python3 data_plotting.py --benchmark {benchmark}"
    drop_rate_plot = f"python3 drop_rate_plotting.py --benchmark {benchmark}"
    delta_plot = f"python3 rps_delta_plotting.py --benchmark {benchmark}"

    os.system(data_plot + '\n' + drop_rate_plot + '\n' + delta_plot)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--benchmark')
    args = parser.parse_args()

    main(args)
