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
        
        # Selected file paths
        self.local_file_path = None
        self.remote_file_path = None
        
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
        # Main container with padding
        container = tk.Frame(self.parent, background=self.bg_color)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Header
        header = tk.Label(container, 
                         text="⏱️ Time Offset Calculator (FFT Cross-Correlation)",
                         font=('Arial', 12, 'bold'),
                         background=self.bg_color, foreground=self.fg_color)
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
        """Build file selection section."""
        file_frame = tk.LabelFrame(parent, text="📁 Timestamp Files", 
                                   font=('Arial', 10, 'bold'),
                                   background='#E8F5E9', bd=2, relief=tk.RIDGE,
                                   padx=10, pady=5)
        file_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Local file
        local_row = tk.Frame(file_frame, background='#E8F5E9')
        local_row.pack(fill=tk.X, pady=2)
        
        tk.Label(local_row, text="LOCAL:", font=('Arial', 9, 'bold'),
                background='#E8F5E9', width=10, anchor='w').pack(side=tk.LEFT, padx=(0, 5))
        
        self.local_file_label = tk.Label(local_row, text="No file selected",
                                         font=('Courier New', 8),
                                         background='white', foreground='#666',
                                         relief=tk.SUNKEN, anchor='w', padx=3)
        self.local_file_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        tk.Button(local_row, text="Browse", command=self._browse_local_file,
                 background='#4CAF50', foreground='white', width=10,
                 font=('Arial', 8, 'bold')).pack(side=tk.LEFT)
        
        # Remote file
        remote_row = tk.Frame(file_frame, background='#E8F5E9')
        remote_row.pack(fill=tk.X, pady=2)
        
        tk.Label(remote_row, text="REMOTE:", font=('Arial', 9, 'bold'),
                background='#E8F5E9', width=10, anchor='w').pack(side=tk.LEFT, padx=(0, 5))
        
        self.remote_file_label = tk.Label(remote_row, text="No file selected",
                                          font=('Courier New', 8),
                                          background='white', foreground='#666',
                                          relief=tk.SUNKEN, anchor='w', padx=3)
        self.remote_file_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        tk.Button(remote_row, text="Browse", command=self._browse_remote_file,
                 background='#2196F3', foreground='white', width=10,
                 font=('Arial', 8, 'bold')).pack(side=tk.LEFT)
    
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
        
        # Number of bins
        tk.Label(params_grid, text="FFT Bins (N):", background='#FFF3E0',
                font=('Arial', 9)).grid(row=1, column=0, sticky='e', padx=5, pady=3)
        self.n_var = tk.StringVar(value="1048576")
        tk.Entry(params_grid, textvariable=self.n_var, width=12,
                font=('Courier New', 9)).grid(row=1, column=1, padx=5, pady=3)
        tk.Label(params_grid, text="(2^20)", background='#FFF3E0',
                font=('Arial', 8), foreground='#666').grid(row=1, column=2, sticky='w', padx=5)
        
        # Initial shift
        tk.Label(params_grid, text="Initial Shift:", background='#FFF3E0',
                font=('Arial', 9)).grid(row=2, column=0, sticky='e', padx=5, pady=3)
        self.tshift_var = tk.StringVar(value="100000000")
        tk.Entry(params_grid, textvariable=self.tshift_var, width=12,
                font=('Courier New', 9)).grid(row=2, column=1, padx=5, pady=3)
        tk.Label(params_grid, text="ps (100 ms)", background='#FFF3E0',
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
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.canvas.draw()
    
    def _auto_detect_files(self):
        """Auto-detect most recent timestamp files."""
        try:
            # Look for recent local files
            local_dir = Path.home() / "Documents" / "AgodSolt" / "data"
            if local_dir.exists():
                local_files = sorted(local_dir.glob("timestamps_live_ch1_*.bin"), 
                                   key=lambda p: p.stat().st_mtime, reverse=True)
                if local_files:
                    self._set_local_file(local_files[0])
            
            # Look for recent remote files
            remote_dir = local_dir / "remote"
            if remote_dir.exists():
                remote_files = sorted(remote_dir.glob("timestamps_live_ch1_*.bin"),
                                    key=lambda p: p.stat().st_mtime, reverse=True)
                if remote_files:
                    self._set_remote_file(remote_files[0])
        except Exception as e:
            logger.debug(f"Auto-detect files failed: {e}")
    
    def _browse_local_file(self):
        """Open file browser for local timestamp file."""
        initial_dir = Path.home() / "Documents" / "AgodSolt" / "data"
        filepath = filedialog.askopenfilename(
            title="Select Local Timestamp File",
            initialdir=str(initial_dir) if initial_dir.exists() else None,
            filetypes=[("Binary files", "*.bin"), ("All files", "*.*")]
        )
        if filepath:
            self._set_local_file(Path(filepath))
    
    def _browse_remote_file(self):
        """Open file browser for remote timestamp file."""
        initial_dir = Path.home() / "Documents" / "AgodSolt" / "data" / "remote"
        filepath = filedialog.askopenfilename(
            title="Select Remote Timestamp File",
            initialdir=str(initial_dir) if initial_dir.exists() else None,
            filetypes=[("Binary files", "*.bin"), ("All files", "*.*")]
        )
        if filepath:
            self._set_remote_file(Path(filepath))
    
    def _set_local_file(self, filepath: Path):
        """Set local file and update UI."""
        self.local_file_path = filepath
        self.local_file_label.config(text=filepath.name, foreground='#2E7D32')
        logger.info(f"Local file selected: {filepath.name}")
    
    def _set_remote_file(self, filepath: Path):
        """Set remote file and update UI."""
        self.remote_file_path = filepath
        self.remote_file_label.config(text=filepath.name, foreground='#1565C0')
        logger.info(f"Remote file selected: {filepath.name}")
    
    def _start_calculation(self):
        """Start correlation calculation in background thread."""
        # Validate file selection
        if not self.local_file_path or not self.remote_file_path:
            messagebox.showwarning("Files Required",
                                  "Please select both local and remote timestamp files.")
            return
        
        if not self.local_file_path.exists():
            messagebox.showerror("File Not Found", f"Local file not found:\n{self.local_file_path}")
            return
        
        if not self.remote_file_path.exists():
            messagebox.showerror("File Not Found", f"Remote file not found:\n{self.remote_file_path}")
            return
        
        # Parse parameters
        try:
            tau = int(self.tau_var.get())
            N = int(self.n_var.get())
            Tshift = int(self.tshift_var.get())
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
        self.status_label.config(text="Calculating... This may take 5-10 seconds",
                                foreground='#FF9800')
        
        # Run in background thread
        def calculation_thread():
            result = self.calculator.run_correlation(self.local_file_path, self.remote_file_path)
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
            self.ax.axvline(peak_index, color='red', linestyle='--', linewidth=2, label=f'Peak at {peak_index}')
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
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
        
        corr_func = self.last_result['correlation_func']
        peak_index = self.last_result['peak_index']
        
        # Full plot
        ax1.plot(corr_func, color='#1976D2', linewidth=1, alpha=0.7)
        ax1.axvline(peak_index, color='red', linestyle='--', linewidth=2, label=f'Peak at {peak_index}')
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
        ax2.axvline(peak_index, color='red', linestyle='--', linewidth=2, label=f'Peak at {peak_index}')
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
        """Save calculated offset to config file."""
        if not self.last_result or not self.last_result['success']:
            return
        
        # Update main app's time offset
        self.app_ref.time_offset_ps = self.last_result['offset_ps']
        self.app_ref.time_offset_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Save to file
        self.app_ref._save_time_offset()
        
        # Update the time offset tab display in main GUI
        if hasattr(self.app_ref, '_update_time_offset_status'):
            self.app_ref._update_time_offset_status()
        
        messagebox.showinfo("Saved", 
                           f"Time offset saved to config:\n\n"
                           f"{self.last_result['offset_ps']:,} ps\n"
                           f"({self.last_result['offset_ms']:.3f} ms)\n\n"
                           f"This will be used for future coincidence calculations.")
        
        logger.info(f"Time offset saved to config: {self.last_result['offset_ps']} ps")
    
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
