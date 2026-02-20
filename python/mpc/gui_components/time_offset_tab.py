"""
Time Offset Calculator GUI Tab

Provides user interface for calculating time offset between sites
using FFT cross-correlation on saved timestamp files.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import logging
import threading
from pathlib import Path
from datetime import datetime

from time_offset_calculator import TimeOffsetCalculator
from gui_components.helpers import format_number

logger = logging.getLogger(__name__)


class TimeOffsetTab:
    """GUI tab for time offset calculation using FFT cross-correlation."""
    
    def __init__(self, parent_frame, app_ref, bg_color='#282828', fg_color='#D4D4D4', 
                 action_color='#007ACC'):
        """
        Initialize the time offset calculator tab.
        
        Args:
            parent_frame: Parent tkinter frame (the tab)
            app_ref: Reference to main App instance
            bg_color: Background color
            fg_color: Foreground color
            action_color: Button color
        """
        self.parent = parent_frame
        self.app_ref = app_ref
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.action_color = action_color
        
        # Calculator instance
        self.calculator = TimeOffsetCalculator()
        
        # Channel pair selections (4 channels)
        self.channel_pairs = []
        for i in range(4):
            self.channel_pairs.append({
                'enabled': tk.BooleanVar(value=(i == 0)),  # Ch1 enabled by default
                'local_file': None,
                'remote_file': None,
                'local_label': None,  # Will be set in UI
                'remote_label': None
            })
        
        # Calculation results
        self.last_result = None
        
        # Build UI
        self._build_ui()
        
        # Auto-detect recent files on startup
        self.root.after(500, self._auto_detect_files)
    
    @property
    def root(self):
        """Get root window from parent."""
        return self.parent.winfo_toplevel()
    
    def _build_ui(self):
        """Build the complete UI for the time offset tab."""
        # Main container with padding - use light background
        container = tk.Frame(self.parent, background='#F5F5F5')
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Header
        header = tk.Label(container, 
                         text="⏱️ Time Offset Calculator (FFT Cross-Correlation)",
                         font=('Arial', 12, 'bold'),
                         background='#F5F5F5', foreground='#1E1E1E')
        header.pack(pady=(0, 8))
        
        # File selection section
        self._build_file_selection(container)
        
        # Parameters section
        self._build_parameters(container)
        
        # Action buttons
        self._build_action_buttons(container)
        
        # Results section
        self._build_results(container)
        
        # Plot section (smaller)
        self._build_plot(container)
    
    def _build_file_selection(self, parent):
        """Build file selection section for multiple channel pairs."""
        file_frame = tk.LabelFrame(parent, text="📁 Channel Pair Selection", 
                                   font=('Arial', 10, 'bold'),
                                   background='#E8F5E9', bd=2, relief=tk.RIDGE,
                                   padx=10, pady=8)
        file_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Header row
        header = tk.Frame(file_frame, background='#E8F5E9')
        header.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(header, text="", width=3, background='#E8F5E9').pack(side=tk.LEFT)
        tk.Label(header, text="Channel", font=('Arial', 8, 'bold'), width=8,
                background='#E8F5E9').pack(side=tk.LEFT)
        tk.Label(header, text="LOCAL File", font=('Arial', 8, 'bold'), width=35,
                background='#E8F5E9', anchor='w').pack(side=tk.LEFT, padx=5)
        tk.Label(header, text="REMOTE File", font=('Arial', 8, 'bold'), width=35,
                background='#E8F5E9', anchor='w').pack(side=tk.LEFT, padx=5)
        
        # Create 4 channel pair rows
        for ch_idx in range(4):
            self._build_channel_row(file_frame, ch_idx)
        
        # Control buttons
        btn_row = tk.Frame(file_frame, background='#E8F5E9')
        btn_row.pack(fill=tk.X, pady=(8, 0))
        
        tk.Button(btn_row, text="🔍 Auto-Detect Files",
                 command=self._auto_detect_files,
                 background='#2196F3', foreground='white',
                 font=('Arial', 8, 'bold'), width=16).pack(side=tk.LEFT, padx=2)
        
        tk.Button(btn_row, text="🗑️ Clear All",
                 command=self._clear_all_files,
                 background='#FF5722', foreground='white',
                 font=('Arial', 8, 'bold'), width=12).pack(side=tk.LEFT, padx=2)
        
        # Status label
        self.file_status_label = tk.Label(file_frame, text="Select at least one channel pair",
                                          font=('Arial', 8), foreground='#666',
                                          background='#E8F5E9')
        self.file_status_label.pack(pady=(5, 0))
    
    def _build_channel_row(self, parent, ch_idx):
        """Build a single channel pair row."""
        ch_num = ch_idx + 1
        pair = self.channel_pairs[ch_idx]
        
        row = tk.Frame(parent, background='#E8F5E9')
        row.pack(fill=tk.X, pady=2)
        
        # Checkbox
        cb = tk.Checkbutton(row, variable=pair['enabled'], background='#E8F5E9',
                           command=self._update_file_status)
        cb.pack(side=tk.LEFT, padx=(0, 5))
        
        # Channel label
        tk.Label(row, text=f"Ch {ch_num}", font=('Arial', 9, 'bold'),
                background='#E8F5E9', width=6, anchor='w').pack(side=tk.LEFT)
        
        # Local file display
        local_label = tk.Label(row, text="(not selected)",
                              font=('Courier New', 7), width=40,
                              background='white', foreground='#999',
                              relief=tk.SUNKEN, anchor='w', padx=3)
        local_label.pack(side=tk.LEFT, padx=2)
        pair['local_label'] = local_label
        
        # Local browse button
        tk.Button(row, text="📂", width=2,
                 command=lambda: self._browse_channel_file(ch_idx, 'local'),
                 background='#4CAF50', foreground='white',
                 font=('Arial', 8, 'bold')).pack(side=tk.LEFT, padx=1)
        
        # Remote file display
        remote_label = tk.Label(row, text="(not selected)",
                               font=('Courier New', 7), width=40,
                               background='white', foreground='#999',
                               relief=tk.SUNKEN, anchor='w', padx=3)
        remote_label.pack(side=tk.LEFT, padx=2)
        pair['remote_label'] = remote_label
        
        # Remote browse button
        tk.Button(row, text="📂", width=2,
                 command=lambda: self._browse_channel_file(ch_idx, 'remote'),
                 background='#2196F3', foreground='white',
                 font=('Arial', 8, 'bold')).pack(side=tk.LEFT, padx=1)
    
    def _build_parameters(self, parent):
        """Build correlation parameters section."""
        param_frame = tk.LabelFrame(parent, text="⚙️ Parameters",
                                   font=('Arial', 10, 'bold'),
                                   background='#FFF3E0', bd=2, relief=tk.RIDGE,
                                   padx=10, pady=5)
        param_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Create grid for parameters
        params_grid = tk.Frame(param_frame, background='#FFF3E0')
        params_grid.pack()
        
        # Bin width (tau)
        tk.Label(params_grid, text="Bin Width (τ):", background='#FFF3E0',
                font=('Arial', 9)).grid(row=0, column=0, sticky='e', padx=5, pady=3)
        self.tau_var = tk.StringVar(value="2048")
        tk.Entry(params_grid, textvariable=self.tau_var, width=12,
                font=('Courier New', 9)).grid(row=0, column=1, padx=5, pady=3)
        tk.Label(params_grid, text="ps (2.048 ns)", background='#FFF3E0',
                font=('Arial', 8), foreground='#666').grid(row=0, column=2, sticky='w', padx=5)
        
        # Number of bins (as power of 2)
        tk.Label(params_grid, text="FFT Bins (2^N):", background='#FFF3E0',
                font=('Arial', 9)).grid(row=1, column=0, sticky='e', padx=5, pady=3)
        self.n_power_var = tk.StringVar(value="23")
        tk.Entry(params_grid, textvariable=self.n_power_var, width=12,
                font=('Courier New', 9)).grid(row=1, column=1, padx=5, pady=3)
        tk.Label(params_grid, text="(23 = 8.4M bins)", background='#FFF3E0',
                font=('Arial', 8), foreground='#666').grid(row=1, column=2, sticky='w', padx=5)
        
        # Initial shift
        tk.Label(params_grid, text="Initial Shift:", background='#FFF3E0',
                font=('Arial', 9)).grid(row=2, column=0, sticky='e', padx=5, pady=3)
        self.tshift_var = tk.StringVar(value="0")
        tk.Entry(params_grid, textvariable=self.tshift_var, width=12,
                font=('Courier New', 9)).grid(row=2, column=1, padx=5, pady=3)
        tk.Label(params_grid, text="ps (0 = auto)", background='#FFF3E0',
                font=('Arial', 8), foreground='#666').grid(row=2, column=2, sticky='w', padx=5)
    
    def _build_action_buttons(self, parent):
        """Build action buttons section."""
        btn_frame = tk.Frame(parent, background=self.bg_color)
        btn_frame.pack(pady=5)
        
        self.calc_button = tk.Button(btn_frame, text="🔬 Calculate Offset",
                                     command=self._start_calculation,
                                     background='#FF9800', foreground='white',
                                     font=('Arial', 10, 'bold'), width=18, height=1)
        self.calc_button.pack(side=tk.LEFT, padx=5)
        
        self.plot_button = tk.Button(btn_frame, text="📊 Show Plot",
                                     command=self._show_correlation_plot,
                                     background='#9C27B0', foreground='white',
                                     font=('Arial', 10, 'bold'), width=15, height=1,
                                     state=tk.DISABLED)
        self.plot_button.pack(side=tk.LEFT, padx=5)
    
    def _build_results(self, parent):
        """Build results display section."""
        results_frame = tk.LabelFrame(parent, text="📋 Results",
                                     font=('Arial', 10, 'bold'),
                                     background='#E8EAF6', bd=2, relief=tk.RIDGE,
                                     padx=10, pady=5)
        results_frame.pack(fill=tk.BOTH, expand=False, pady=(0, 5))
        
        # Status label
        self.status_label = tk.Label(results_frame, text="Ready - Select files and click Calculate",
                                     font=('Arial', 9), background='#E8EAF6',
                                     foreground='#666')
        self.status_label.pack(pady=(0, 5))
        
        # Results grid
        results_grid = tk.Frame(results_frame, background='#E8EAF6')
        results_grid.pack()
        
        # Peak position
        tk.Label(results_grid, text="Peak Position:", background='#E8EAF6',
                font=('Arial', 9, 'bold')).grid(row=0, column=0, sticky='e', padx=5, pady=3)
        self.peak_pos_label = tk.Label(results_grid, text="---", background='#E8EAF6',
                                       font=('Courier New', 10), foreground='#333', width=20, anchor='w')
        self.peak_pos_label.grid(row=0, column=1, sticky='w', padx=5, pady=3)
        
        # Time offset (ps)
        tk.Label(results_grid, text="Time Offset:", background='#E8EAF6',
                font=('Arial', 9, 'bold')).grid(row=1, column=0, sticky='e', padx=5, pady=3)
        self.offset_ps_label = tk.Label(results_grid, text="---", background='#E8EAF6',
                                        font=('Courier New', 10, 'bold'), foreground='#1976D2', width=20, anchor='w')
        self.offset_ps_label.grid(row=1, column=1, sticky='w', padx=5, pady=3)
        
        # Time offset (ms)
        tk.Label(results_grid, text="", background='#E8EAF6').grid(row=2, column=0)
        self.offset_ms_label = tk.Label(results_grid, text="---", background='#E8EAF6',
                                        font=('Courier New', 9), foreground='#666', width=20, anchor='w')
        self.offset_ms_label.grid(row=2, column=1, sticky='w', padx=5, pady=3)
        
        # Correlation strength
        tk.Label(results_grid, text="Peak Strength:", background='#E8EAF6',
                font=('Arial', 9, 'bold')).grid(row=3, column=0, sticky='e', padx=5, pady=3)
        self.strength_label = tk.Label(results_grid, text="---", background='#E8EAF6',
                                       font=('Courier New', 10), foreground='#333', width=20, anchor='w')
        self.strength_label.grid(row=3, column=1, sticky='w', padx=5, pady=3)
        
        # Confidence
        tk.Label(results_grid, text="Confidence:", background='#E8EAF6',
                font=('Arial', 9, 'bold')).grid(row=4, column=0, sticky='e', padx=5, pady=3)
        self.confidence_label = tk.Label(results_grid, text="---", background='#E8EAF6',
                                         font=('Arial', 10, 'bold'), foreground='#333', width=20, anchor='w')
        self.confidence_label.grid(row=4, column=1, sticky='w', padx=5, pady=3)
        
        # Action buttons row
        action_row = tk.Frame(results_frame, background='#E8EAF6')
        action_row.pack(pady=(5, 0))
        
        # Offset slot selector for saving
        tk.Label(action_row, text="Save to:", font=('Arial', 9)).pack(side=tk.LEFT, padx=(0, 2))
        self.save_offset_slot_var = tk.StringVar(value="1")
        ttk.Combobox(action_row, values=["1", "2", "3", "4"], width=3, state="readonly",
                     textvariable=self.save_offset_slot_var).pack(side=tk.LEFT, padx=(0, 5))
        
        self.save_button = tk.Button(action_row, text="💾 Save Config",
                                     command=self._save_to_config,
                                     background='#4CAF50', foreground='white',
                                     font=('Arial', 9, 'bold'), width=15,
                                     state=tk.DISABLED)
        self.save_button.pack(side=tk.LEFT, padx=5)
        
        self.copy_button = tk.Button(action_row, text="📋 Copy",
                                     command=self._copy_to_clipboard,
                                     background='#2196F3', foreground='white',
                                     font=('Arial', 9, 'bold'), width=12,
                                     state=tk.DISABLED)
        self.copy_button.pack(side=tk.LEFT, padx=5)
    
    def _build_plot(self, parent):
        """Build matplotlib plot area."""
        plot_frame = tk.LabelFrame(parent, text="📈 Preview",
                                  font=('Arial', 10, 'bold'),
                                  background='#F5F5F5', bd=2, relief=tk.RIDGE,
                                  padx=5, pady=5)
        plot_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create small preview plot
        self.fig, self.ax = plt.subplots(figsize=(10, 2), facecolor='#F5F5F5')
        self.ax.set_facecolor('#FFFFFF')
        self.ax.set_title('Correlation preview (click "Show Plot" for full view)', fontsize=9)
        self.ax.set_xlabel('Lag Index', fontsize=8)
        self.ax.set_ylabel('σ', fontsize=8)
        self.ax.tick_params(labelsize=7)
        self.ax.grid(True, alpha=0.3)
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().configure(background='#F5F5F5')
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.canvas.draw()
    
    def _update_file_status(self):
        """Update file selection status label."""
        enabled_count = sum(1 for pair in self.channel_pairs if pair['enabled'].get())
        pairs_with_files = sum(1 for pair in self.channel_pairs 
                               if pair['enabled'].get() and pair['local_file'] and pair['remote_file'])
        
        if pairs_with_files == 0:
            self.file_status_label.config(text="⚠️ Select at least one channel pair with both files",
                                         foreground='#FF5722')
        elif pairs_with_files < enabled_count:
            self.file_status_label.config(text=f"⚠️ {pairs_with_files}/{enabled_count} enabled channels have both files",
                                         foreground='#FF9800')
        else:
            self.file_status_label.config(text=f"✓ {pairs_with_files} channel pair(s) ready",
                                         foreground='#4CAF50')
    
    def _auto_detect_files(self):
        """Auto-detect most recent timestamp files for all channels."""
        try:
            data_dir = Path.home() / "Documents" / "AgodSolt" / "data"
            if not data_dir.exists():
                logger.warning(f"Data directory not found: {data_dir}")
                return
            
            # Try to find files for each channel
            for ch_idx in range(4):
                ch_num = ch_idx + 1
                
                # Look for local files (ch1_*, ch2_*, etc.)
                local_pattern = f"*ch{ch_num}*.bin"
                local_files = sorted(data_dir.glob(local_pattern),
                                   key=lambda p: p.stat().st_mtime, reverse=True)
                
                # Exclude 'remote' or 'wigner' in filename for local
                local_files = [f for f in local_files if 'remote' not in f.name.lower() 
                              and 'wigner' not in f.name.lower()]
                
                if local_files:
                    self._set_channel_file(ch_idx, 'local', local_files[0])
                    logger.info(f"Auto-detected Ch{ch_num} local: {local_files[0].name}")
                
                # Look for remote files
                remote_dir = data_dir / "remote"
                if remote_dir.exists():
                    remote_files = sorted(remote_dir.glob(local_pattern),
                                        key=lambda p: p.stat().st_mtime, reverse=True)
                    if remote_files:
                        self._set_channel_file(ch_idx, 'remote', remote_files[0])
                        logger.info(f"Auto-detected Ch{ch_num} remote: {remote_files[0].name}")
                else:
                    # Try files with 'wigner' or 'remote' in name
                    remote_files = sorted(data_dir.glob(local_pattern),
                                        key=lambda p: p.stat().st_mtime, reverse=True)
                    remote_files = [f for f in remote_files if 'wigner' in f.name.lower() 
                                  or 'remote' in f.name.lower()]
                    if remote_files:
                        self._set_channel_file(ch_idx, 'remote', remote_files[0])
                        logger.info(f"Auto-detected Ch{ch_num} remote: {remote_files[0].name}")
            
            self._update_file_status()
            
        except Exception as e:
            logger.error(f"Auto-detect files failed: {e}", exc_info=True)
    
    def _browse_channel_file(self, ch_idx, side):
        """Open file browser for specific channel and side (local/remote)."""
        ch_num = ch_idx + 1
        initial_dir = Path.home() / "Documents" / "AgodSolt" / "data"
        
        if side == 'remote':
            remote_dir = initial_dir / "remote"
            if remote_dir.exists():
                initial_dir = remote_dir
        
        title = f"Select Ch{ch_num} {side.upper()} Timestamp File"
        filepath = filedialog.askopenfilename(
            title=title,
            initialdir=str(initial_dir) if initial_dir.exists() else None,
            filetypes=[("Binary files", "*.bin"), ("All files", "*.*")]
        )
        if filepath:
            self._set_channel_file(ch_idx, side, Path(filepath))
    
    def _set_channel_file(self, ch_idx, side, filepath: Path):
        """Set file for a specific channel and side."""
        pair = self.channel_pairs[ch_idx]
        
        if side == 'local':
            pair['local_file'] = filepath
            pair['local_label'].config(text=filepath.name, foreground='#2E7D32')
        else:
            pair['remote_file'] = filepath
            pair['remote_label'].config(text=filepath.name, foreground='#1565C0')
        
        self._update_file_status()
        logger.info(f"Ch{ch_idx+1} {side} file set: {filepath.name}")
    
    def _clear_all_files(self):
        """Clear all file selections."""
        for pair in self.channel_pairs:
            pair['local_file'] = None
            pair['remote_file'] = None
            pair['local_label'].config(text="(not selected)", foreground='#999')
            pair['remote_label'].config(text="(not selected)", foreground='#999')
        
        self._update_file_status()
        logger.info("All files cleared")
    
    def _start_calculation(self):
        """Start correlation calculation in background thread."""
        # Collect enabled channel pairs with both files selected
        local_files = []
        remote_files = []
        
        for ch_idx, pair in enumerate(self.channel_pairs):
            if pair['enabled'].get():
                if not pair['local_file'] or not pair['remote_file']:
                    messagebox.showwarning("Incomplete Selection",
                                         f"Channel {ch_idx+1} is enabled but missing files.\n"
                                         f"Please select both local and remote files, or disable the channel.")
                    return
                
                if not pair['local_file'].exists():
                    messagebox.showerror("File Not Found",
                                       f"Ch{ch_idx+1} local file not found:\n{pair['local_file']}")
                    return
                
                if not pair['remote_file'].exists():
                    messagebox.showerror("File Not Found",
                                       f"Ch{ch_idx+1} remote file not found:\n{pair['remote_file']}")
                    return
                
                local_files.append(pair['local_file'])
                remote_files.append(pair['remote_file'])
        
        if not local_files or not remote_files:
            messagebox.showwarning("No Channels Selected",
                                  "Please enable and select files for at least one channel pair.")
            return
        
        # Parse parameters
        try:
            tau = int(self.tau_var.get())
            n_power = int(self.n_power_var.get())
            Tshift = int(self.tshift_var.get())
            
            # Validate power of 2
            if n_power < 10 or n_power > 30:
                messagebox.showerror("Invalid Parameter", "FFT bins power must be between 10 and 30")
                return
            
            N = 2 ** n_power  # Calculate actual N from power
        except ValueError:
            messagebox.showerror("Invalid Parameters", "Please enter valid integer parameters.")
            return
        
        # Update calculator parameters
        self.calculator.tau = tau
        self.calculator.N = N
        self.calculator.Tshift = Tshift
        
        # Disable buttons during calculation
        self.calc_button.config(state=tk.DISABLED, text="⏳ Calculating...")
        self.plot_button.config(state=tk.DISABLED)
        self.save_button.config(state=tk.DISABLED)
        self.copy_button.config(state=tk.DISABLED)
        
        num_channels = len(local_files)
        self.status_label.config(text=f"Calculating with {num_channels} channel pair(s)... Please wait",
                                foreground='#FF9800')
        
        # Run in background thread
        def calculation_thread():
            result = self.calculator.run_correlation(local_files, remote_files)
            self.root.after(0, lambda: self._on_calculation_complete(result))
        
        thread = threading.Thread(target=calculation_thread, daemon=True)
        thread.start()
    
    def _on_calculation_complete(self, result: dict):
        """Handle calculation completion."""
        self.last_result = result
        
        # Re-enable button
        self.calc_button.config(state=tk.NORMAL, text="🔬 Calculate Offset")
        
        if result['success']:
            # Update results display
            self.peak_pos_label.config(text=f"{result['peak_index']:,}")
            self.offset_ps_label.config(text=f"{result['offset_ps']:,} ps")
            self.offset_ms_label.config(text=f"(= {result['offset_ms']:.3f} ms)")
            self.strength_label.config(text=f"{result['peak_value']:.2f} σ")
            
            # Update confidence with color coding
            confidence = result['confidence']
            if confidence == "High":
                color = '#2E7D32'  # Green
                icon = "✓"
            elif confidence == "Medium":
                color = '#F57C00'  # Orange
                icon = "⚠"
            else:
                color = '#D32F2F'  # Red
                icon = "✗"
            
            self.confidence_label.config(text=f"{confidence} {icon}", foreground=color)
            
            # Update status
            if result['reliable']:
                self.status_label.config(text="✓ Calculation complete - Results reliable",
                                        foreground='#2E7D32')
                self.save_button.config(state=tk.NORMAL)
            else:
                self.status_label.config(text="⚠ Calculation complete - Low confidence, verify manually",
                                        foreground='#F57C00')
                self.save_button.config(state=tk.DISABLED)
            
            self.copy_button.config(state=tk.NORMAL)
            self.plot_button.config(state=tk.NORMAL)
            
            # Update preview plot
            self._update_preview_plot(result)
            
        else:
            # Show error
            error_msg = result.get('error', 'Unknown error')
            self.status_label.config(text=f"❌ Error: {error_msg}", foreground='#D32F2F')
            messagebox.showerror("Calculation Failed", f"Error during correlation calculation:\n\n{error_msg}")
    
    def _update_preview_plot(self, result: dict):
        """Update the correlation function preview plot."""
        try:
            self.ax.clear()
            
            corr_func = result['correlation_func']
            peak_index = result['peak_index']
            
            # Plot correlation function (zoom to interesting region around peak)
            zoom_range = min(10000, len(corr_func) // 20)
            start = max(0, peak_index - zoom_range)
            end = min(len(corr_func), peak_index + zoom_range)
            
            x = range(start, end)
            y = corr_func[start:end]
            
            self.ax.plot(x, y, color='#1976D2', linewidth=1.5)
            # Horizontal line at peak height (not vertical - vertical hides the peak!)
            peak_value = result['peak_value']
            self.ax.axhline(peak_value, color='red', linestyle='--', linewidth=1.5, alpha=0.7, 
                           label=f'Peak: {peak_value:.2f}σ at index {peak_index}')
            self.ax.axhline(0, color='gray', linestyle='-', linewidth=0.5, alpha=0.5)
            
            self.ax.set_title(f'Cross-Correlation Function (zoomed near peak)', fontsize=10)
            self.ax.set_xlabel('Lag Index', fontsize=9)
            self.ax.set_ylabel('Correlation Strength (σ)', fontsize=9)
            self.ax.legend(fontsize=8)
            self.ax.grid(True, alpha=0.3)
            
            self.canvas.draw()
            
        except Exception as e:
            logger.error(f"Failed to update preview plot: {e}")
    
    def _show_correlation_plot(self):
        """Show full correlation function plot in separate window."""
        if not self.last_result or not self.last_result['success']:
            return
        
        # Create new window with full plot
        plot_window = tk.Toplevel(self.root)
        plot_window.title("Full Correlation Function")
        plot_window.geometry("1000x600")
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), facecolor='#F5F5F5')
        ax1.set_facecolor('#FFFFFF')
        ax2.set_facecolor('#FFFFFF')
        
        corr_func = self.last_result['correlation_func']
        peak_index = self.last_result['peak_index']
        
        # Full plot
        peak_value = self.last_result['peak_value']
        ax1.plot(corr_func, color='#1976D2', linewidth=1, alpha=0.7)
        ax1.axhline(peak_value, color='red', linestyle='--', linewidth=1.5, alpha=0.7,
                   label=f'Peak: {peak_value:.2f}σ at index {peak_index}')
        ax1.axhline(0, color='gray', linestyle='-', linewidth=0.5, alpha=0.5)
        ax1.set_title('Full Cross-Correlation Function', fontsize=12, fontweight='bold')
        ax1.set_xlabel('Lag Index', fontsize=10)
        ax1.set_ylabel('Correlation Strength (σ)', fontsize=10)
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Zoomed plot around peak
        zoom_range = min(5000, len(corr_func) // 40)
        start = max(0, peak_index - zoom_range)
        end = min(len(corr_func), peak_index + zoom_range)
        
        ax2.plot(range(start, end), corr_func[start:end], color='#1976D2', linewidth=2)
        ax2.axhline(peak_value, color='red', linestyle='--', linewidth=2, alpha=0.7,
                   label=f'Peak: {peak_value:.2f}σ at index {peak_index}')
        ax2.axhline(0, color='gray', linestyle='-', linewidth=0.5, alpha=0.5)
        ax2.set_title('Zoomed View Around Peak', fontsize=12, fontweight='bold')
        ax2.set_xlabel('Lag Index', fontsize=10)
        ax2.set_ylabel('Correlation Strength (σ)', fontsize=10)
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        fig.tight_layout()
        
        canvas = FigureCanvasTkAgg(fig, master=plot_window)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        canvas.draw()
    
    def _save_to_config(self):
        """Save calculated offset to the selected offset slot."""
        if not self.last_result or not self.last_result['success']:
            return
        
        # Get target slot (0-based)
        slot_idx = int(self.save_offset_slot_var.get()) - 1
        
        # Update the selected offset slot
        self.app_ref.time_offsets_ps[slot_idx] = self.last_result['offset_ps']
        self.app_ref.time_offsets_updated[slot_idx] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Save to file
        self.app_ref._save_time_offset()
        
        # Update the time offset display in main GUI
        if hasattr(self.app_ref, '_update_time_offset_status'):
            self.app_ref._update_time_offset_status()
        
        # Also refresh the entry field in main GUI if it exists
        if hasattr(self.app_ref, 'offset_entries') and slot_idx < len(self.app_ref.offset_entries):
            entry = self.app_ref.offset_entries[slot_idx]
            entry.delete(0, 'end')
            entry.insert(0, str(self.last_result['offset_ps']))
        
        messagebox.showinfo("Saved", 
                           f"Time offset saved to Offset {slot_idx + 1}:\n\n"
                           f"{self.last_result['offset_ps']:,} ps\n"
                           f"({self.last_result['offset_ms']:.3f} ms)")
        
        logger.info(f"Time offset saved to slot {slot_idx + 1}: {self.last_result['offset_ps']} ps")
    
    def _copy_to_clipboard(self):
        """Copy offset value to clipboard."""
        if not self.last_result or not self.last_result['success']:
            return
        
        offset_text = str(self.last_result['offset_ps'])
        self.root.clipboard_clear()
        self.root.clipboard_append(offset_text)
        
        self.status_label.config(text=f"✓ Copied to clipboard: {offset_text} ps",
                                foreground='#2E7D32')
        logger.info(f"Copied offset to clipboard: {offset_text} ps")
