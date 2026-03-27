"""Command handlers for peer-to-peer communication."""

import logging

logger = logging.getLogger(__name__)


class PeerCommandHandlers:
    """Centralized handlers for peer connection commands."""
    
    def __init__(self, app):
        """
        Initialize command handlers.
        
        Args:
            app: Reference to main App instance
        """
        self.app = app
    
    def register_all(self, peer_connection):
        """Register all command handlers with peer connection."""
        peer_connection.register_command_handler('OPTIMIZE_START', self.handle_optimize_start)
        peer_connection.register_command_handler('OPTIMIZE_STOP', self.handle_optimize_stop)
        peer_connection.register_command_handler('STATUS_UPDATE', self.handle_status_update)
        peer_connection.register_command_handler('PROGRESS_UPDATE', self.handle_progress_update)
        peer_connection.register_command_handler('CAGE_OPTIMIZE_START', self.handle_cage_optimize_start)
        peer_connection.register_command_handler('CAGE_OPTIMIZE_STOP', self.handle_cage_optimize_stop)
        peer_connection.register_command_handler('CAGE_STATUS_UPDATE', self.handle_cage_status_update)
        peer_connection.register_command_handler('CAGE_PROGRESS_UPDATE', self.handle_cage_progress_update)
        peer_connection.register_command_handler('STREAMING_START', self.handle_streaming_start)
        peer_connection.register_command_handler('STREAMING_STOP', self.handle_streaming_stop)
        peer_connection.register_command_handler('TIMESTAMP_BATCH', self.handle_timestamp_batch)
        peer_connection.register_command_handler('COUNTER_DATA', self.handle_counter_data)
        peer_connection.register_command_handler('SAVE_SETTINGS_UPDATE', self.handle_save_settings_update)
        peer_connection.register_command_handler('SAVE_SETTINGS_REQUEST', self.handle_save_settings_request)
        peer_connection.register_command_handler('APPLY_SERVER_TC_DELAYS', self.handle_apply_server_tc_delays)
        logger.info("Registered all peer command handlers")
    
    # Optimization control handlers
    
    def handle_optimize_start(self, data: dict):
        """Handle remote optimization start command."""
        remote_row_idx = data.get('row_index', 0)
        local_row_idx = remote_row_idx - 4  # Map 4-7 to 0-3
        
        if local_row_idx in self.app.optim_rows:
            row = self.app.optim_rows[local_row_idx]
            if not row.is_remote:
                row.channel_box.set(data.get('channel', 1))
                if data.get('serial'):
                    row.serial_var.set(data['serial'])
                row._on_start()
    
    def handle_optimize_stop(self, data: dict):
        """Handle remote optimization stop command."""
        local_row_idx = data.get('row_index', 0) - 4  # Map 4-7 to 0-3
        
        if local_row_idx in self.app.optim_rows:
            row = self.app.optim_rows[local_row_idx]
            if not row.is_remote:
                row._on_stop()
    
    def handle_status_update(self, data: dict):
        """Handle status update from remote peer."""
        remote_row_idx = data.get('row_index', 0) + 4  # Map 0-3 to 4-7
        
        if remote_row_idx in self.app.optim_rows:
            self.app.optim_rows[remote_row_idx].handle_remote_status(data)
    
    def handle_progress_update(self, data: dict):
        """Handle progress update from remote peer."""
        remote_row_idx = data.get('row_index', 0) + 4  # Map 0-3 to 4-7
        
        if remote_row_idx in self.app.optim_rows:
            self.app.optim_rows[remote_row_idx].handle_remote_progress(data)

    def handle_cage_optimize_start(self, data: dict):
        """Handle remote CageRotator optimization start command."""
        rows = getattr(self.app, 'cage_optim_rows', {})
        remote_row_idx = data.get('row_index', 0)
        local_row_idx = remote_row_idx - 2  # Map 2-3 to 0-1

        if local_row_idx in rows:
            row = rows[local_row_idx]
            if not row.is_remote:
                row.channel_box.set(data.get('channel', 1))
                if data.get('serial'):
                    row.serial_var.set(data['serial'])
                row._on_start()

    def handle_cage_optimize_stop(self, data: dict):
        """Handle remote CageRotator optimization stop command."""
        rows = getattr(self.app, 'cage_optim_rows', {})
        local_row_idx = data.get('row_index', 0) - 2  # Map 2-3 to 0-1

        if local_row_idx in rows:
            row = rows[local_row_idx]
            if not row.is_remote:
                row._on_stop()

    def handle_cage_status_update(self, data: dict):
        """Handle CageRotator status update from remote peer."""
        rows = getattr(self.app, 'cage_optim_rows', {})
        remote_row_idx = data.get('row_index', 0) + 2  # Map 0-1 to 2-3

        if remote_row_idx in rows:
            rows[remote_row_idx].handle_remote_status(data)

    def handle_cage_progress_update(self, data: dict):
        """Handle CageRotator progress update from remote peer."""
        rows = getattr(self.app, 'cage_optim_rows', {})
        remote_row_idx = data.get('row_index', 0) + 2  # Map 0-1 to 2-3

        if remote_row_idx in rows:
            rows[remote_row_idx].handle_remote_progress(data)
    
    # Streaming control handlers
    
    def handle_streaming_start(self, data: dict):
        """Handle streaming start command from remote peer."""
        import time
        duration_sec = data.get('duration_sec')
        logger.info(f"Received STREAMING_START command from peer (duration={duration_sec}s)")
        
        # Update duration field in UI to match remote side
        if hasattr(self.app, 'duration_var'):
            if duration_sec:
                self.app.duration_var.set(str(duration_sec))
                logger.info(f"Updated duration UI field to {duration_sec} seconds")
            else:
                self.app.duration_var.set("0")
                logger.info("Updated duration UI field to 0 (unlimited)")
        
        # Get save settings from checkboxes
        local_save_channels = [i+1 for i in range(4) if self.app.local_save_vars[i].get()]
        remote_save_channels = [i+1 for i in range(4) if self.app.remote_save_vars[i].get()] if hasattr(self.app, 'remote_save_vars') and self.app.remote_save_vars else []
        
        # Start local streaming with the same duration
        if hasattr(self.app, 'plot_updater') and self.app.plot_updater:
            self.app.plot_updater.start(
                local_save_channels=local_save_channels,
                remote_save_channels=remote_save_channels,
                recording_duration_sec=duration_sec
            )
        
        # Start timer if duration specified
        if duration_sec:
            self.app.recording_start_time = time.time()
            self.app.recording_duration = duration_sec
            if hasattr(self.app, '_update_recording_timer'):
                self.app._update_recording_timer()
    
    def handle_streaming_stop(self, data: dict):
        """Handle streaming stop command from remote peer."""
        logger.info("Received STREAMING_STOP command from peer - stopping local streaming")
        
        # Clear recording timer
        if hasattr(self.app, 'recording_start_time'):
            self.app.recording_start_time = None
            self.app.recording_duration = None
        if hasattr(self.app, 'recording_timer_label'):
            self.app.recording_timer_label.config(text="")
        
        # Stop local streaming (but keep counter display running)
        if hasattr(self.app, 'plot_updater') and self.app.plot_updater:
            self.app.plot_updater.stop_streaming()
        
        # Auto-transfer files if checkbox is checked (same as _on_stop_streaming)
        if hasattr(self.app, 'auto_transfer_var') and self.app.auto_transfer_var and self.app.auto_transfer_var.get():
            logger.info("Auto-transfer enabled - requesting remote files")
            # Delay slightly to ensure peer has finished writing files
            if hasattr(self.app, 'root'):
                self.app.root.after(1000, self.app._request_remote_files)
    
    # Data exchange handlers
    
    def handle_timestamp_batch(self, data: dict):
        """Handle timestamp batch received from remote peer."""
        try:
            import base64
            import zlib
            import numpy as np
            from gui_components.config import DEBUG_MODE
            
            if not isinstance(data, dict) or 'timestamps' not in data:
                logger.warning("Invalid timestamp batch format")
                return
            
            timestamps = data['timestamps']
            total_received = 0
            
            # Add timestamps to remote buffers
            for channel_str, ts_data in timestamps.items():
                channel = int(channel_str)
                if channel in [1, 2, 3, 4] and isinstance(ts_data, dict):
                    # Decompress binary timestamp data
                    ts_encoded = ts_data.get('data', '')
                    ref_encoded = ts_data.get('ref_data', '')
                    count = ts_data.get('count', 0)
                    
                    if ts_encoded and count > 0:
                        # Decode timestamps: base64 -> decompress -> numpy array
                        ts_compressed = base64.b64decode(ts_encoded)
                        ts_binary = zlib.decompress(ts_compressed)
                        ts_array = np.frombuffer(ts_binary, dtype=np.uint64)
                        
                        # Decode reference seconds if available
                        ref_array = None
                        if ref_encoded:
                            ref_compressed = base64.b64decode(ref_encoded)
                            ref_binary = zlib.decompress(ref_compressed)
                            ref_array = np.frombuffer(ref_binary, dtype=np.uint64)
                        
                        # Add with reference seconds for proper cleanup
                        self.app.plot_updater.remote_buffers[channel].add_timestamps_array(ts_array, ref_array)
                        total_received += len(ts_array)
                        if DEBUG_MODE:
                            logger.debug(f"Ch{channel}: Added {len(ts_array)} remote timestamps, buffer now {len(self.app.plot_updater.remote_buffers[channel])}")
            
            if DEBUG_MODE and total_received > 0:
                logger.debug(f"Received timestamp batch: {total_received} total timestamps from peer")
        except Exception as e:
            logger.error(f"Error handling remote timestamp batch: {e}")
    
    def handle_counter_data(self, data: dict):
        """Handle detector counter data received from remote peer."""
        try:
            counters = data.get('counters', [0, 0, 0, 0])
            if len(counters) == 4:
                self.app.remote_beutes_szamok = counters
        except Exception as e:
            logger.error(f"Error handling remote counter data: {e}")
    
    # Save settings handlers
    
    def handle_save_settings_update(self, data: dict):
        """Handle save settings update from remote peer."""
        try:
            save_channels = data.get('save_channels', [])
            logger.info(f"Received save settings from peer: {save_channels}")
            
            # Update remote checkboxes to reflect peer's settings
            if hasattr(self.app, 'remote_save_vars'):
                for i in range(4):
                    channel = i + 1
                    should_save = channel in save_channels
                    self.app.remote_save_vars[i].set(should_save)
        except Exception as e:
            logger.error(f"Error handling save settings update: {e}")
    
    def handle_save_settings_request(self, data: dict):
        """Handle request from peer to change our local save settings."""
        try:
            save_channels = data.get('save_channels', [])
            logger.info(f"Peer requested we update our save settings to: {save_channels}")
            
            # Update our local checkboxes based on peer's request
            if hasattr(self.app, 'local_save_vars'):
                for i in range(4):
                    channel = i + 1
                    should_save = channel in save_channels
                    self.app.local_save_vars[i].set(should_save)
                
                # After updating, send back confirmation
                self.app._on_local_save_changed()
        except Exception as e:
            logger.error(f"Error handling save settings request: {e}")

    def handle_apply_server_tc_delays(self, data: dict):
        """Handle request to apply server-side TC delay settings."""
        try:
            # Only server side (Wigner/computer_a) should execute this request.
            if getattr(self.app, 'computer_role', None) != 'computer_a':
                logger.warning("Ignoring APPLY_SERVER_TC_DELAYS on non-server role")
                return

            from mock_time_controller import is_mock_controller
            if not hasattr(self.app, 'tc') or is_mock_controller(self.app.tc):
                logger.warning("Cannot apply server TC delays: TC unavailable or mock mode")
                return

            import importlib
            import gui_components.config as _cfg_mod
            from utils.common import zmq_exec

            importlib.reload(_cfg_mod)
            payload_delays = data.get('wigner_delays', {}) if isinstance(data, dict) else {}
            payload_enabled = data.get('wigner_enabled', {}) if isinstance(data, dict) else {}

            def _get_delay(name: str, cfg_default: int) -> int:
                raw = payload_delays.get(name, cfg_default)
                try:
                    return int(raw)
                except (TypeError, ValueError):
                    return int(cfg_default)

            delay_commands = [
                ("delay1", _get_delay("delay1", _cfg_mod.TCWIGNER_DELAY1_VALUE)),
                ("delay2", _get_delay("delay2", _cfg_mod.TCWIGNER_DELAY2_VALUE)),
                ("delay3", _get_delay("delay3", _cfg_mod.TCWIGNER_DELAY3_VALUE)),
                ("delay4", _get_delay("delay4", _cfg_mod.TCWIGNER_DELAY4_VALUE)),
            ]

            for cmd_name, cmd_value in delay_commands:
                if isinstance(payload_enabled, dict) and cmd_name in payload_enabled:
                    if not bool(payload_enabled.get(cmd_name)):
                        continue
                tc_cmd = f"{cmd_name}:value {cmd_value}"
                zmq_exec(self.app.tc, tc_cmd)
                logger.info("Applied server TC command from peer request: %s", tc_cmd)

        except Exception as e:
            logger.error(f"Error handling APPLY_SERVER_TC_DELAYS: {e}")
