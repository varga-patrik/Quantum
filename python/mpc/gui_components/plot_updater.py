"""Plot updater component for real-time measurement visualization."""

import threading
import time
import numpy as np
import random
import logging

from mock_time_controller import safe_zmq_exec, safe_acquire_histograms
from utils.plot import filter_histogram_bins

logger = logging.getLogger(__name__)


class PlotUpdater:
    """Manages real-time plot updates with histogram and correlation data."""
    
    def __init__(self, fig, ax, canvas, tc, default_acq_duration, bin_width, 
                 default_bin_count, default_histograms, peer_connection=None, app_ref=None):
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
        
        # Peer connection for cross-site correlation
        self.peer_connection = peer_connection
        self.app_ref = app_ref  # Reference to main app for accessing correlation pairs

        # State exposed for other panels
        self.histograms = {}
        self.correlation_series = np.zeros((8, 20))  # Expanded to 8 for cross-site pairs
        self.last_correlation = [0, 0, 0, 0, 0, 0, 0, 0]
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

        # Update correlation rolling window (sum of each histogram) - first 4 are local
        for i, (_, histogram) in enumerate(self.histograms.items()):
            if i < 4:
                self.correlation_series[i, 0:19] = self.correlation_series[i, 1:20]
                try:
                    self.correlation_series[i, 19] = int(np.sum(histogram))
                except Exception:
                    self.correlation_series[i, 19] = 0

        # Last correlation snapshot for local
        for i in range(4):
            self.last_correlation[i] = int(self.correlation_series[i, 19])
        
        # Send histogram data to peer if connected
        if self.peer_connection and self.peer_connection.is_connected():
            try:
                # Convert histograms to JSON-serializable format
                hist_data = {str(k): [int(x) for x in v] for k, v in self.histograms.items()}
                self.peer_connection.send_command('HISTOGRAM_DATA', {'histograms': hist_data})
            except Exception as e:
                logger.error(f"Failed to send histogram data: {e}")
        
        # Calculate cross-site correlations if we have remote data
        self._update_cross_site_correlations()

        # Live counters from TC
        for j in range(1, 5):
            try:
                self.beutes_szamok[j - 1] = int(safe_zmq_exec(self.tc, f"INPUt{j}:COUNter?", zmq_exec))
            except Exception:
                self.beutes_szamok[j - 1] = random.randint(20000, 100000)
    
    def _update_cross_site_correlations(self):
        """Calculate cross-site correlations for selected pairs."""
        if not self.app_ref or not hasattr(self.app_ref, 'correlation_pairs'):
            logger.debug("No app_ref or correlation_pairs")
            return
        
        # Check if peer is still connected - if not, clear remote data and zero correlations
        if not self.peer_connection or not self.peer_connection.is_connected():
            logger.debug("Peer not connected - clearing cross-site correlations")
            if hasattr(self.app_ref, 'remote_histograms'):
                self.app_ref.remote_histograms = {}
            # Zero out cross-site correlation values (indices 4-7)
            for pair_idx in range(4, 8):
                self.correlation_series[pair_idx, :] = 0
                self.last_correlation[pair_idx] = 0
            return
        
        if not hasattr(self.app_ref, 'remote_histograms') or not self.app_ref.remote_histograms:
            logger.debug(f"No remote histograms (has_attr={hasattr(self.app_ref, 'remote_histograms')}, empty={not self.app_ref.remote_histograms if hasattr(self.app_ref, 'remote_histograms') else 'N/A'})")
            return
        
        # Get correlation pairs from app
        pairs = self.app_ref.correlation_pairs
        logger.debug(f"Updating cross-site correlations for {len(pairs)} pairs, remote keys: {list(self.app_ref.remote_histograms.keys())}")
        
        # Calculate correlation for each pair (stored in indices 4-7)
        for idx, (local_in, remote_in) in enumerate(pairs[:4]):  # Max 4 pairs for now
            pair_idx = 4 + idx
            self.correlation_series[pair_idx, 0:19] = self.correlation_series[pair_idx, 1:20]
            
            try:
                # Get local and remote histograms for this pair
                local_hist = self.histograms.get(local_in, [])
                remote_hist = self.app_ref.remote_histograms.get(remote_in, [])
                
                if len(local_hist) > 0 and len(remote_hist) > 0:
                    # Cross-correlation: sum of products of coincident bins
                    min_len = min(len(local_hist), len(remote_hist))
                    correlation = sum(local_hist[i] * remote_hist[i] for i in range(min_len))
                    self.correlation_series[pair_idx, 19] = int(correlation)
                    self.last_correlation[pair_idx] = int(correlation)
                    logger.debug(f"  Pair {idx} ({local_in}↔{remote_in}): corr={correlation}, local_len={len(local_hist)}, remote_len={len(remote_hist)}")
                else:
                    self.correlation_series[pair_idx, 19] = 0
                    self.last_correlation[pair_idx] = 0
                    logger.debug(f"  Pair {idx} ({local_in}↔{remote_in}): NO DATA (local={len(local_hist)}, remote={len(remote_hist)})")
            except Exception as e:
                logger.error(f"  Pair {idx}: ERROR {e}")
                self.correlation_series[pair_idx, 19] = 0
                self.last_correlation[pair_idx] = 0

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
        
        # Draw local correlations (first 4)
        for i in range(4):
            self.ax.plot(data[i], color=CORRELATION_COLORS[i], marker='o', 
                        linestyle='', label=CORRELATION_LABELS[i])
        
        # Draw cross-site correlations (indices 4-7) if peer connected
        if self.app_ref and hasattr(self.app_ref, 'correlation_pairs') and self.app_ref.correlation_pairs:
            cross_colors = ['purple', 'orange', 'brown', 'pink']
            logger.debug(f"Drawing cross-site correlations for {len(self.app_ref.correlation_pairs)} pairs")
            for idx, (local_in, remote_in) in enumerate(self.app_ref.correlation_pairs[:4]):
                pair_idx = 4 + idx
                role_label = "Client" if self.app_ref.computer_role == "computer_b" else "Server"
                remote_role = "Server" if self.app_ref.computer_role == "computer_b" else "Client"
                label = f"{role_label}-{local_in}↔{remote_role}-{remote_in}"
                logger.debug(f"  Pair {idx}: {label}, data range: {data[pair_idx].min():.0f}-{data[pair_idx].max():.0f}")
                self.ax.plot(data[pair_idx], color=cross_colors[idx], marker='x', 
                            linestyle='--', label=label)
        else:
            logger.debug(f"NOT drawing cross-site: app_ref={self.app_ref is not None}, "
                        f"has_pairs={hasattr(self.app_ref, 'correlation_pairs') if self.app_ref else False}, "
                        f"pairs_count={len(self.app_ref.correlation_pairs) if self.app_ref and hasattr(self.app_ref, 'correlation_pairs') else 0}")
        
        self.ax.legend(loc='upper left', fontsize=8)
        self.ax.set_ylim([0, ylim])
        self.ax.set_yticks(np.linspace(0, ylim, 11))
        self.ax.set_title('Koincidencia mérés (Local + Cross-Site)')
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
