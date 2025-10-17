import tkinter as tk
from tkinter import ttk
import threading
import time
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import random

# Reuse existing helpers/utilities; do not change their behavior
# Default Time Controller IP address
DEFAULT_TC_ADDRESS = "169.254.104.112"

from utils.acquisitions import acquire_histograms
from utils.plot import filter_histogram_bins
from utils.common import zmq_exec
from device_hander import MPC320Controller, TimeController as TCWrapper
from functions import optimize_paddles
from mock_time_controller import (
    MockTimeController,
    safe_zmq_exec,
    safe_acquire_histograms,
    is_mock_controller
)


def format_number(number: int) -> str:
    return f"{number:,}".replace(",", " ")


class PlotUpdater:
    def __init__(self, fig, ax, canvas, tc, default_acq_duration, bin_width, default_bin_count, default_histograms):
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

    def _draw_plot(self):
        self.ax.clear()

        if not self.plot_histogram:
            data = self.correlation_series.copy()
            ylim = int(max(1, np.max(data)) / 5000) * 5000 + 5000
            if self.normalize_plot:
                col_sum = np.sum(data, axis=0)
                with np.errstate(divide='ignore', invalid='ignore'):
                    data = np.nan_to_num(data / col_sum, nan=0.0, posinf=0.0, neginf=0.0)
                ylim = 1
            colors = ['blue', 'green', 'red', 'yellow']
            labels = ['1-3 koincidencia', '1-4 koincidencia', '2-3 koincidencia', '2-4 koincidencia']
            for i in range(4):
                self.ax.plot(data[i], color=colors[i], marker='o', linestyle='', label=labels[i])
            self.ax.legend(loc='upper left')
            self.ax.set_ylim([0, ylim])
            self.ax.set_yticks(np.linspace(0, ylim, 11))
            self.ax.set_title('Koincidencia mérés')
            self.ax.set_xlabel('Adat')
            self.ax.set_ylabel('Beütések')
            self.ax.set_xticks(range(0, 20))
        else:
            try:
                max_bin_count = max(len(h) for h in self.histograms.values())
            except Exception:
                max_bin_count = 5000
            self.ax.set(xlabel="ps", ylabel="Darab")
            self.ax.set_xlim(0, max_bin_count * self.bin_width)
            colors2 = ['blue', 'green', 'red', 'yellow']
            for idx, (hist_title, histogram) in enumerate(self.histograms.items()):
                title = f"Histogram {hist_title}" if isinstance(hist_title, int) else hist_title
                bins = filter_histogram_bins(histogram, self.bin_width)
                xp, yp = tuple(bins.keys()), tuple(bins.values())
                self.ax.bar(xp, yp, align="edge", width=self.bin_width, alpha=0.1)
                self.ax.step(xp, yp, color=colors2[idx % len(colors2)], where="post", label=title, alpha=1)
            self.ax.legend(['1-3', '1-4', '2-3', '2-4'])
            self.ax.set_xticks(range(0, max_bin_count * self.bin_width + 1, 200))
            self.ax.set_title('Korrelációs hisztogrammok')

        self.canvas.draw()

    def _loop(self):
        while self.continue_update:
            self._update_measurements()
            self._draw_plot()
            time.sleep(0.1)

    def start(self):
        if self.continue_update:
            return
        self.continue_update = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        if not self.continue_update:
            return
        self.continue_update = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Koincidencia mérés")

        # Theme
        self.bg_color = '#1E1E1E'
        self.fg_color = '#D4D4D4'
        self.highlight_color = '#2E2E2E'
        self.primary_color = '#282828'
        self.action_color = '#007ACC'

        # Connect Time Controller with fallback to mock
        # Import connect function directly to avoid sys.exit() in time_controller_csatlakozas
        from utils.common import connect, adjust_bin_width
        
        self.tc = None
        self.DEFAULT_ACQ_DURATION = 0.5
        self.bin_width = 100
        self.DEFAULT_BIN_COUNT = 20
        self.DEFAULT_HISTOGRAMS = [1, 2, 3, 4]
        
        try:
            self.tc = connect(DEFAULT_TC_ADDRESS)
            self.bin_width = adjust_bin_width(self.tc, 100)
            print("Successfully connected to Time Controller at", DEFAULT_TC_ADDRESS)
        except (ConnectionError, Exception) as e:
            print(f"Failed to connect to Time Controller: {e}")
            print("Using MockTimeController instead")
            self.tc = MockTimeController()

        # Optimizer rows state (up to 4 devices)
        self.optim_rows = {}
        # Default serials to mirror CLI defaults in search_paddle_space
        self.default_serials = [("38530254", 1), ("38532504", 2), ("38521084", 3), ("38530684", 4)]

        # Layout
        self.root.configure(background=self.primary_color)
        self.root.rowconfigure(0, weight=0)  # Status bar row
        self.root.rowconfigure(1, weight=1)  # Main content row
        self.root.columnconfigure(0, weight=1)
        self.root.columnconfigure(1, weight=1)

        # Status indicator at the top
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

        # Tabbed notebook on the left, plot on the right (same visual layout)
        self.notebook = ttk.Notebook(self.root)
        self.tab_plot = ttk.Frame(self.notebook)
        self.tab_polarizer = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_plot, text="Plotolás")
        self.notebook.add(self.tab_polarizer, text="Polarizáció kontroller")
        self.notebook.grid(row=1, column=0, sticky="news")

        # Plot frame on the right
        self.plot_frame = tk.Frame(self.root, background=self.primary_color)
        self.plot_frame.grid(row=1, column=1, sticky="news")
        self._build_plot_tab()
        self._build_polarizer_tab()

        # Graceful shutdown to avoid dangling after-callbacks
        self._after_id = None
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_plot_tab(self):
        # Figure
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

        # Updater
        self.plot_updater = PlotUpdater(
            fig,
            ax,
            canvas,
            self.tc,
            self.DEFAULT_ACQ_DURATION,
            self.bin_width,
            self.DEFAULT_BIN_COUNT,
            self.DEFAULT_HISTOGRAMS,
        )

        # Controls (left side of Plot tab area)
        controls = tk.Frame(self.tab_plot, relief=tk.GROOVE, bd=2, width=600)
        controls.grid(row=0, column=0, sticky="nws", pady=5)

        label = tk.Label(controls, text="Plot:", width=20, height=2)
        btn_start = tk.Button(
            controls,
            text="Start",
            background=self.action_color,
            width=15,
            command=self.plot_updater.start,
        )
        btn_stop = tk.Button(
            controls,
            text="Stop",
            background=self.action_color,
            width=15,
            command=self.plot_updater.stop,
        )
        cb_hist = tk.Checkbutton(
            controls,
            text='Hisztogram',
            onvalue=True,
            offvalue=False,
            command=lambda: setattr(self.plot_updater, 'plot_histogram', not self.plot_updater.plot_histogram),
        )
        cb_norm = tk.Checkbutton(
            controls,
            text='Normált',
            onvalue=True,
            offvalue=False,
            command=lambda: setattr(self.plot_updater, 'normalize_plot', not self.plot_updater.normalize_plot),
        )

        label.grid(row=0, column=0, sticky="news")
        btn_start.grid(row=0, column=1, sticky="news", padx=2)
        btn_stop.grid(row=0, column=2, sticky="news")
        cb_hist.grid(row=1, column=1, sticky="news", pady=4)
        cb_norm.grid(row=1, column=2, sticky="news", pady=4)

        # Live counters panel
        counters = tk.Frame(self.tab_plot, relief=tk.GROOVE, bd=2, width=600)
        counters.grid(row=1, column=0, sticky="nws", pady=5)
        tk.Label(counters, text="Detektorok beütésszámai", width=20, height=2).grid(row=0, column=0, columnspan=4, sticky="news")

        self.beutes_labels = [
            tk.Label(counters, text="0", width=10),
            tk.Label(counters, text="0", width=10),
            tk.Label(counters, text="0", width=10),
            tk.Label(counters, text="0", width=10),
        ]
        for i, lbl in enumerate(self.beutes_labels):
            tk.Label(counters, text=f"{i+1}.").grid(row=1, column=i, sticky="news")
            lbl.grid(row=2, column=i, sticky="news")

        # Periodically mirror beutes_szamok to labels
        def _mirror_counters():
            vals = getattr(self.plot_updater, 'beutes_szamok', [0, 0, 0, 0])
            try:
                for i in range(4):
                    # Skip if label was already destroyed during shutdown
                    if self.beutes_labels[i].winfo_exists():
                        self.beutes_labels[i].config(text=format_number(vals[i]))
            except Exception:
                pass
            # Re-schedule only if window still exists
            if self.root.winfo_exists():
                self._after_id = self.root.after(300, _mirror_counters)

        _mirror_counters()

    def _build_polarizer_tab(self):
        frame = tk.Frame(self.tab_polarizer, relief=tk.GROOVE, bd=2, width=800)
        frame.grid(row=0, column=0, sticky="nws", pady=5)

        tk.Label(frame, text="Polarizáció optimizálás", width=60, height=2).grid(row=0, column=0, columnspan=10, sticky="news")

        headers = [
            "Sorszám (Serial)",
            "TC csatorna",
            "Kezdő [deg]",
            "Kezdő érték",
            "Szögek [deg]",
            "Aktuális érték",
            "Legjobb [deg]",
            "Legjobb érték",
            "Állapot",
            "Művelet",
        ]
        for j, h in enumerate(headers):
            tk.Label(frame, text=h).grid(row=1, column=j, padx=3, pady=2)

        def make_row(row_idx: int):
            row = {}
            # Inputs
            row['serial_var'] = tk.StringVar()
            row['serial_entry'] = tk.Entry(frame, textvariable=row['serial_var'], width=14)
            row['serial_entry'].grid(row=2 + row_idx, column=0, padx=3)

            row['channel_var'] = tk.IntVar(value=1 + row_idx)
            row['channel_box'] = ttk.Combobox(frame, values=[1, 2, 3, 4], width=5, state="readonly")
            row['channel_box'].set(row['channel_var'].get())
            row['channel_box'].grid(row=2 + row_idx, column=1)

            # Start, live, and best values
            row['start_angles_lbl'] = tk.Label(frame, text="- , - , -", width=16)
            row['start_value_lbl'] = tk.Label(frame, text="-", width=10)
            row['angles_lbl'] = tk.Label(frame, text="- , - , -", width=16)
            row['value_lbl'] = tk.Label(frame, text="-", width=10)
            row['best_angles_lbl'] = tk.Label(frame, text="- , - , -", width=16)
            row['best_value_lbl'] = tk.Label(frame, text="-", width=10)
            row['status_lbl'] = tk.Label(frame, text="Idle", width=18)
            row['start_angles_lbl'].grid(row=2 + row_idx, column=2)
            row['start_value_lbl'].grid(row=2 + row_idx, column=3)
            row['angles_lbl'].grid(row=2 + row_idx, column=4)
            row['value_lbl'].grid(row=2 + row_idx, column=5)
            row['best_angles_lbl'].grid(row=2 + row_idx, column=6)
            row['best_value_lbl'].grid(row=2 + row_idx, column=7)
            row['status_lbl'].grid(row=2 + row_idx, column=8)

            # Control buttons
            row['start_btn'] = tk.Button(frame, text="Optimize", background=self.action_color, width=12)
            row['stop_btn'] = tk.Button(frame, text="Stop", background=self.action_color, width=8, state=tk.DISABLED)
            btn_frame = tk.Frame(frame)
            row['start_btn'].pack(in_=btn_frame, side=tk.LEFT)
            row['stop_btn'].pack(in_=btn_frame, side=tk.LEFT, padx=4)
            btn_frame.grid(row=2 + row_idx, column=9)

            # Runtime state
            row['controller'] = None
            row['tc'] = None
            row['thread'] = None
            row['stop_event'] = threading.Event()
            row['started_set'] = False
            row['last_iter'] = 0

            def on_progress(it, angles, value, best_angles, best_value):
                try:
                    # capture start on first callback
                    if not row['started_set'] and it == 0:
                        row['start_angles_lbl'].config(text=f"{angles[0]:.1f}, {angles[1]:.1f}, {angles[2]:.1f}")
                        row['start_value_lbl'].config(text=format_number(int(value)))
                        row['started_set'] = True
                    row['angles_lbl'].config(text=f"{angles[0]:.1f}, {angles[1]:.1f}, {angles[2]:.1f}")
                    row['value_lbl'].config(text=format_number(int(value)))
                    row['best_angles_lbl'].config(text=f"{best_angles[0]:.1f}, {best_angles[1]:.1f}, {best_angles[2]:.1f}")
                    row['best_value_lbl'].config(text=format_number(int(best_value)))
                    row['status_lbl'].config(text=f"Iter {it}")
                    row['last_iter'] = it
                except Exception:
                    pass

            def run_opt():
                row['status_lbl'].config(text="Csatlakozás...")
                serial = row['serial_var'].get().strip()
                try:
                    channel = int(row['channel_box'].get())
                except Exception:
                    channel = 1
                if not serial:
                    row['status_lbl'].config(text="Hiányzó serial")
                    row['start_btn']['state'] = tk.NORMAL
                    row['stop_btn']['state'] = tk.DISABLED
                    return
                try:
                    # Connect controller and dedicated TC
                    row['controller'] = MPC320Controller(serial, channel).connect()
                except Exception:
                    row['status_lbl'].config(text="Polarizer hiba")
                    row['start_btn']['state'] = tk.NORMAL
                    row['stop_btn']['state'] = tk.DISABLED
                    return
                try:
                    row['tc'] = TCWrapper(DEFAULT_TC_ADDRESS).connect()
                except Exception:
                    row['status_lbl'].config(text="TC hiba")
                    try:
                        row['controller'].disconnect()
                    except Exception:
                        pass
                    row['controller'] = None
                    row['start_btn']['state'] = tk.NORMAL
                    row['stop_btn']['state'] = tk.DISABLED
                    return

                row['status_lbl'].config(text="Fut...")
                # Reset stop flag
                row['stop_event'].clear()
                try:
                    best_angles, best_value = optimize_paddles(
                        controller=row['controller'],
                        tc=row['tc'],
                        channel=channel,
                        angle_min=0.0,
                        angle_max=160.0,
                        seeds=4,
                        measure_samples=2,
                        dwell_after_move_s=0.05,
                        fd_delta_deg=2.0,
                        lr_deg=5.0,
                        momentum_beta=0.8,
                        max_iters=80,
                        patience=10,
                        progress=on_progress,
                        stop_event=row['stop_event'],
                    )
                    row['status_lbl'].config(text=f"Kész (iter {row['last_iter']})")
                except Exception:
                    row['status_lbl'].config(text="Hiba")
                finally:
                    try:
                        if row['tc'] is not None:
                            row['tc'].close()
                    except Exception:
                        pass
                    row['tc'] = None
                    try:
                        if row['controller'] is not None:
                            row['controller'].disconnect()
                    except Exception:
                        pass
                    row['controller'] = None
                    row['start_btn']['state'] = tk.NORMAL
                    row['stop_btn']['state'] = tk.DISABLED

            def on_start():
                row['start_btn']['state'] = tk.DISABLED
                row['stop_btn']['state'] = tk.NORMAL
                row['thread'] = threading.Thread(target=run_opt, daemon=True)
                row['thread'].start()

            def on_stop():
                row['status_lbl'].config(text="Leállítás...")
                row['stop_event'].set()
                # Let thread finish gracefully; no join to avoid blocking UI

            row['start_btn']['command'] = on_start
            row['stop_btn']['command'] = on_stop

            self.optim_rows[row_idx] = row

            # Prefill defaults if available
            try:
                if row_idx < len(self.default_serials):
                    s, ch = self.default_serials[row_idx]
                    row['serial_var'].set(s)
                    row['channel_box'].set(ch)
            except Exception:
                pass

        # Create 4 rows
        for r in range(4):
            make_row(r)

        # Bulk controls
        bulk = tk.Frame(self.tab_polarizer, relief=tk.GROOVE, bd=2, width=800)
        bulk.grid(row=1, column=0, sticky="nws", pady=5)
        tk.Button(bulk, text="Optimize all", background=self.action_color, width=16,
                  command=lambda: [self.optim_rows[i]['start_btn'].invoke() for i in range(4) if self.optim_rows[i]['serial_var'].get().strip()]
                  ).grid(row=0, column=0, padx=4)
        tk.Button(bulk, text="Stop all", background=self.action_color, width=16,
                  command=lambda: [self.optim_rows[i]['stop_btn'].invoke() for i in range(4)]
                  ).grid(row=0, column=1, padx=4)
        # Optimize one (select row 1..4)
        tk.Label(bulk, text="Row").grid(row=0, column=2, padx=4)
        sel_var = tk.StringVar(value="1")
        sel_combo = ttk.Combobox(bulk, values=["1", "2", "3", "4"], width=4, state="readonly", textvariable=sel_var)
        sel_combo.grid(row=0, column=3, padx=2)
        def _opt_one():
            try:
                idx = max(0, min(3, int(sel_var.get()) - 1))
            except Exception:
                idx = 0
            row = self.optim_rows.get(idx)
            if not row:
                return
            if row['serial_var'].get().strip():
                row['start_btn'].invoke()
            else:
                try:
                    row['status_lbl'].config(text="Hiányzó serial")
                except Exception:
                    pass
        tk.Button(bulk, text="Optimize one", background=self.action_color, width=16, command=_opt_one).grid(row=0, column=4, padx=4)

    def _on_close(self):
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
                    row['stop_event'].set()
                except Exception:
                    pass
                try:
                    if row.get('tc') is not None:
                        row['tc'].close()
                except Exception:
                    pass
                try:
                    if row.get('controller') is not None:
                        row['controller'].disconnect()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            # Close Time Controller socket
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
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()


