import seaborn as sns
import pickle
import matplotlib.pyplot as plt

with open('filename.pickle', 'rb') as handle:
    logs = pickle.load(handle)

def plot(logs, x_key, y_key, legend_key, **kwargs):
    nums = len(logs[legend_key].unique())
    palette = sns.color_palette("hls", nums)
    if 'palette' not in kwargs:
        kwargs['palette'] = palette
    fig = sns.lineplot(x=x_key, y=y_key, data=logs, hue=legend_key, **kwargs)
    fig.figure.savefig('data.pdf')

def main(logs=logs):
    plot(logs, logs['step'], logs['reward'], 'Alg')

if __name__ == "__main__":
    main()