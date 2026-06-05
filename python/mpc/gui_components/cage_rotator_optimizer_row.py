"""Cage rotator optimizer row with local and remote control support."""

import threading
import time
import tkinter as tk
from tkinter import ttk

from .helpers import format_number
from device_hander import CageRotatorController, TimeController as TCWrapper


def _clip_angle(angle_deg: float, lo: float, hi: float) -> float:
    return min(max(float(angle_deg), lo), hi)


def _measure_counts(tc, channel: int, samples: int = 2, inter_sample_sleep: float = 0.02) -> float:
    acc = 0.0
    count = max(1, int(samples))
    for i in range(count):
        try:
            value = tc.query_counter(channel)
        except Exception:
            value = 0
        acc += float(value)
        if i + 1 < count and inter_sample_sleep > 0:
            time.sleep(inter_sample_sleep)
    return acc / count


def _measure_visibility(tc, channel_a: int, channel_b: int, samples: int = 2, inter_sample_sleep: float = 0.02) -> float:
    """Measure visibility between two TC channels using averaged counts.

    Visibility defined as (max - min) / (max + min). Returns 0.0 if sum is zero.
    """
    def _sum_spec(spec):
        if spec is None:
            return 0.0
        if isinstance(spec, (list, tuple)):
            s = 0.0
            for ch in spec:
                try:
                    s += _measure_counts(tc, int(ch), samples, inter_sample_sleep)
                except Exception:
                    pass
            return s
        try:
            return _measure_counts(tc, int(spec), samples, inter_sample_sleep)
        except Exception:
            return 0.0

    a = _sum_spec(channel_a)
    b = _sum_spec(channel_b)
    s = a + b
    if s <= 0:
        return 0.0
    return abs(a - b) / s


def _parse_channel_spec(spec: str):
    """Parse a comma-separated channel spec into a list of ints.

    Examples: '1' -> [1], '1,2' -> [1,2], '' -> []. Ignores invalid entries.
    """
    if spec is None:
        return []
    s = str(spec).strip()
    if not s:
        return []
    parts = [p.strip() for p in s.split(',') if p.strip()]
    out = []
    for p in parts:
        try:
            out.append(int(p))
        except Exception:
            pass
    return out


def optimize_cage_rotator(
    controller,
    tc,
    channel_a: int,
    channel_b: int,
    *,
    angle_min: float = 0.0,
    angle_max: float = 360.0,
    measure_samples: int = 2,
    dwell_after_move_s: float = 0.05,
    fd_delta_deg: float = 2.0,
    lr_deg: float = 6.0,
    momentum_beta: float = 0.8,
    max_iters: int = 80,
    patience: int = 10,
    progress=None,
    stop_event=None,
):
    """Gradient-ascent optimizer for one cage rotator angle maximizing visibility.

    The objective is the visibility computed from two TC channels.
    """

    def move_to(angle: float):
        controller.move_to(angle)
        if dwell_after_move_s > 0:
            time.sleep(dwell_after_move_s)

    def eval_at(angle: float) -> float:
        a = _clip_angle(angle, angle_min, angle_max)
        move_to(a)
        return _measure_visibility(tc, channel_a=channel_a, channel_b=channel_b, samples=measure_samples)

    x = _clip_angle(controller.get_position(), angle_min, angle_max)
    fx = eval_at(x)
    best_x = x
    best_fx = fx
    velocity = 0.0
    no_improve = 0

    if progress is not None:
        try:
            progress(0, x, fx, best_x, best_fx)
        except Exception:
            pass

    for it in range(1, int(max_iters) + 1):
        if stop_event is not None and getattr(stop_event, "is_set", lambda: False)():
            break

        x_plus = _clip_angle(x + fd_delta_deg, angle_min, angle_max)
        x_minus = _clip_angle(x - fd_delta_deg, angle_min, angle_max)

        f_plus = eval_at(x_plus)
        f_minus = eval_at(x_minus)

        move_to(x)
        grad = (f_plus - f_minus) / max(1e-6, (x_plus - x_minus))

        velocity = momentum_beta * velocity + (1.0 - momentum_beta) * grad
        direction = 0.0
        if velocity > 0:
            direction = 1.0
        elif velocity < 0:
            direction = -1.0

        x_new = _clip_angle(x + direction * lr_deg, angle_min, angle_max)
        fx_new = eval_at(x_new)

        if fx_new > fx:
            x = x_new
            fx = fx_new
            if fx_new > best_fx:
                best_x = x_new
                best_fx = fx_new
            no_improve = 0
        else:
            lr_deg = max(0.5, lr_deg * 0.7)
            no_improve += 1

        if progress is not None:
            try:
                progress(it, x, fx, best_x, best_fx)
            except Exception:
                pass

        if no_improve >= int(patience):
            break

    move_to(best_x)
    return best_x, best_fx


