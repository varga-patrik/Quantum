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
        peer_connection.register_command_handler('STREAMING_START', self.handle_streaming_start)
        peer_connection.register_command_handler('STREAMING_STOP', self.handle_streaming_stop)
        peer_connection.register_command_handler('TIMESTAMP_BATCH', self.handle_timestamp_batch)
        peer_connection.register_command_handler('COUNTER_DATA', self.handle_counter_data)
        peer_connection.register_command_handler('SAVE_SETTINGS_UPDATE', self.handle_save_settings_update)
        peer_connection.register_command_handler('SAVE_SETTINGS_REQUEST', self.handle_save_settings_request)
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
    
    # Streaming control handlers
    
    def handle_streaming_start(self, data: dict):
        """Handle streaming start command from remote peer."""
        import time
        duration_sec = data.get('duration_sec')
        # Note: local_save_channels from sender's perspective = this side should save those channels
        # remote_save_channels from sender's perspective = not used on this side
        local_save_channels = data.get('local_save_channels', [])
        logger.info(f"Received STREAMING_START command from peer (duration={duration_sec}s, save_channels={local_save_channels})")
        
        if hasattr(self.app, 'plot_updater') and self.app.plot_updater:
            # Start local streaming when peer requests it with same save settings
            self.app.plot_updater.start(
                local_save_channels=local_save_channels,
                recording_duration_sec=duration_sec
            )
        
        # Start timer if duration specified
        if duration_sec:
            self.app.recording_start_time = time.time()
            self.app.recording_duration = duration_sec
            self.app._update_recording_timer()
    
    def handle_streaming_stop(self, data: dict):
        """Handle streaming stop command from remote peer."""
        logger.info("Received STREAMING_STOP command from peer - stopping local streaming")
        if hasattr(self.app, 'plot_updater') and self.app.plot_updater:
            # Stop local streaming when peer requests it (but keep counter display running)
            self.app.plot_updater.stop_streaming()
    
    # Data exchange handlers
    
    def handle_timestamp_batch(self, data: dict):
        """Handle timestamp batch received from remote peer."""
        try:
            import base64
            import zlib
            import numpy as np
            
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
                    encoded = ts_data.get('data', '')
                    count = ts_data.get('count', 0)
                    
                    if encoded and count > 0:
                        # Decode base64 -> decompress -> convert to numpy array
                        compressed = base64.b64decode(encoded)
                        binary = zlib.decompress(compressed)
                        ts_array = np.frombuffer(binary, dtype=np.uint64)
                        
                        self.app.plot_updater.remote_buffers[channel].add_timestamps_array(ts_array)
                        total_received += len(ts_array)
            
            logger.debug(f"Received timestamp batch: {total_received} total timestamps")
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
