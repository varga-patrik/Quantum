import logging
from typing import Any, Dict, List
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)


def should_filter_bin(histogram, i):
    if histogram[i] != 0:
        return True

    if i in [0, len(histogram)-1]:
        return True

    if histogram[i-1] or histogram[i+1]:
        return True

    return False

def filter_histogram_bins(histogram, bin_width):
    h = histogram + [histogram[-1]]

    bins = {
        bin_no * bin_width: bin_value
        for bin_no, bin_value in enumerate(h)
        if should_filter_bin(h, bin_no)
    }
    return bins

def plot_histograms(
    histograms: Dict[Any, List[int]],
    bin_width,
    title="Histogram",
    log_axis=False
):
    _, ax = plt.subplots(num=title)

    max_bin_count = max(len(histogram) for histogram in histograms.values())

    ax.set(xlabel="ps", ylabel="counts")
    ax.set_xlim(0, max_bin_count * bin_width)

    for hist_title, histogram in histograms.items():

        if isinstance(hist_title, int):
            hist_title = f"Histogram {hist_title}"

        bins = filter_histogram_bins(histogram, bin_width)

        xp, yp = tuple(bins.keys()), tuple(bins.values())
        
        bar_plot = ax.bar(xp, yp, align="edge", width=bin_width, alpha=0.1)
        color = bar_plot.patches[0].get_facecolor()
        ax.step(xp, yp, color=color, where="post", label=hist_title, alpha=1)

    if log_axis:
        ax.set_yscale('log')

    ax.legend()
    plt.tight_layout()
    plt.show() 

def plot_histograms2(
    histograms: Dict[Any, List[int]],
    bin_width,
    title="Histogram",
    log_axis=False
):
    _, ax = plt.subplots(num=title)

    max_bin_count = max(len(histogram) for histogram in histograms.values())

    ax.set(xlabel="ps", ylabel="counts")
    ax.set_xlim(0, max_bin_count * bin_width)

    for hist_title, histogram in histograms.items():

        if isinstance(hist_title, int):
            hist_title = f"Histogram {hist_title}"

        bins = filter_histogram_bins(histogram, bin_width)

        xp, yp = tuple(bins.keys()), tuple(bins.values())
        
        bar_plot = ax.bar(xp, yp, align="edge", width=bin_width, alpha=0.1)
        color = bar_plot.patches[0].get_facecolor()
        ax.step(xp, yp, color=color, where="post", label=hist_title, alpha=1)

    if log_axis:
        ax.set_yscale('log')

    ax.legend()
    plt.tight_layout()
    plt.show(block=False) 

