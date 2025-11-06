"""Optimizer row component for polarization controller."""

import threading
import tkinter as tk
from tkinter import ttk

from .helpers import format_number, format_angles
from device_hander import MPC320Controller, TimeController as TCWrapper
from functions import optimize_paddles


class OptimizerRow:
    """Manages a single row in the polarization optimizer tab."""
    
    def __init__(self, frame, row_idx, tc_address, action_color, default_serial=None, default_channel=1):
        self.frame = frame
        self.row_idx = row_idx
        self.tc_address = tc_address
        self.action_color = action_color
        
        # Runtime state
        self.controller = None
        self.tc = None
        self.thread = None
        self.stop_event = threading.Event()
        self.started_set = False
        self.last_iter = 0
        
        self._build_widgets(default_serial, default_channel)
    
    def _build_widgets(self, default_serial, default_channel):
        """Create all widgets for this row."""
        row = 2 + self.row_idx
        
        # Serial input
        self.serial_var = tk.StringVar(value=default_serial or "")
        self.serial_entry = tk.Entry(self.frame, textvariable=self.serial_var, width=14)
        self.serial_entry.grid(row=row, column=0, padx=3)
        
        # Channel selector
        self.channel_var = tk.IntVar(value=default_channel)
        self.channel_box = ttk.Combobox(self.frame, values=[1, 2, 3, 4], width=5, state="readonly")
        self.channel_box.set(default_channel)
        self.channel_box.grid(row=row, column=1)
        
        # Display labels
        self.start_angles_lbl = tk.Label(self.frame, text="- , - , -", width=16)
        self.start_value_lbl = tk.Label(self.frame, text="-", width=10)
        self.angles_lbl = tk.Label(self.frame, text="- , - , -", width=16)
        self.value_lbl = tk.Label(self.frame, text="-", width=10)
        self.best_angles_lbl = tk.Label(self.frame, text="- , - , -", width=16)
        self.best_value_lbl = tk.Label(self.frame, text="-", width=10)
        self.status_lbl = tk.Label(self.frame, text="Idle", width=18)
        
        self.start_angles_lbl.grid(row=row, column=2)
        self.start_value_lbl.grid(row=row, column=3)
        self.angles_lbl.grid(row=row, column=4)
        self.value_lbl.grid(row=row, column=5)
        self.best_angles_lbl.grid(row=row, column=6)
        self.best_value_lbl.grid(row=row, column=7)
        self.status_lbl.grid(row=row, column=8)
        
        # Control buttons
        self.start_btn = tk.Button(self.frame, text="Optimize", 
                                   background=self.action_color, width=12,
                                   command=self._on_start)
        self.stop_btn = tk.Button(self.frame, text="Stop", 
                                  background=self.action_color, width=8,
                                  state=tk.DISABLED, command=self._on_stop)
        
        btn_frame = tk.Frame(self.frame)
        self.start_btn.pack(in_=btn_frame, side=tk.LEFT)
        self.stop_btn.pack(in_=btn_frame, side=tk.LEFT, padx=4)
        btn_frame.grid(row=row, column=9)
    
    def _on_progress(self, it, angles, value, best_angles, best_value):
        """Callback for optimization progress updates."""
        try:
            # Capture start on first callback
            if not self.started_set and it == 0:
                self.start_angles_lbl.config(text=format_angles(angles))
                self.start_value_lbl.config(text=format_number(int(value)))
                self.started_set = True
            
            self.angles_lbl.config(text=format_angles(angles))
            self.value_lbl.config(text=format_number(int(value)))
            self.best_angles_lbl.config(text=format_angles(best_angles))
            self.best_value_lbl.config(text=format_number(int(best_value)))
            self.status_lbl.config(text=f"Iter {it}")
            self.last_iter = it
        except Exception:
            pass
    
    def _run_optimization(self):
        """Run the optimization process in background thread."""
        self.status_lbl.config(text="Csatlakozás...")
        serial = self.serial_var.get().strip()
        
        try:
            channel = int(self.channel_box.get())
        except Exception:
            channel = 1
        
        if not serial:
            self.status_lbl.config(text="Hiányzó serial")
            self.start_btn['state'] = tk.NORMAL
            self.stop_btn['state'] = tk.DISABLED
            return
        
        # Connect controller
        try:
            self.controller = MPC320Controller(serial, channel).connect()
        except Exception:
            self.status_lbl.config(text="Polarizer hiba")
            self.start_btn['state'] = tk.NORMAL
            self.stop_btn['state'] = tk.DISABLED
            return
        
        # Connect Time Controller
        try:
            self.tc = TCWrapper(self.tc_address).connect()
        except Exception:
            self.status_lbl.config(text="TC hiba")
            try:
                self.controller.disconnect()
            except Exception:
                pass
            self.controller = None
            self.start_btn['state'] = tk.NORMAL
            self.stop_btn['state'] = tk.DISABLED
            return
        
        self.status_lbl.config(text="Fut...")
        self.stop_event.clear()
        
        try:
            best_angles, best_value = optimize_paddles(
                controller=self.controller,
                tc=self.tc,
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
                progress=self._on_progress,
                stop_event=self.stop_event,
            )
            self.status_lbl.config(text=f"Kész (iter {self.last_iter})")
        except Exception:
            self.status_lbl.config(text="Hiba")
        finally:
            self._cleanup_connections()
    
    def _cleanup_connections(self):
        """Clean up controller and TC connections."""
        try:
            if self.tc is not None:
                self.tc.close()
        except Exception:
            pass
        self.tc = None
        
        try:
            if self.controller is not None:
                self.controller.disconnect()
        except Exception:
            pass
        self.controller = None
        
        self.start_btn['state'] = tk.NORMAL
        self.stop_btn['state'] = tk.DISABLED
    
    def _on_start(self):
        """Start button handler."""
        self.start_btn['state'] = tk.DISABLED
        self.stop_btn['state'] = tk.NORMAL
        self.started_set = False
        self.thread = threading.Thread(target=self._run_optimization, daemon=True)
        self.thread.start()
    
    def _on_stop(self):
        """Stop button handler."""
        self.status_lbl.config(text="Leállítás...")
        self.stop_event.set()
    
    def has_serial(self):
        """Check if row has a serial number entered."""
        return bool(self.serial_var.get().strip())
    
    def cleanup(self):
        """Clean up resources when closing."""
        try:
            self.stop_event.set()
        except Exception:
            pass
        try:
            if self.tc is not None:
                self.tc.close()
        except Exception:
            pass
        try:
            if self.controller is not None:
                self.controller.disconnect()
        except Exception:
            pass
