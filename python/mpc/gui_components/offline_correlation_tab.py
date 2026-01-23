"""
Offline Correlation Analysis Tab

Provides user interface for analyzing coincidences from saved timestamp files
using the calculated time offset. Similar to live correlation but for offline analysis.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
import logging
import threading
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import time

from streaming.timestamp_stream import CoincidenceCounter
from gui_components.helpers import format_number
from gui_components.config import COINCIDENCE_WINDOW_PS

logger = logging.getLogger(__name__)


class OfflineCorrelationTab:
    """GUI tab for offline coincidence analysis from saved timestamp files."""
    
    def __init__(self, parent_frame, app_ref, bg_color='#282828', fg_color='#D4D4D4', 
                 action_color='#007ACC'):
        """
        Initialize the offline correlation analysis tab.
        
        Args:
            parent_frame: Parent tkinter frame (the tab)
            app_ref: Reference to main App instance (for time_offset_ps)
            bg_color: Background color
            fg_color: Foreground color
            action_color: Button color
        """
        self.parent = parent_frame
        self.app_ref = app_ref
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.action_color = action_color
        
        # Coincidence counter
        self.coincidence_counter = CoincidenceCounter(window_ps=COINCIDENCE_WINDOW_PS)
        
        # Channel pair selections (4 channels)
        self.channel_pairs = []
        for i in range(4):
            self.channel_pairs.append({
                'enabled': tk.BooleanVar(value=(i == 0)),  # Ch1 enabled by default
                'local_file': None,
                'remote_file': None,
                'local_label': None,
                'remote_label': None
            })
        
        # Analysis parameters
        self.time_bin_sec = tk.DoubleVar(value=1.0)  # Time bin for histogram
        self.coincidence_window_ps = tk.IntVar(value=COINCIDENCE_WINDOW_PS)
        
        # Results storage
        self.last_results = None
        self.timestamps_local = {}  # {channel: np.array}
        self.timestamps_remote = {}
        
        # Build UI
        self._build_ui()
        
        # Auto-detect files
        self.root.after(500, self._auto_detect_files)
    
    @property
    def root(self):
        """Get root window from parent."""
        return self.parent.winfo_toplevel()
    
    def _build_ui(self):
        """Build the complete UI for the offline correlation tab."""
        # Main container
        container = tk.Frame(self.parent, background=self.bg_color)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Header
        header = tk.Label(container, 
                         text="📊 Offline Correlation Analysis",
                         font=('Arial', 12, 'bold'),
                         background=self.bg_color, foreground=self.fg_color)
        header.pack(pady=(0, 8))
        
        # Top section: File selection and parameters
        top_frame = tk.Frame(container, background=self.bg_color)
        top_frame.pack(fill=tk.X, pady=(0, 5))
        
        # File selection (left)
        self._build_file_selection(top_frame)
        
        # Parameters (right)
        self._build_parameters(top_frame)
        
        # Action buttons
        self._build_action_buttons(container)
        
        # Results section with plots
        self._build_results_section(container)
    
    def _build_file_selection(self, parent):
        """Build file selection section."""
        file_frame = tk.LabelFrame(parent, text="📁 Timestamp Files", 
                                   font=('Arial', 10, 'bold'),
                                   background='#E8F5E9', bd=2, relief=tk.RIDGE,
                                   padx=8, pady=6)
        file_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Header row
        header = tk.Frame(file_frame, background='#E8F5E9')
        header.pack(fill=tk.X, pady=(0, 3))
        
        tk.Label(header, text="", width=3, background='#E8F5E9').pack(side=tk.LEFT)
        tk.Label(header, text="Ch", font=('Arial', 8, 'bold'), width=4,
                background='#E8F5E9').pack(side=tk.LEFT)
        tk.Label(header, text="LOCAL File", font=('Arial', 8, 'bold'), width=32,
                background='#E8F5E9', anchor='w').pack(side=tk.LEFT, padx=3)
        tk.Label(header, text="REMOTE File", font=('Arial', 8, 'bold'), width=32,
                background='#E8F5E9', anchor='w').pack(side=tk.LEFT, padx=3)
        
        # Channel rows
        for ch_idx in range(4):
            self._build_channel_row(file_frame, ch_idx)
        
        # Control buttons
        btn_row = tk.Frame(file_frame, background='#E8F5E9')
        btn_row.pack(fill=tk.X, pady=(6, 0))
        
        tk.Button(btn_row, text="🔍 Auto-Detect",
                 command=self._auto_detect_files,
                 background='#2196F3', foreground='white',
                 font=('Arial', 8), width=12).pack(side=tk.LEFT, padx=2)
        
        tk.Button(btn_row, text="🗑️ Clear All",
                 command=self._clear_all_files,
                 background='#FF5722', foreground='white',
                 font=('Arial', 8), width=10).pack(side=tk.LEFT, padx=2)
    
    def _build_channel_row(self, parent, ch_idx):
        """Build a single channel row."""
        ch_num = ch_idx + 1
        pair = self.channel_pairs[ch_idx]
        
        row = tk.Frame(parent, background='#E8F5E9')
        row.pack(fill=tk.X, pady=1)
        
        # Checkbox
        cb = tk.Checkbutton(row, variable=pair['enabled'], background='#E8F5E9')
        cb.pack(side=tk.LEFT, padx=(0, 3))
        
        # Channel label
        tk.Label(row, text=f"{ch_num}", font=('Arial', 9, 'bold'),
                background='#E8F5E9', width=3, anchor='w').pack(side=tk.LEFT)
        
        # Local file display
        local_label = tk.Label(row, text="(not selected)",
                              font=('Courier New', 7), width=35,
                              background='white', foreground='#999',
                              relief=tk.SUNKEN, anchor='w', padx=2)
        local_label.pack(side=tk.LEFT, padx=2)
        pair['local_label'] = local_label
        
        # Local browse button
        tk.Button(row, text="📂", width=2,
                 command=lambda: self._browse_file(ch_idx, 'local'),
                 background='#4CAF50', foreground='white',
                 font=('Arial', 8)).pack(side=tk.LEFT, padx=1)
        
        # Remote file display
        remote_label = tk.Label(row, text="(not selected)",
                               font=('Courier New', 7), width=35,
                               background='white', foreground='#999',
                               relief=tk.SUNKEN, anchor='w', padx=2)
        remote_label.pack(side=tk.LEFT, padx=2)
        pair['remote_label'] = remote_label
        
        # Remote browse button
        tk.Button(row, text="📂", width=2,
                 command=lambda: self._browse_file(ch_idx, 'remote'),
                 background='#2196F3', foreground='white',
                 font=('Arial', 8)).pack(side=tk.LEFT, padx=1)
    
    def _build_parameters(self, parent):
        """Build parameters section."""
        param_frame = tk.LabelFrame(parent, text="⚙️ Parameters",
                                   font=('Arial', 10, 'bold'),
                                   background='#FFF3E0', bd=2, relief=tk.RIDGE,
                                   padx=8, pady=6)
        param_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(5, 0))
        
        # Time offset display (from config)
        offset_frame = tk.Frame(param_frame, background='#FFF3E0')
        offset_frame.pack(fill=tk.X, pady=2)
        
        tk.Label(offset_frame, text="Time Offset:", background='#FFF3E0',
                font=('Arial', 9)).pack(side=tk.LEFT)
        
        self.offset_label = tk.Label(offset_frame, text="Not set",
                                    font=('Courier New', 9, 'bold'),
                                    background='#FFF3E0', foreground='#1976D2')
        self.offset_label.pack(side=tk.LEFT, padx=5)
        
        tk.Button(offset_frame, text="↻", width=2,
                 command=self._refresh_offset,
                 background='#9E9E9E', foreground='white',
                 font=('Arial', 8)).pack(side=tk.LEFT)
        
        # Coincidence window
        window_frame = tk.Frame(param_frame, background='#FFF3E0')
        window_frame.pack(fill=tk.X, pady=2)
        
        tk.Label(window_frame, text="Window (±ps):", background='#FFF3E0',
                font=('Arial', 9)).pack(side=tk.LEFT)
        tk.Entry(window_frame, textvariable=self.coincidence_window_ps, width=8,
                font=('Courier New', 9)).pack(side=tk.LEFT, padx=5)
        
        # Time bin for histogram
        bin_frame = tk.Frame(param_frame, background='#FFF3E0')
        bin_frame.pack(fill=tk.X, pady=2)
        
        tk.Label(bin_frame, text="Time Bin (s):", background='#FFF3E0',
                font=('Arial', 9)).pack(side=tk.LEFT)
        tk.Entry(bin_frame, textvariable=self.time_bin_sec, width=8,
                font=('Courier New', 9)).pack(side=tk.LEFT, padx=5)
        
        # Refresh offset on load
        self._refresh_offset()
    
    def _build_action_buttons(self, parent):
        """Build action buttons."""
        btn_frame = tk.Frame(parent, background=self.bg_color)
        btn_frame.pack(pady=5)
        
        self.analyze_button = tk.Button(btn_frame, text="🔬 Analyze Correlations",
                                        command=self._start_analysis,
                                        background='#FF9800', foreground='white',
                                        font=('Arial', 10, 'bold'), width=20)
        self.analyze_button.pack(side=tk.LEFT, padx=5)
        
        self.export_button = tk.Button(btn_frame, text="💾 Export Results",
                                       command=self._export_results,
                                       background='#607D8B', foreground='white',
                                       font=('Arial', 10, 'bold'), width=15,
                                       state=tk.DISABLED)
        self.export_button.pack(side=tk.LEFT, padx=5)
    
    def _build_results_section(self, parent):
        """Build results display section with plots."""
        results_frame = tk.Frame(parent, background=self.bg_color)
        results_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        
        # Left: Statistics
        stats_frame = tk.LabelFrame(results_frame, text="📋 Statistics",
                                   font=('Arial', 10, 'bold'),
                                   background='#E8EAF6', bd=2, relief=tk.RIDGE,
                                   padx=8, pady=6)
        stats_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        
        # Status
        self.status_label = tk.Label(stats_frame, text="Ready - Load files and analyze",
                                    font=('Arial', 9), background='#E8EAF6',
                                    foreground='#666', wraplength=180)
        self.status_label.pack(pady=(0, 5))
        
        # Statistics grid
        stats_grid = tk.Frame(stats_frame, background='#E8EAF6')
        stats_grid.pack()
        
        # Duration
        tk.Label(stats_grid, text="Duration:", background='#E8EAF6',
                font=('Arial', 9)).grid(row=0, column=0, sticky='e', padx=3, pady=2)
        self.duration_label = tk.Label(stats_grid, text="---", background='#E8EAF6',
                                       font=('Courier New', 9), width=12, anchor='w')
        self.duration_label.grid(row=0, column=1, sticky='w', padx=3, pady=2)
        
        # Local events
        tk.Label(stats_grid, text="Local Events:", background='#E8EAF6',
                font=('Arial', 9)).grid(row=1, column=0, sticky='e', padx=3, pady=2)
        self.local_events_label = tk.Label(stats_grid, text="---", background='#E8EAF6',
                                           font=('Courier New', 9), width=12, anchor='w')
        self.local_events_label.grid(row=1, column=1, sticky='w', padx=3, pady=2)
        
        # Remote events
        tk.Label(stats_grid, text="Remote Events:", background='#E8EAF6',
                font=('Arial', 9)).grid(row=2, column=0, sticky='e', padx=3, pady=2)
        self.remote_events_label = tk.Label(stats_grid, text="---", background='#E8EAF6',
                                            font=('Courier New', 9), width=12, anchor='w')
        self.remote_events_label.grid(row=2, column=1, sticky='w', padx=3, pady=2)
        
        # Total coincidences
        tk.Label(stats_grid, text="Coincidences:", background='#E8EAF6',
                font=('Arial', 9, 'bold')).grid(row=3, column=0, sticky='e', padx=3, pady=2)
        self.coincidences_label = tk.Label(stats_grid, text="---", background='#E8EAF6',
                                           font=('Courier New', 10, 'bold'), 
                                           foreground='#1976D2', width=12, anchor='w')
        self.coincidences_label.grid(row=3, column=1, sticky='w', padx=3, pady=2)
        
        # Coincidence rate
        tk.Label(stats_grid, text="Rate:", background='#E8EAF6',
                font=('Arial', 9)).grid(row=4, column=0, sticky='e', padx=3, pady=2)
        self.rate_label = tk.Label(stats_grid, text="---", background='#E8EAF6',
                                   font=('Courier New', 9), width=12, anchor='w')
        self.rate_label.grid(row=4, column=1, sticky='w', padx=3, pady=2)
        
        # Per-channel breakdown
        tk.Label(stats_grid, text="", background='#E8EAF6').grid(row=5, column=0, pady=5)
        tk.Label(stats_grid, text="Per Channel:", background='#E8EAF6',
                font=('Arial', 9, 'bold')).grid(row=6, column=0, columnspan=2, pady=2)
        
        self.channel_labels = []
        for i in range(4):
            lbl = tk.Label(stats_grid, text=f"Ch{i+1}: ---", background='#E8EAF6',
                          font=('Courier New', 8), anchor='w')
            lbl.grid(row=7+i, column=0, columnspan=2, sticky='w', padx=3, pady=1)
            self.channel_labels.append(lbl)
        
        # Right: Plots
        plot_frame = tk.Frame(results_frame, background=self.bg_color)
        plot_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Create figure with 2 subplots
        self.fig, (self.ax1, self.ax2) = plt.subplots(1, 2, figsize=(10, 4))
        self.fig.patch.set_facecolor(self.bg_color)
        
        self.ax1.set_title('Coincidence Time Series', fontsize=10, fontweight='bold')
        self.ax1.set_xlabel('Time (s)')
        self.ax1.set_ylabel('Coincidences')
        self.ax1.grid(True, alpha=0.3)
        
        self.ax2.set_title('Coincidence Histogram', fontsize=10, fontweight='bold')
        self.ax2.set_xlabel('Time Difference (ps)')
        self.ax2.set_ylabel('Counts')
        self.ax2.grid(True, alpha=0.3)
        
        self.fig.tight_layout()
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.canvas.draw()
    
    def _refresh_offset(self):
        """Refresh time offset from app config."""
        if self.app_ref and hasattr(self.app_ref, 'time_offset_ps'):
            offset = self.app_ref.time_offset_ps
            if offset is not None:
                self.offset_label.config(text=f"{offset:,} ps", foreground='#1976D2')
            else:
                self.offset_label.config(text="Not set", foreground='#F44336')
        else:
            self.offset_label.config(text="N/A", foreground='#999')
    
    def _browse_file(self, ch_idx, side):
        """Browse for a timestamp file."""
        filepath = filedialog.askopenfilename(
            title=f"Select {'Local' if side == 'local' else 'Remote'} Ch{ch_idx+1} File",
            filetypes=[("Binary files", "*.bin"), ("All files", "*.*")]
        )
        if filepath:
            self._set_file(ch_idx, side, Path(filepath))
    
    def _set_file(self, ch_idx, side, filepath: Path):
        """Set a file for a channel."""
        pair = self.channel_pairs[ch_idx]
        pair[f'{side}_file'] = filepath
        
        label = pair[f'{side}_label']
        if label:
            label.config(text=filepath.name[:35], foreground='#333')
        
        logger.info(f"Ch{ch_idx+1} {side} file set: {filepath.name}")
    
    def _clear_all_files(self):
        """Clear all file selections."""
        for pair in self.channel_pairs:
            pair['local_file'] = None
            pair['remote_file'] = None
            if pair['local_label']:
                pair['local_label'].config(text="(not selected)", foreground='#999')
            if pair['remote_label']:
                pair['remote_label'].config(text="(not selected)", foreground='#999')
    
    def _auto_detect_files(self):
        """Auto-detect timestamp files in data directory."""
        # Try common data directories
        search_dirs = [
            Path.home() / "Documents" / "AgodSolt" / "data",
            Path("D:/MyStuff/School/szakgyak/data/10min"),
            Path("D:/MyStuff/School/szakgyak/data"),
            Path.cwd() / "data"
        ]
        
        data_dir = None
        for d in search_dirs:
            if d.exists():
                data_dir = d
                break
        
        if not data_dir:
            logger.warning("No data directory found for auto-detect")
            return
        
        # Find most recent timestamp files
        bme_files = sorted(data_dir.glob("*bme*.bin"), key=lambda f: f.stat().st_mtime, reverse=True)
        wigner_files = sorted(data_dir.glob("*wigner*.bin"), key=lambda f: f.stat().st_mtime, reverse=True)
        
        # Match by channel number
        for ch_idx in range(4):
            ch_num = ch_idx + 1
            
            # Find local (BME) file for this channel
            for f in bme_files:
                if f"C{ch_num}" in f.name or f"ch{ch_num}" in f.name.lower():
                    self._set_file(ch_idx, 'local', f)
                    break
            
            # Find remote (Wigner) file for this channel
            for f in wigner_files:
                if f"C{ch_num}" in f.name or f"ch{ch_num}" in f.name.lower():
                    self._set_file(ch_idx, 'remote', f)
                    break
        
        logger.info("Auto-detect completed")
    
    def _read_timestamp_file(self, filepath: Path) -> Tuple[np.ndarray, Dict]:
        """
        Read binary timestamp file.
        
        Returns:
            Tuple of (timestamps_ps array, info dict)
        """
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")
        
        file_size = filepath.stat().st_size
        num_pairs = file_size // 16  # Each pair is 2x uint64 = 16 bytes
        
        logger.info(f"Reading {filepath.name}: {num_pairs:,} timestamp pairs")
        
        # Read in chunks for memory efficiency
        timestamps = []
        chunk_size = 100_000 * 2  # pairs
        
        with open(filepath, 'rb') as f:
            while True:
                raw_bytes = f.read(chunk_size * 8)
                if not raw_bytes:
                    break
                
                raw_values = np.frombuffer(raw_bytes, dtype=np.uint64)
                
                if len(raw_values) % 2 != 0:
                    raw_values = raw_values[:-1]
                
                ps_values = raw_values[0::2]
                sec_values = raw_values[1::2]
                
                # Convert to absolute picoseconds
                total_ps = ps_values.astype(np.uint64) + (sec_values.astype(np.uint64) * np.uint64(int(1e12)))
                timestamps.append(total_ps)
        
        all_timestamps = np.concatenate(timestamps) if timestamps else np.array([], dtype=np.uint64)
        
        # Calculate info
        time_span_sec = 0
        if len(all_timestamps) > 1:
            time_span_sec = (all_timestamps[-1] - all_timestamps[0]) / 1e12
        
        info = {
            'num_timestamps': len(all_timestamps),
            'time_span_sec': time_span_sec,
            'first_timestamp': all_timestamps[0] if len(all_timestamps) > 0 else 0,
            'last_timestamp': all_timestamps[-1] if len(all_timestamps) > 0 else 0,
            'mean_rate_hz': len(all_timestamps) / time_span_sec if time_span_sec > 0 else 0
        }
        
        logger.info(f"Loaded {len(all_timestamps):,} timestamps, span={time_span_sec:.2f}s")
        
        return all_timestamps, info
    
    def _count_coincidences_with_histogram(self, local_ts: np.ndarray, remote_ts: np.ndarray,
                                           time_offset_ps: int, window_ps: int) -> Tuple[int, np.ndarray]:
        """
        Count coincidences and build time difference histogram.
        
        Uses vectorized binary search for efficient O(n log m) performance.
        
        Returns:
            Tuple of (coincidence_count, time_differences_array)
        """
        if len(local_ts) == 0 or len(remote_ts) == 0:
            return 0, np.array([])
        
        # Apply time offset - SUBTRACT to align remote with local
        # Positive offset means remote is AHEAD, so we subtract to bring it back
        remote_adjusted = remote_ts.astype(np.int64) - time_offset_ps
        
        logger.info(f"Counting coincidences: {len(local_ts):,} local × {len(remote_ts):,} remote, "
                   f"offset={time_offset_ps:,} ps, window=±{window_ps} ps")
        
        # Vectorized approach using binary search
        # For each local timestamp, find the range of remote timestamps within ±window_ps
        local_int = local_ts.astype(np.int64)
        
        # Find left and right boundaries for each local timestamp
        left_bounds = np.searchsorted(remote_adjusted, local_int - window_ps, side='left')
        right_bounds = np.searchsorted(remote_adjusted, local_int + window_ps, side='right')
        
        # Count matches for each local timestamp
        counts_per_local = right_bounds - left_bounds
        total_coincidences = int(np.sum(counts_per_local))
        
        logger.info(f"Found {total_coincidences:,} coincidences")
        
        # Build time differences histogram (sample if too many)
        time_diffs = []
        max_diffs_to_store = 1_000_000  # Limit memory usage
        
        if total_coincidences > 0:
            # Find local timestamps that have matches
            has_match = counts_per_local > 0
            matched_indices = np.where(has_match)[0]
            
            # Sample if needed
            if total_coincidences > max_diffs_to_store:
                # Randomly sample local indices
                sample_size = min(100_000, len(matched_indices))
                sample_indices = np.random.choice(matched_indices, size=sample_size, replace=False)
            else:
                sample_indices = matched_indices
            
            # Collect time differences for sampled local timestamps
            for idx in sample_indices:
                local_t = local_int[idx]
                left = left_bounds[idx]
                right = right_bounds[idx]
                
                if right > left:
                    diffs = remote_adjusted[left:right] - local_t
                    time_diffs.extend(diffs.tolist())
                    
                    if len(time_diffs) >= max_diffs_to_store:
                        break
        
        return total_coincidences, np.array(time_diffs, dtype=np.int64)
    
    def _start_analysis(self):
        """Start correlation analysis."""
        # Collect enabled channels with files
        local_files = []
        remote_files = []
        enabled_channels = []
        
        for ch_idx, pair in enumerate(self.channel_pairs):
            if pair['enabled'].get():
                if not pair['local_file'] or not pair['remote_file']:
                    messagebox.showwarning("Missing Files",
                                          f"Channel {ch_idx+1} is enabled but missing files.")
                    return
                local_files.append((ch_idx, pair['local_file']))
                remote_files.append((ch_idx, pair['remote_file']))
                enabled_channels.append(ch_idx)
        
        if not enabled_channels:
            messagebox.showwarning("No Channels", "Please enable at least one channel.")
            return
        
        # Get time offset
        time_offset_ps = 0
        if self.app_ref and hasattr(self.app_ref, 'time_offset_ps'):
            time_offset_ps = self.app_ref.time_offset_ps or 0
        
        if time_offset_ps == 0:
            result = messagebox.askyesno("No Time Offset",
                                        "Time offset is not set (0 ps).\n"
                                        "Results may be incorrect without proper time synchronization.\n\n"
                                        "Continue anyway?")
            if not result:
                return
        
        # Get parameters
        window_ps = self.coincidence_window_ps.get()
        time_bin_sec = self.time_bin_sec.get()
        
        # Update UI
        self.analyze_button.config(state=tk.DISABLED, text="⏳ Analyzing...")
        self.status_label.config(text="Loading files...", foreground='#FF9800')
        self.root.update()
        
        # Run analysis in background thread
        def analysis_thread():
            try:
                results = self._run_analysis(local_files, remote_files, time_offset_ps,
                                            window_ps, time_bin_sec)
                self.root.after(0, lambda: self._on_analysis_complete(results))
            except Exception as e:
                logger.error(f"Analysis failed: {e}", exc_info=True)
                self.root.after(0, lambda: self._on_analysis_error(str(e)))
        
        thread = threading.Thread(target=analysis_thread, daemon=True)
        thread.start()
    
    def _run_analysis(self, local_files: List, remote_files: List,
                      time_offset_ps: int, window_ps: int, time_bin_sec: float) -> Dict:
        """Run the correlation analysis (in background thread)."""
        results = {
            'channels': {},
            'total_coincidences': 0,
            'total_local_events': 0,
            'total_remote_events': 0,
            'duration_sec': 0,
            'all_time_diffs': [],
            'time_series': {},
        }
        
        min_first_ts = None
        max_last_ts = None
        
        for (ch_idx, local_file), (_, remote_file) in zip(local_files, remote_files):
            logger.info(f"Analyzing channel {ch_idx+1}...")
            
            # Read files
            local_ts, local_info = self._read_timestamp_file(local_file)
            remote_ts, remote_info = self._read_timestamp_file(remote_file)
            
            # Track overall time span
            for info in [local_info, remote_info]:
                if info['first_timestamp'] > 0:
                    if min_first_ts is None or info['first_timestamp'] < min_first_ts:
                        min_first_ts = info['first_timestamp']
                    if max_last_ts is None or info['last_timestamp'] > max_last_ts:
                        max_last_ts = info['last_timestamp']
            
            # Count coincidences with histogram
            count, time_diffs = self._count_coincidences_with_histogram(
                local_ts, remote_ts, time_offset_ps, window_ps
            )
            
            # Build time series
            if min_first_ts is not None and len(local_ts) > 0:
                time_series = self._build_time_series(local_ts, remote_ts, time_offset_ps,
                                                      window_ps, time_bin_sec, min_first_ts)
            else:
                time_series = (np.array([]), np.array([]))
            
            results['channels'][ch_idx] = {
                'coincidences': count,
                'local_events': len(local_ts),
                'remote_events': len(remote_ts),
                'time_diffs': time_diffs,
                'time_series': time_series,
            }
            
            results['total_coincidences'] += count
            results['total_local_events'] += len(local_ts)
            results['total_remote_events'] += len(remote_ts)
            results['all_time_diffs'].extend(time_diffs.tolist())
        
        # Calculate duration
        if min_first_ts is not None and max_last_ts is not None:
            results['duration_sec'] = (max_last_ts - min_first_ts) / 1e12
        
        results['all_time_diffs'] = np.array(results['all_time_diffs'])
        
        return results
    
    def _build_time_series(self, local_ts: np.ndarray, remote_ts: np.ndarray,
                           time_offset_ps: int, window_ps: int, 
                           time_bin_sec: float, ref_time: int) -> Tuple[np.ndarray, np.ndarray]:
        """Build coincidence time series using vectorized operations."""
        if len(local_ts) == 0 or len(remote_ts) == 0:
            return np.array([]), np.array([])
        
        # Apply offset - SUBTRACT to align remote with local
        remote_adjusted = remote_ts.astype(np.int64) - time_offset_ps
        
        # Convert to seconds relative to reference
        local_sec = (local_ts.astype(np.int64) - ref_time) / 1e12
        
        # Determine time range
        max_time = np.max(local_sec)
        num_bins = int(np.ceil(max_time / time_bin_sec))
        
        if num_bins <= 0 or num_bins > 100000:
            return np.array([]), np.array([])
        
        bin_edges = np.arange(0, (num_bins + 1) * time_bin_sec, time_bin_sec)
        bin_centers = bin_edges[:-1] + time_bin_sec / 2
        coincidence_counts = np.zeros(num_bins)
        
        local_int = local_ts.astype(np.int64)
        
        # Vectorized: find coincidences for all local timestamps at once
        left_bounds = np.searchsorted(remote_adjusted, local_int - window_ps, side='left')
        right_bounds = np.searchsorted(remote_adjusted, local_int + window_ps, side='right')
        counts_per_local = right_bounds - left_bounds
        
        # Bin the coincidence counts by time
        local_bins = np.digitize(local_sec, bin_edges) - 1
        
        # Sum coincidences in each bin
        for i in range(len(local_int)):
            bin_idx = local_bins[i]
            if 0 <= bin_idx < num_bins:
                coincidence_counts[bin_idx] += counts_per_local[i]
        
        return bin_centers[:len(coincidence_counts)], coincidence_counts
    
    def _on_analysis_complete(self, results: Dict):
        """Handle analysis completion."""
        self.last_results = results
        
        # Update UI
        self.analyze_button.config(state=tk.NORMAL, text="🔬 Analyze Correlations")
        self.export_button.config(state=tk.NORMAL)
        
        # Update statistics
        duration = results['duration_sec']
        self.duration_label.config(text=f"{duration:.2f} s")
        self.local_events_label.config(text=format_number(results['total_local_events']))
        self.remote_events_label.config(text=format_number(results['total_remote_events']))
        self.coincidences_label.config(text=format_number(results['total_coincidences']))
        
        rate = results['total_coincidences'] / duration if duration > 0 else 0
        self.rate_label.config(text=f"{rate:.1f} Hz")
        
        # Calculate expected accidentals and SNR
        if duration > 0:
            local_rate = results['total_local_events'] / duration
            remote_rate = results['total_remote_events'] / duration
            window_ps = self.coincidence_window_ps.get()
            window_sec = 2 * window_ps * 1e-12  # Full window width in seconds
            expected_accidentals = local_rate * remote_rate * window_sec * duration
            
            # SNR = (measured - accidentals) / sqrt(accidentals)
            if expected_accidentals > 0:
                snr = (results['total_coincidences'] - expected_accidentals) / np.sqrt(expected_accidentals)
                results['expected_accidentals'] = expected_accidentals
                results['snr'] = snr
                logger.info(f"Expected accidentals: {expected_accidentals:.0f}, SNR: {snr:.1f}σ")
        
        # Update per-channel stats
        for i, lbl in enumerate(self.channel_labels):
            if i in results['channels']:
                ch_data = results['channels'][i]
                lbl.config(text=f"Ch{i+1}: {ch_data['coincidences']:,}")
            else:
                lbl.config(text=f"Ch{i+1}: ---")
        
        # Status with SNR info
        status_text = "✓ Analysis complete!"
        if 'snr' in results:
            snr = results['snr']
            if snr > 5:
                status_text += f"\n🎯 SNR: {snr:.1f}σ (GOOD)"
                fg_color = '#2E7D32'
            elif snr > 2:
                status_text += f"\n⚠️ SNR: {snr:.1f}σ (LOW)"
                fg_color = '#FF9800'
            else:
                status_text += f"\n❌ SNR: {snr:.1f}σ (NOISE)"
                fg_color = '#D32F2F'
        else:
            fg_color = '#2E7D32'
        
        self.status_label.config(text=status_text, foreground=fg_color)
        
        # Update plots
        self._update_plots(results)
    
    def _on_analysis_error(self, error_msg: str):
        """Handle analysis error."""
        self.analyze_button.config(state=tk.NORMAL, text="🔬 Analyze Correlations")
        self.status_label.config(text=f"❌ Error: {error_msg}", foreground='#D32F2F')
        messagebox.showerror("Analysis Error", f"Analysis failed:\n\n{error_msg}")
    
    def _update_plots(self, results: Dict):
        """Update the plots with results."""
        self.ax1.clear()
        self.ax2.clear()
        
        # Plot 1: Time series
        colors = ['#1976D2', '#388E3C', '#F57C00', '#7B1FA2']
        
        for ch_idx, ch_data in results['channels'].items():
            times, counts = ch_data['time_series']
            if len(times) > 0:
                self.ax1.plot(times, counts, color=colors[ch_idx % 4], 
                             linewidth=1.5, alpha=0.8, label=f'Ch{ch_idx+1}')
        
        # Add expected accidentals level to time series
        if 'expected_accidentals' in results and results['duration_sec'] > 0:
            time_bin = self.time_bin_sec.get()
            acc_per_bin = results['expected_accidentals'] * time_bin / results['duration_sec']
            self.ax1.axhline(acc_per_bin, color='red', linestyle='--', linewidth=1, 
                            alpha=0.7, label=f'Accidentals: {acc_per_bin:.1f}/bin')
        
        self.ax1.set_title('Coincidence Time Series', fontsize=10, fontweight='bold')
        self.ax1.set_xlabel('Time (s)')
        self.ax1.set_ylabel('Coincidences per bin')
        self.ax1.legend(fontsize=8)
        self.ax1.grid(True, alpha=0.3)
        
        # Plot 2: Time difference histogram
        all_diffs = results['all_time_diffs']
        if len(all_diffs) > 0:
            window_ps = self.coincidence_window_ps.get()
            bins = np.linspace(-window_ps, window_ps, 51)
            counts, bin_edges, patches = self.ax2.hist(all_diffs, bins=bins, color='#1976D2', 
                                                        edgecolor='white', alpha=0.7)
            self.ax2.axvline(0, color='red', linestyle='--', linewidth=1.5, alpha=0.7,
                            label='Perfect sync')
            
            # Find and annotate peak
            if len(counts) > 0:
                peak_idx = np.argmax(counts)
                peak_pos = (bin_edges[peak_idx] + bin_edges[peak_idx + 1]) / 2
                peak_val = counts[peak_idx]
                
                # Check if peak is significant
                mean_count = np.mean(counts)
                if peak_val > mean_count * 1.5:  # 50% above mean
                    self.ax2.annotate(f'Peak: {peak_pos:.0f} ps',
                                     xy=(peak_pos, peak_val),
                                     xytext=(peak_pos, peak_val * 1.1),
                                     ha='center', fontsize=8,
                                     arrowprops=dict(arrowstyle='->', color='green'),
                                     color='green', fontweight='bold')
        
        self.ax2.set_title('Time Difference Histogram', fontsize=10, fontweight='bold')
        self.ax2.set_xlabel('Time Difference (ps)')
        self.ax2.set_ylabel('Counts')
        self.ax2.legend(fontsize=8)
        self.ax2.grid(True, alpha=0.3)
        
        self.fig.tight_layout()
        self.canvas.draw()
    
    def _export_results(self):
        """Export results to file."""
        if not self.last_results:
            messagebox.showwarning("No Results", "Run analysis first.")
            return
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if not filepath:
            return
        
        try:
            with open(filepath, 'w') as f:
                f.write("Offline Correlation Analysis Results\n")
                f.write(f"Duration (s),{self.last_results['duration_sec']:.2f}\n")
                f.write(f"Total Local Events,{self.last_results['total_local_events']}\n")
                f.write(f"Total Remote Events,{self.last_results['total_remote_events']}\n")
                f.write(f"Total Coincidences,{self.last_results['total_coincidences']}\n")
                f.write(f"Coincidence Window (ps),{self.coincidence_window_ps.get()}\n")
                f.write(f"Time Offset (ps),{self.app_ref.time_offset_ps or 0}\n")
                f.write("\n")
                f.write("Per Channel:\n")
                f.write("Channel,Coincidences,Local Events,Remote Events\n")
                for ch_idx, ch_data in self.last_results['channels'].items():
                    f.write(f"{ch_idx+1},{ch_data['coincidences']},"
                           f"{ch_data['local_events']},{ch_data['remote_events']}\n")
            
            messagebox.showinfo("Export Complete", f"Results saved to:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export:\n{e}")
