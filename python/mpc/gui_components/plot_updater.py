"""Plot updater component for real-time measurement visualization."""

import threading
import time
import numpy as np
import random

from mock_time_controller import safe_zmq_exec, safe_acquire_histograms
from utils.plot import filter_histogram_bins


class PlotUpdater:
    """Manages real-time plot updates with histogram and correlation data."""
    
    def __init__(self, fig, ax, canvas, tc, default_acq_duration, bin_width, 
                 default_bin_count, default_histograms):
        self.fig = fig
        self.ax = ax
        self.canvas = canvas

        self.tc = tc
        self.default_acq_duration = default_acq_duration
        self.bin_width = bin_width
        self.default_bin_count = default_bin_count
        self.default_histograms = default_histograms

        self.continue_update = False
        self.thread = None

        self.plot_histogram = False
        self.normalize_plot = False

        # State exposed for other panels
        self.histograms = {}
        self.correlation_series = np.zeros((4, 20))
        self.last_correlation = [0, 0, 0, 0]
        self.beutes_szamok = [0, 0, 0, 0]

    def _update_measurements(self):
        """Acquire histograms and update correlation data."""
        from utils.acquisitions import acquire_histograms
        from utils.common import zmq_exec
        
        # Acquire histograms
        self.histograms = safe_acquire_histograms(
            self.tc, self.default_acq_duration, self.bin_width, 
            self.default_bin_count, self.default_histograms, acquire_histograms
        )

        # Update correlation rolling window (sum of each histogram)
        for i, (_, histogram) in enumerate(self.histograms.items()):
            self.correlation_series[i, 0:19] = self.correlation_series[i, 1:20]
            try:
                self.correlation_series[i, 19] = int(np.sum(histogram))
            except Exception:
                self.correlation_series[i, 19] = 0

        # Last correlation snapshot
        for i in range(4):
            self.last_correlation[i] = int(self.correlation_series[i, 19])

        # Live counters from TC
        for j in range(1, 5):
            try:
                self.beutes_szamok[j - 1] = int(safe_zmq_exec(self.tc, f"INPUt{j}:COUNter?", zmq_exec))
            except Exception:
                self.beutes_szamok[j - 1] = random.randint(20000, 100000)

    def _draw_correlation_plot(self):
        """Draw correlation time series plot."""
        from .config import CORRELATION_COLORS, CORRELATION_LABELS
        
        data = self.correlation_series.copy()
        ylim = int(max(1, np.max(data)) / 5000) * 5000 + 5000
        
        if self.normalize_plot:
            col_sum = np.sum(data, axis=0)
            with np.errstate(divide='ignore', invalid='ignore'):
                data = np.nan_to_num(data / col_sum, nan=0.0, posinf=0.0, neginf=0.0)
            ylim = 1
        
        for i in range(4):
            self.ax.plot(data[i], color=CORRELATION_COLORS[i], marker='o', 
                        linestyle='', label=CORRELATION_LABELS[i])
        
        self.ax.legend(loc='upper left')
        self.ax.set_ylim([0, ylim])
        self.ax.set_yticks(np.linspace(0, ylim, 11))
        self.ax.set_title('Koincidencia mérés')
        self.ax.set_xlabel('Adat')
        self.ax.set_ylabel('Beütések')
        self.ax.set_xticks(range(0, 20))

    def _draw_histogram_plot(self):
        """Draw correlation histograms."""
        from .config import HISTOGRAM_COLORS, HISTOGRAM_LABELS
        
        try:
            max_bin_count = max(len(h) for h in self.histograms.values())
        except Exception:
            max_bin_count = 5000
        
        self.ax.set(xlabel="ps", ylabel="Darab")
        self.ax.set_xlim(0, max_bin_count * self.bin_width)
        
        for idx, (hist_title, histogram) in enumerate(self.histograms.items()):
            title = f"Histogram {hist_title}" if isinstance(hist_title, int) else hist_title
            bins = filter_histogram_bins(histogram, self.bin_width)
            xp, yp = tuple(bins.keys()), tuple(bins.values())
            self.ax.bar(xp, yp, align="edge", width=self.bin_width, alpha=0.1)
            self.ax.step(xp, yp, color=HISTOGRAM_COLORS[idx % len(HISTOGRAM_COLORS)], 
                        where="post", label=title, alpha=1)
        
        self.ax.legend(HISTOGRAM_LABELS)
        self.ax.set_xticks(range(0, max_bin_count * self.bin_width + 1, 200))
        self.ax.set_title('Korrelációs hisztogrammok')

    def _draw_plot(self):
        """Update the plot based on current mode."""
        self.ax.clear()

        if not self.plot_histogram:
            self._draw_correlation_plot()
        else:
            self._draw_histogram_plot()

        self.canvas.draw()

    def _loop(self):
        """Main update loop running in background thread."""
        while self.continue_update:
            self._update_measurements()
            self._draw_plot()
            time.sleep(0.1)

    def start(self):
        """Start the background update thread."""
        if self.continue_update:
            return
        self.continue_update = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop the background update thread."""
        if not self.continue_update:
            return
        self.continue_update = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
