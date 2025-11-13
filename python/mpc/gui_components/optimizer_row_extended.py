"""Extended optimizer row supporting both local and remote device control."""

import threading
import tkinter as tk
from tkinter import ttk
from typing import Optional

from .helpers import format_number, format_angles
from device_hander import MPC320Controller, TimeController as TCWrapper
from functions import optimize_paddles


class OptimizerRowExtended:
    """
    Extended optimizer row that can control both local and remote MPC320 devices.
    Remote control sends commands via PeerConnection.
    """
    
    def __init__(self, frame, row_idx, tc_address, action_color, 
                 is_remote: bool = False, peer_connection=None,
                 default_serial=None, default_channel=1):
        self.frame = frame
        self.row_idx = row_idx
        self.tc_address = tc_address
        self.action_color = action_color
        self.is_remote = is_remote
        self.peer_connection = peer_connection
        
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
        
        # Style serial entry for remote rows (light blue background)
        if self.is_remote:
            self.serial_entry.config(background='#E3F2FD')  # Light blue for remote
        
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
        
        # Remote indicator
        if self.is_remote:
            self.status_lbl.config(foreground='blue')
        
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
            
            # Send progress update to peer (if local row and connected)
            if not self.is_remote and self.peer_connection and self.peer_connection.is_connected():
                self.peer_connection.send_command('PROGRESS_UPDATE', {
                    'row_index': self.row_idx,
                    'iteration': it,
                    'angles': list(angles),
                    'value': int(value),
                    'best_angles': list(best_angles),
                    'best_value': int(best_value)
                })
        except Exception:
            pass
    
    def handle_remote_progress(self, data: dict):
        """Handle progress update from remote peer."""
        try:
            it = data.get('iteration', 0)
            angles = data.get('angles', [0, 0, 0])
            value = data.get('value', 0)
            best_angles = data.get('best_angles', [0, 0, 0])
            best_value = data.get('best_value', 0)
            
            self._on_progress(it, angles, value, best_angles, best_value)
        except Exception as e:
            import logging
            logging.exception("Error handling remote progress: %s", e)
    
    def handle_remote_status(self, data: dict):
        """Handle status update from remote peer."""
        try:
            status = data.get('status', 'Unknown')
            self.status_lbl.config(text=status)
            
            if status in ['Kész', 'Hiba', 'Idle', 'Leállítva']:
                self.start_btn['state'] = tk.NORMAL
                self.stop_btn['state'] = tk.DISABLED
        except Exception as e:
            import logging
            logging.exception("Error handling remote status: %s", e)
    
    def _send_status_to_peer(self, status: str):
        """Send status update to peer."""
        if self.peer_connection and self.peer_connection.is_connected():
            self.peer_connection.send_command('STATUS_UPDATE', {
                'row_index': self.row_idx,
                'status': status
            })
    
    def _run_optimization_local(self):
        """Run local optimization process."""
        self.status_lbl.config(text="Csatlakozás...")
        self._send_status_to_peer("Csatlakozás...")
        
        serial = self.serial_var.get().strip()
        
        try:
            channel = int(self.channel_box.get())
        except Exception:
            channel = 1
        
        if not serial:
            self.status_lbl.config(text="Hiányzó serial")
            self._send_status_to_peer("Hiányzó serial")
            self.start_btn['state'] = tk.NORMAL
            self.stop_btn['state'] = tk.DISABLED
            return
        
        # Connect controller
        try:
            self.controller = MPC320Controller(serial, channel).connect()
        except Exception:
            self.status_lbl.config(text="Polarizer hiba")
            self._send_status_to_peer("Polarizer hiba")
            self.start_btn['state'] = tk.NORMAL
            self.stop_btn['state'] = tk.DISABLED
            return
        
        # Connect Time Controller
        try:
            self.tc = TCWrapper(self.tc_address).connect()
        except Exception:
            self.status_lbl.config(text="TC hiba")
            self._send_status_to_peer("TC hiba")
            try:
                self.controller.disconnect()
            except Exception:
                pass
            self.controller = None
            self.start_btn['state'] = tk.NORMAL
            self.stop_btn['state'] = tk.DISABLED
            return
        
        self.status_lbl.config(text="Fut...")
        self._send_status_to_peer("Fut...")
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
            final_status = f"Kész (iter {self.last_iter})"
            self.status_lbl.config(text=final_status)
            self._send_status_to_peer(final_status)
        except Exception:
            self.status_lbl.config(text="Hiba")
            self._send_status_to_peer("Hiba")
        finally:
            self._cleanup_connections()
    
    def _run_optimization_remote(self):
        """Send remote optimization command via peer connection."""
        if self.peer_connection is None or not self.peer_connection.is_connected():
            self.status_lbl.config(text="Nincs kapcsolat")
            self.start_btn['state'] = tk.NORMAL
            self.stop_btn['state'] = tk.DISABLED
            return
        
        serial = self.serial_var.get().strip()
        
        try:
            channel = int(self.channel_box.get())
        except Exception:
            channel = 1
        
        # Send start command to peer
        success = self.peer_connection.send_command('OPTIMIZE_START', {
            'row_index': self.row_idx,
            'channel': channel,
            'serial': serial
        })
        
        if success:
            self.status_lbl.config(text="Távoli fut...")
        else:
            self.status_lbl.config(text="Küldési hiba")
            self.start_btn['state'] = tk.NORMAL
            self.stop_btn['state'] = tk.DISABLED
    
    def _cleanup_connections(self):
        """Clean up controller and TC connections (local only)."""
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
        
        if self.is_remote:
            # Send remote command
            self.thread = threading.Thread(target=self._run_optimization_remote, daemon=True)
        else:
            # Run local optimization
            self.thread = threading.Thread(target=self._run_optimization_local, daemon=True)
        
        self.thread.start()
    
    def _on_stop(self):
        """Stop button handler."""
        self.status_lbl.config(text="Leállítás...")
        
        if self.is_remote:
            # Send stop command to peer
            if self.peer_connection is not None and self.peer_connection.is_connected():
                self.peer_connection.send_command('OPTIMIZE_STOP', {
                    'row_index': self.row_idx
                })
        else:
            # Stop local optimization
            self.stop_event.set()
    
    def has_serial(self):
        """Check if row has a serial number entered."""
        if self.is_remote:
            # Remote rows are always "ready" if connected
            return self.peer_connection is not None and self.peer_connection.is_connected()
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