class CageRotatorOptimizerRow:
    """Optimizer row for a single CageRotator with optional remote control."""

    def __init__(
        self,
        frame,
        row_idx,
        tc_address,
        action_color,
        is_remote: bool = False,
        peer_connection=None,
        default_serial=None,
        default_channel=1,
    ):
        self.frame = frame
        self.row_idx = row_idx
        self.tc_address = tc_address
        self.action_color = action_color
        self.is_remote = is_remote
        self.peer_connection = peer_connection

        self.controller = None
        self.tc = None
        self.thread = None
        self.stop_event = threading.Event()
        self.started_set = False
        self.last_iter = 0

        self._build_widgets(default_serial, default_channel)

    def _build_widgets(self, default_serial, default_channel):
        row = 2 + self.row_idx

        self.serial_var = tk.StringVar(value=default_serial or "")
        self.serial_entry = tk.Entry(self.frame, textvariable=self.serial_var, width=14)
        self.serial_entry.grid(row=row, column=0, padx=3)
        if self.is_remote:
            self.serial_entry.config(background="#E3F2FD")

        # channel list entries (comma-separated allowed), A and B sides
        self.channel_entry_a = tk.Entry(self.frame, width=8)
        self.channel_entry_a.grid(row=row, column=1)
        self.channel_entry_b = tk.Entry(self.frame, width=8)
        self.channel_entry_b.grid(row=row, column=2)
        # set defaults
        try:
            self.channel_entry_a.delete(0, tk.END)
            self.channel_entry_a.insert(0, str(int(default_channel)))
        except Exception:
            self.channel_entry_a.insert(0, "1")
        default_secondary = (default_channel % 4) + 1 if isinstance(default_channel, int) else 2
        try:
            self.channel_entry_b.delete(0, tk.END)
            self.channel_entry_b.insert(0, str(int(default_secondary)))
        except Exception:
            self.channel_entry_b.insert(0, "2")

        self.start_angle_lbl = tk.Label(self.frame, text="-", width=10)
        self.start_value_lbl = tk.Label(self.frame, text="-", width=10)
        self.angle_lbl = tk.Label(self.frame, text="-", width=10)
        self.value_lbl = tk.Label(self.frame, text="-", width=10)
        self.best_angle_lbl = tk.Label(self.frame, text="-", width=10)
        self.best_value_lbl = tk.Label(self.frame, text="-", width=10)
        self.status_lbl = tk.Label(self.frame, text="Idle", width=18)

        if self.is_remote:
            self.status_lbl.config(foreground="blue")

        # shift label columns right by one to accommodate second channel selector
        self.start_angle_lbl.grid(row=row, column=3)
        self.start_value_lbl.grid(row=row, column=4)
        self.angle_lbl.grid(row=row, column=5)
        self.value_lbl.grid(row=row, column=6)
        self.best_angle_lbl.grid(row=row, column=7)
        self.best_value_lbl.grid(row=row, column=8)
        self.status_lbl.grid(row=row, column=9)

        self.start_btn = tk.Button(
            self.frame,
            text="Optimize",
            background=self.action_color,
            width=12,
            command=self._on_start,
        )
        self.stop_btn = tk.Button(
            self.frame,
            text="Stop",
            background=self.action_color,
            width=8,
            state=tk.DISABLED,
            command=self._on_stop,
        )

        btn_frame = tk.Frame(self.frame)
        self.start_btn.pack(in_=btn_frame, side=tk.LEFT)
        self.stop_btn.pack(in_=btn_frame, side=tk.LEFT, padx=4)
        btn_frame.grid(row=row, column=10)

    def _fmt_angle(self, value: float) -> str:
        try:
            return f"{float(value):.2f}"
        except Exception:
            return "-"

    def _fmt_visibility(self, value: float) -> str:
        try:
            return f"{float(value):.3f}"
        except Exception:
            return "-"

    def _on_progress(self, it, angle, value, best_angle, best_value):
        try:
            if not self.started_set and it == 0:
                self.start_angle_lbl.config(text=self._fmt_angle(angle))
                self.start_value_lbl.config(text=self._fmt_visibility(value))
                self.started_set = True

            self.angle_lbl.config(text=self._fmt_angle(angle))
            self.value_lbl.config(text=self._fmt_visibility(value))
            self.best_angle_lbl.config(text=self._fmt_angle(best_angle))
            self.best_value_lbl.config(text=self._fmt_visibility(best_value))
            self.status_lbl.config(text=f"Iter {it}")
            self.last_iter = it

            if not self.is_remote and self.peer_connection and self.peer_connection.is_connected():
                self.peer_connection.send_command(
                    "CAGE_PROGRESS_UPDATE",
                    {
                        "row_index": self.row_idx,
                        "iteration": it,
                        "angle": float(angle),
                        "value": float(value),
                        "best_angle": float(best_angle),
                        "best_value": float(best_value),
                    },
                )
        except Exception:
            pass

    def handle_remote_progress(self, data: dict):
        try:
            self._on_progress(
                data.get("iteration", 0),
                data.get("angle", 0.0),
                data.get("value", 0),
                data.get("best_angle", 0.0),
                data.get("best_value", 0),
            )
        except Exception:
            pass

    def handle_remote_status(self, data: dict):
        try:
            status = data.get("status", "Unknown")
            self.status_lbl.config(text=status)
            if status in ["Kész", "Hiba", "Idle", "Leállítva"]:
                self.start_btn["state"] = tk.NORMAL
                self.stop_btn["state"] = tk.DISABLED
        except Exception:
            pass

    def _send_status_to_peer(self, status: str):
        if self.peer_connection and self.peer_connection.is_connected():
            self.peer_connection.send_command(
                "CAGE_STATUS_UPDATE",
                {
                    "row_index": self.row_idx,
                    "status": status,
                },
            )

    def _run_optimization_local(self):
        self.status_lbl.config(text="Csatlakozás...")
        self._send_status_to_peer("Csatlakozás...")

        serial = self.serial_var.get().strip()
        # parse channel lists (comma-separated allowed)
        try:
            ch_spec_a = self.channel_entry_a.get()
        except Exception:
            ch_spec_a = ""
        channel_a = _parse_channel_spec(ch_spec_a)
        if not channel_a:
            channel_a = [1]

        try:
            ch_spec_b = self.channel_entry_b.get()
        except Exception:
            ch_spec_b = ""
        channel_b = _parse_channel_spec(ch_spec_b)
        if not channel_b:
            # default to next channel if nothing provided
            channel_b = [((channel_a[0] if channel_a else 1) % 4) + 1]

        if not serial:
            self.status_lbl.config(text="Hiányzó serial")
            self._send_status_to_peer("Hiányzó serial")
            self.start_btn["state"] = tk.NORMAL
            self.stop_btn["state"] = tk.DISABLED
            return

        try:
            self.controller = CageRotatorController(serial).connect()
        except Exception:
            self.status_lbl.config(text="Rotator hiba")
            self._send_status_to_peer("Rotator hiba")
            self.start_btn["state"] = tk.NORMAL
            self.stop_btn["state"] = tk.DISABLED
            return

        try:
            self.tc = TCWrapper(self.tc_address).connect()
        except Exception as e:
            self.status_lbl.config(text=f"TC hiba: {str(e)[:20]}")
            self._send_status_to_peer(f"TC hiba: {str(e)[:20]}")
            try:
                self.controller.disconnect()
            except Exception:
                pass
            self.controller = None
            self.start_btn["state"] = tk.NORMAL
            self.stop_btn["state"] = tk.DISABLED
            return

        self.status_lbl.config(text="Fut...")
        self._send_status_to_peer("Fut...")
        self.stop_event.clear()

        try:
            optimize_cage_rotator(
                controller=self.controller,
                tc=self.tc,
                channel_a=channel_a,
                channel_b=channel_b,
                angle_min=0.0,
                angle_max=360.0,
                measure_samples=2,
                dwell_after_move_s=0.05,
                fd_delta_deg=2.0,
                lr_deg=6.0,
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
        if self.peer_connection is None or not self.peer_connection.is_connected():
            self.status_lbl.config(text="Nincs kapcsolat")
            self.start_btn["state"] = tk.NORMAL
            self.stop_btn["state"] = tk.DISABLED
            return

        serial = self.serial_var.get().strip()
        # parse channel lists for remote command
        try:
            ch_spec_a = self.channel_entry_a.get()
        except Exception:
            ch_spec_a = ""
        channel_a = _parse_channel_spec(ch_spec_a)
        if not channel_a:
            channel_a = [1]

        try:
            ch_spec_b = self.channel_entry_b.get()
        except Exception:
            ch_spec_b = ""
        channel_b = _parse_channel_spec(ch_spec_b)
        if not channel_b:
            channel_b = [((channel_a[0] if channel_a else 1) % 4) + 1]

        success = self.peer_connection.send_command(
            "CAGE_OPTIMIZE_START",
            {
                "row_index": self.row_idx,
                "channel_a": channel_a,
                "channel_b": channel_b,
                "serial": serial,
            },
        )

        if success:
            self.status_lbl.config(text="Távoli fut...")
        else:
            self.status_lbl.config(text="Küldési hiba")
            self.start_btn["state"] = tk.NORMAL
            self.stop_btn["state"] = tk.DISABLED

    def _cleanup_connections(self):
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

        self.start_btn["state"] = tk.NORMAL
        self.stop_btn["state"] = tk.DISABLED

    def _on_start(self):
        self.start_btn["state"] = tk.DISABLED
        self.stop_btn["state"] = tk.NORMAL
        self.started_set = False

        if self.is_remote:
            self.thread = threading.Thread(target=self._run_optimization_remote, daemon=True)
        else:
            self.thread = threading.Thread(target=self._run_optimization_local, daemon=True)
        self.thread.start()

    def _on_stop(self):
        self.status_lbl.config(text="Leállítás...")
        if self.is_remote:
            if self.peer_connection is not None and self.peer_connection.is_connected():
                self.peer_connection.send_command(
                    "CAGE_OPTIMIZE_STOP",
                    {
                        "row_index": self.row_idx,
                    },
                )
        else:
            self.stop_event.set()

    def has_serial(self):
        if self.is_remote:
            return self.peer_connection is not None and self.peer_connection.is_connected()
        return bool(self.serial_var.get().strip())

    def cleanup(self):
        try:
            self.stop_event.set()
        except Exception:
            pass
        self._cleanup_connections()
