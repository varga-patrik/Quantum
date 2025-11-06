import tkinter as tk
from tkinter import ttk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from gui_components import (
    DEFAULT_TC_ADDRESS, DEFAULT_ACQ_DURATION, DEFAULT_BIN_WIDTH,
    DEFAULT_BIN_COUNT, DEFAULT_HISTOGRAMS, BG_COLOR, FG_COLOR,
    HIGHLIGHT_COLOR, PRIMARY_COLOR, ACTION_COLOR, DEFAULT_SERIALS,
    format_number, PlotUpdater, OptimizerRow
)
from mock_time_controller import MockTimeController, is_mock_controller


class App:
    """Main application class for the GUI."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Koincidencia mérés")

        # Apply theme colors
        self.bg_color = BG_COLOR
        self.fg_color = FG_COLOR
        self.highlight_color = HIGHLIGHT_COLOR
        self.primary_color = PRIMARY_COLOR
        self.action_color = ACTION_COLOR

        # Initialize Time Controller
        self.tc = self._connect_time_controller()
        
        # Optimizer rows state
        self.optim_rows = {}

        # Setup UI layout
        self._setup_layout()
        self._build_status_indicator()
        self._build_notebook()
        self._build_plot_frame()
        self._build_plot_tab()
        self._build_polarizer_tab()

        # Graceful shutdown handler
        self._after_id = None
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _connect_time_controller(self):
        """Connect to Time Controller with fallback to mock."""
        from utils.common import connect, adjust_bin_width
        
        tc = None
        try:
            tc = connect(DEFAULT_TC_ADDRESS)
            self.bin_width = adjust_bin_width(tc, DEFAULT_BIN_WIDTH)
            print("Successfully connected to Time Controller at", DEFAULT_TC_ADDRESS)
        except (ConnectionError, Exception) as e:
            print(f"Failed to connect to Time Controller: {e}")
            print("Using MockTimeController instead")
            tc = MockTimeController()
            self.bin_width = DEFAULT_BIN_WIDTH
        
        return tc

    def _setup_layout(self):
        """Configure root window layout."""
        self.root.configure(background=self.primary_color)
        self.root.rowconfigure(0, weight=0)  # Status bar row
        self.root.rowconfigure(1, weight=1)  # Main content row
        self.root.columnconfigure(0, weight=1)
        self.root.columnconfigure(1, weight=1)

    def _build_status_indicator(self):
        """Build status indicator bar for mock mode."""
        if is_mock_controller(self.tc):
            status_frame = tk.Frame(self.root, background='#ff9800', relief=tk.RAISED, bd=2)
            status_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
            status_label = tk.Label(
                status_frame,
                text="⚠️ MOCK MODE: Using random data (20,000-100,000) - Time Controller not connected",
                font=('Arial', 10, 'bold'),
                background='#ff9800',
                foreground='white',
                pady=8
            )
            status_label.pack(fill=tk.BOTH, expand=True)

    def _build_notebook(self):
        """Create tabbed notebook on the left."""
        self.notebook = ttk.Notebook(self.root)
        self.tab_plot = ttk.Frame(self.notebook)
        self.tab_polarizer = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_plot, text="Plotolás")
        self.notebook.add(self.tab_polarizer, text="Polarizáció kontroller")
        self.notebook.grid(row=1, column=0, sticky="news")

    def _build_plot_frame(self):
        """Create plot frame on the right."""
        self.plot_frame = tk.Frame(self.root, background=self.primary_color)
        self.plot_frame.grid(row=1, column=1, sticky="news")


    def _build_plot_tab(self):
        """Build the plot tab with controls and live counters."""
        # Create matplotlib figure
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.set_title('Koincidencia mérés')
        ax.set_xlabel('Adat')
        ax.set_ylabel('Beütések')
        ax.set_xticks(range(0, 20))
        ax.set_ylim([0, 4000])
        ax.set_facecolor(self.bg_color)
        ax.grid(color=self.highlight_color)

        canvas = FigureCanvasTkAgg(fig, master=self.plot_frame)
        canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)
        canvas.get_tk_widget().config(background=self.primary_color)

        # Create plot updater
        self.plot_updater = PlotUpdater(
            fig, ax, canvas, self.tc,
            DEFAULT_ACQ_DURATION, self.bin_width,
            DEFAULT_BIN_COUNT, DEFAULT_HISTOGRAMS
        )

        # Build control panel
        self._build_plot_controls()
        
        # Build live counters panel
        self._build_live_counters()

    def _build_plot_controls(self):
        """Build plot control buttons and checkboxes."""
        controls = tk.Frame(self.tab_plot, relief=tk.GROOVE, bd=2, width=600)
        controls.grid(row=0, column=0, sticky="nws", pady=5)

        tk.Label(controls, text="Plot:", width=20, height=2).grid(row=0, column=0, sticky="news")
        
        btn_start = tk.Button(
            controls, text="Start", background=self.action_color, width=15,
            command=self.plot_updater.start
        )
        btn_start.grid(row=0, column=1, sticky="news", padx=2)
        
        btn_stop = tk.Button(
            controls, text="Stop", background=self.action_color, width=15,
            command=self.plot_updater.stop
        )
        btn_stop.grid(row=0, column=2, sticky="news")
        
        cb_hist = tk.Checkbutton(
            controls, text='Hisztogram', onvalue=True, offvalue=False,
            command=lambda: setattr(self.plot_updater, 'plot_histogram', 
                                   not self.plot_updater.plot_histogram)
        )
        cb_hist.grid(row=1, column=1, sticky="news", pady=4)
        
        cb_norm = tk.Checkbutton(
            controls, text='Normált', onvalue=True, offvalue=False,
            command=lambda: setattr(self.plot_updater, 'normalize_plot', 
                                   not self.plot_updater.normalize_plot)
        )
        cb_norm.grid(row=1, column=2, sticky="news", pady=4)

    def _build_live_counters(self):
        """Build live detector counter display."""
        counters = tk.Frame(self.tab_plot, relief=tk.GROOVE, bd=2, width=600)
        counters.grid(row=1, column=0, sticky="nws", pady=5)
        
        tk.Label(counters, text="Detektorok beütésszámai", width=20, height=2).grid(
            row=0, column=0, columnspan=4, sticky="news"
        )

        self.beutes_labels = []
        for i in range(4):
            tk.Label(counters, text=f"{i+1}.").grid(row=1, column=i, sticky="news")
            lbl = tk.Label(counters, text="0", width=10)
            lbl.grid(row=2, column=i, sticky="news")
            self.beutes_labels.append(lbl)

        # Start periodic counter update
        self._update_counters()

    def _update_counters(self):
        """Periodically update counter labels from plot updater."""
        vals = getattr(self.plot_updater, 'beutes_szamok', [0, 0, 0, 0])
        try:
            for i in range(4):
                if self.beutes_labels[i].winfo_exists():
                    self.beutes_labels[i].config(text=format_number(vals[i]))
        except Exception:
            pass
        
        if self.root.winfo_exists():
            self._after_id = self.root.after(300, self._update_counters)


    def _build_polarizer_tab(self):
        """Build the polarization controller tab with optimizer rows."""
        frame = tk.Frame(self.tab_polarizer, relief=tk.GROOVE, bd=2, width=800)
        frame.grid(row=0, column=0, sticky="nws", pady=5)

        # Header
        tk.Label(frame, text="Polarizáció optimizálás", width=60, height=2).grid(
            row=0, column=0, columnspan=10, sticky="news"
        )

        # Column headers
        headers = [
            "Sorszám (Serial)", "TC csatorna", "Kezdő [deg]", "Kezdő érték",
            "Szögek [deg]", "Aktuális érték", "Legjobb [deg]", "Legjobb érték",
            "Állapot", "Művelet"
        ]
        for j, h in enumerate(headers):
            tk.Label(frame, text=h).grid(row=1, column=j, padx=3, pady=2)

        # Create 4 optimizer rows
        for r in range(4):
            default_serial, default_channel = DEFAULT_SERIALS[r] if r < len(DEFAULT_SERIALS) else (None, r + 1)
            row = OptimizerRow(frame, r, DEFAULT_TC_ADDRESS, self.action_color, 
                             default_serial, default_channel)
            self.optim_rows[r] = row

        # Build bulk controls
        self._build_bulk_controls()

    def _build_bulk_controls(self):
        """Build bulk control buttons for all optimizer rows."""
        bulk = tk.Frame(self.tab_polarizer, relief=tk.GROOVE, bd=2, width=800)
        bulk.grid(row=1, column=0, sticky="nws", pady=5)
        
        # Optimize all button
        tk.Button(
            bulk, text="Optimize all", background=self.action_color, width=16,
            command=self._optimize_all
        ).grid(row=0, column=0, padx=4)
        
        # Stop all button
        tk.Button(
            bulk, text="Stop all", background=self.action_color, width=16,
            command=self._stop_all
        ).grid(row=0, column=1, padx=4)
        
        # Single row selector
        tk.Label(bulk, text="Row").grid(row=0, column=2, padx=4)
        self.sel_var = tk.StringVar(value="1")
        sel_combo = ttk.Combobox(bulk, values=["1", "2", "3", "4"], width=4, 
                                state="readonly", textvariable=self.sel_var)
        sel_combo.grid(row=0, column=3, padx=2)
        
        # Optimize one button
        tk.Button(
            bulk, text="Optimize one", background=self.action_color, width=16,
            command=self._optimize_one
        ).grid(row=0, column=4, padx=4)

    def _optimize_all(self):
        """Start optimization for all rows with serial numbers."""
        for i in range(4):
            row = self.optim_rows.get(i)
            if row and row.has_serial():
                row._on_start()

    def _stop_all(self):
        """Stop optimization for all rows."""
        for i in range(4):
            row = self.optim_rows.get(i)
            if row:
                row._on_stop()

    def _optimize_one(self):
        """Start optimization for selected row."""
        try:
            idx = max(0, min(3, int(self.sel_var.get()) - 1))
        except Exception:
            idx = 0
        
        row = self.optim_rows.get(idx)
        if row and row.has_serial():
            row._on_start()
        elif row:
            try:
                row.status_lbl.config(text="Hiányzó serial")
            except Exception:
                pass


    def _on_close(self):
        """Handle window close event with proper cleanup."""
        # Stop background updater loop
        try:
            if hasattr(self, 'plot_updater'):
                self.plot_updater.stop()
        except Exception:
            pass
        
        # Cancel scheduled UI updates
        try:
            if self._after_id is not None:
                self.root.after_cancel(self._after_id)
                self._after_id = None
        except Exception:
            pass
        
        # Cleanup per-row optimizer resources
        try:
            for i in list(getattr(self, 'optim_rows', {}).keys()):
                row = self.optim_rows[i]
                try:
                    row.cleanup()
                except Exception:
                    pass
        except Exception:
            pass
        
        # Close Time Controller socket
        try:
            if hasattr(self, 'tc') and self.tc is not None:
                try:
                    self.tc.close(0)
                except Exception:
                    try:
                        self.tc.close()
                    except Exception:
                        pass
        except Exception:
            pass
        
        # Close matplotlib figures
        try:
            plt.close('all')
        except Exception:
            pass
        
        # Ensure Tk loop exits then destroy window
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass


def main():
    """Main entry point for the application."""
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()

