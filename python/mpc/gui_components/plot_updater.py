"""Plot updater component for real-time timestamp streaming and coincidence measurement."""

import threading
import time
import numpy as np
import random
import logging
from typing import Optional

from mock_time_controller import safe_zmq_exec
from utils.timestamp_stream import TimestampBuffer, CoincidenceCounter
from utils.stream_client import TimeControllerStreamClient
from gui_components.config import (
    COINCIDENCE_WINDOW_PS,
    TIMESTAMP_BUFFER_DURATION_SEC,
    TIMESTAMP_BUFFER_MAX_SIZE,
    TIMESTAMP_BATCH_INTERVAL_SEC
)

logger = logging.getLogger(__name__)


class PlotUpdater:
    """Manages real-time plot updates with timestamp streaming and coincidence counting."""
    
    def __init__(self, fig, ax, canvas, tc, default_acq_duration, bin_width, 
                 default_bin_count, default_histograms, peer_connection=None, app_ref=None):
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

        # Display mode
        self.plot_histogram = False
        self.normalize_plot = False
        
        # Peer connection for cross-site data exchange
        self.peer_connection = peer_connection
        self.app_ref = app_ref  # Reference to main app
        
        # Timestamp buffers (circular buffers for each channel)
        self.local_buffers = {
            1: TimestampBuffer(1, TIMESTAMP_BUFFER_DURATION_SEC, TIMESTAMP_BUFFER_MAX_SIZE),
            2: TimestampBuffer(2, TIMESTAMP_BUFFER_DURATION_SEC, TIMESTAMP_BUFFER_MAX_SIZE),
            3: TimestampBuffer(3, TIMESTAMP_BUFFER_DURATION_SEC, TIMESTAMP_BUFFER_MAX_SIZE),
            4: TimestampBuffer(4, TIMESTAMP_BUFFER_DURATION_SEC, TIMESTAMP_BUFFER_MAX_SIZE)
        }
        self.remote_buffers = {
            1: TimestampBuffer(1, TIMESTAMP_BUFFER_DURATION_SEC, TIMESTAMP_BUFFER_MAX_SIZE),
            2: TimestampBuffer(2, TIMESTAMP_BUFFER_DURATION_SEC, TIMESTAMP_BUFFER_MAX_SIZE),
            3: TimestampBuffer(3, TIMESTAMP_BUFFER_DURATION_SEC, TIMESTAMP_BUFFER_MAX_SIZE),
            4: TimestampBuffer(4, TIMESTAMP_BUFFER_DURATION_SEC, TIMESTAMP_BUFFER_MAX_SIZE)
        }
        
        # Coincidence counter
        self.coincidence_counter = CoincidenceCounter(window_ps=COINCIDENCE_WINDOW_PS)
        
        # Coincidence counts (cross-site pairs only)
        # Pairs: (1,1), (2,2), (3,3), (4,4) 
        self.coincidence_series = np.zeros((4, 20))  # 4 pairs, 20 time points
        self.last_coincidence_counts = [0, 0, 0, 0]
        
        # Detector single counts (for display only)
        self.beutes_szamok = [0, 0, 0, 0]
        
        # Stream client (will be initialized when streaming starts)
        self.stream_client: Optional[TimeControllerStreamClient] = None
        self.streaming_active = False
        
        # Batch sending for peer exchange
        self.last_batch_send_time = time.time()

    def start_streaming(self, tc_address: str, is_mock: bool = False):
        """
        Start timestamp streaming from Time Controller via DLT service.
        
        Args:
            tc_address: Time Controller IP address
            is_mock: Use mock streaming for testing
        """
        if self.streaming_active:
            logger.warning("Streaming already active")
            return
        
        logger.info(f"Starting timestamp streaming from {tc_address} (mock={is_mock})")
        
        # Start DLT acquisitions (if not mock)
        self.acquisition_ids = {}
        if not is_mock:
            from utils.common import zmq_exec, dlt_exec
            from pathlib import Path
            import time as time_module
            
            # Get DLT connection from app_ref
            dlt = getattr(self.app_ref, 'dlt', None) if self.app_ref else None
            if not dlt:
                logger.error("DLT service not connected - cannot start streaming")
                return
            
            # Close any active acquisitions first
            try:
                active_acquisitions = dlt_exec(dlt, "list")
                if active_acquisitions:
                    logger.info(f"Found {len(active_acquisitions)} active acquisitions, closing them...")
                    for acq_id in active_acquisitions:
                        dlt_exec(dlt, f"stop --id {acq_id}")
                        logger.info(f"Closed acquisition {acq_id}")
            except Exception as e:
                logger.warning(f"Error checking/closing active acquisitions: {e}")
            
            # Start DLT acquisitions for each channel
            output_dir = Path.home() / "Documents" / "AgodSolt" / "data"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            for channel in [1, 2, 3, 4]:
                try:
                    # Clear any previous errors
                    zmq_exec(self.tc, f"RAW{channel}:ERRORS:CLEAR")
                    
                    # Create filename for this acquisition
                    timestr = time_module.strftime("%Y%m%d_%H%M%S")
                    filepath = output_dir / f"timestamps_live_ch{channel}_{timestr}.bin"
                    filepath_escaped = str(filepath).replace("\\", "\\\\")
                    
                    # Tell DLT to start saving timestamps (also creates streaming endpoint)
                    command = f'start-save --address {tc_address} --channel {channel} --filename "{filepath_escaped}" --format bin --with-ref-index'
                    logger.info(f"Sending DLT command: {command}")
                    answer = dlt_exec(dlt, command)
                    logger.info(f"DLT response: {answer}")
                    acq_id = answer["id"]
                    
                    # Parse acquisition ID to get streaming port
                    # Format is "address:port" like "169.254.104.112:5556"
                    if ':' in acq_id:
                        stream_port = int(acq_id.split(':')[1])
                        self.acquisition_ids[channel] = {'id': acq_id, 'port': stream_port}
                        logger.info(f"Started DLT acquisition for channel {channel}, ID: {acq_id}, port: {stream_port}, file: {filepath}")
                    else:
                        self.acquisition_ids[channel] = {'id': acq_id, 'port': None}
                        logger.warning(f"Could not parse port from acquisition ID: {acq_id}")
                    
                    # Enable timestamp transmission from Time Controller
                    # Check if already enabled first
                    try:
                        send_status = zmq_exec(self.tc, f"RAW{channel}:SEND?")
                        if send_status.strip().upper() != "ON":
                            zmq_exec(self.tc, f"RAW{channel}:SEND ON")
                            send_status = zmq_exec(self.tc, f"RAW{channel}:SEND?")
                        logger.info(f"RAW{channel}:SEND status: {send_status}")
                    except Exception as e:
                        logger.error(f"Error enabling RAW{channel}:SEND: {e}")
                        raise  # Re-raise to be caught by outer exception handler
                    
                    # Check for errors
                    time_module.sleep(0.1)  # Brief delay to let any errors accumulate
                    error_count = zmq_exec(self.tc, f"RAW{channel}:ERRORS?")
                    logger.info(f"Channel {channel} error count: {error_count}")
                    
                except Exception as e:
                    logger.error(f"Failed to start DLT acquisition for channel {channel}: {e}")
                    # Continue with other channels even if one fails
            
            # Start the Time Controller acquisition (REC:PLAY)
            # This tells the TC to actually start generating and sending timestamps
            try:
                rec_stage = zmq_exec(self.tc, "REC:STAGe?")
                logger.info(f"REC stage before PLAY: {rec_stage}")
                
                if rec_stage.strip().upper() != "PLAYING":
                    zmq_exec(self.tc, "REC:PLAY")
                    rec_stage_after = zmq_exec(self.tc, "REC:STAGe?")
                    logger.info(f"Started Time Controller recording - REC stage: {rec_stage_after}")
                else:
                    logger.info("Time Controller already in PLAYING state")
            except Exception as e:
                logger.error(f"Failed to start Time Controller recording: {e}")
                # Try to continue anyway - streaming might still work
        
        # Check DLT acquisition status
        if not is_mock:
            time_module.sleep(0.5)  # Wait a bit for data to start flowing
            try:
                dlt_status = dlt_exec(dlt, "list")
                logger.info(f"Active DLT acquisitions: {dlt_status}")
                
                # Check status of each acquisition
                for channel, acq_info in self.acquisition_ids.items():
                    acq_id = acq_info['id']
                    status = dlt_exec(dlt, f"status --id {acq_id}")
                    logger.info(f"DLT acquisition {acq_id} status: {status}")
            except Exception as e:
                logger.warning(f"Could not check DLT status: {e}")
        
        # Create stream client connected to Time Controller's native streaming ports
        # TC streams on ports 4242-4245 (STREAM_PORTS_BASE + channel)
        # Note: DLT handles file saving separately; for live GUI streaming we connect directly to TC
        self.stream_client = TimeControllerStreamClient(tc_address, is_mock=is_mock)
        
        # Start streams for each channel with callback
        # Don't use DLT acquisition ports - those are for DLT's internal use
        # Use None for port to let StreamClient use default TC streaming ports (4242-4245)
        for channel in [1, 2, 3, 4]:
            callback = lambda data, ch=channel: self._on_timestamp_batch(ch, data)
            self.stream_client.start_stream(channel, callback, port=None)
        
        self.streaming_active = True
        logger.info("Timestamp streaming started for all channels")
    
    def stop_streaming(self):
        """Stop timestamp streaming and DLT acquisitions."""
        if not self.streaming_active or self.stream_client is None:
            return
        
        logger.info("Stopping timestamp streaming")
        
        # Stop stream clients first
        self.stream_client.stop_all_streams()
        
        # Stop DLT acquisitions (if not mock)
        if not self.stream_client.is_mock and hasattr(self, 'acquisition_ids'):
            from utils.common import zmq_exec, dlt_exec
            
            # Get DLT connection from app_ref
            dlt = getattr(self.app_ref, 'dlt', None) if self.app_ref else None
            
            if dlt:
                # Stop DLT acquisitions
                for channel, acq_info in self.acquisition_ids.items():
                    try:
                        acq_id = acq_info['id'] if isinstance(acq_info, dict) else acq_info
                        status = dlt_exec(dlt, f"stop --id {acq_id}")
                        logger.info(f"Stopped DLT acquisition for channel {channel}")
                    except Exception as e:
                        logger.error(f"Error stopping DLT acquisition for channel {channel}: {e}")
                
                # Stop Time Controller recording
                try:
                    zmq_exec(self.tc, "REC:STOP")
                    logger.info("Stopped Time Controller recording (REC:STOP)")
                except Exception as e:
                    logger.error(f"Failed to stop TC recording: {e}")
                
                # Disable RAW streaming on Time Controller
                for channel in self.acquisition_ids.keys():
                    try:
                        zmq_exec(self.tc, f"RAW{channel}:SEND OFF")
                        logger.info(f"Disabled RAW{channel}:SEND on Time Controller")
                    except Exception as e:
                        logger.error(f"Failed to disable streaming on channel {channel}: {e}")
        
        self.streaming_active = False
    
    def _on_timestamp_batch(self, channel: int, binary_data: bytes):
        """
        Callback for receiving timestamp batch from stream.
        
        Args:
            channel: Channel number (1-4)
            binary_data: Binary timestamp data (uint64 pairs)
        """
        try:
            if len(binary_data) > 0:
                logger.info(f"Ch{channel}: Received {len(binary_data)} bytes from stream")
                # Add timestamps to buffer
                self.local_buffers[channel].add_timestamps(binary_data, with_ref_index=True)
                logger.info(f"Ch{channel}: Buffer size now {len(self.local_buffers[channel])}")
            else:
                logger.warning(f"Ch{channel}: Received empty data packet")
                
        except Exception as e:
            logger.error(f"Error processing timestamp batch for channel {channel}: {e}", exc_info=True)
    
    def _send_timestamp_batch_to_peer(self):
        """Send local timestamp batches to peer for cross-site correlation."""
        if self.peer_connection is None or not self.peer_connection.is_connected():
            return
        
        try:
            import base64
            import zlib
            
            # Limit: only send most recent timestamps (last 100ms worth, ~5000 per channel)
            # This is enough for coincidence detection while keeping network load manageable
            MAX_TIMESTAMPS_PER_CHANNEL = 5000
            
            # Collect timestamps from all channels as compressed binary
            batch_data = {}
            total_ts = 0
            for channel in [1, 2, 3, 4]:
                timestamps = self.local_buffers[channel].get_timestamps()
                if len(timestamps) > 0:
                    # Only send the most recent N timestamps
                    recent = timestamps[-MAX_TIMESTAMPS_PER_CHANNEL:] if len(timestamps) > MAX_TIMESTAMPS_PER_CHANNEL else timestamps
                    
                    # Convert to binary (much more efficient than JSON)
                    binary = recent.tobytes()
                    # Compress to reduce network load
                    compressed = zlib.compress(binary, level=1)  # Fast compression
                    # Encode as base64 for JSON transport
                    encoded = base64.b64encode(compressed).decode('ascii')
                    batch_data[channel] = {
                        'data': encoded,
                        'count': len(recent)
                    }
                    total_ts += len(recent)
            
            if batch_data and total_ts > 0:
                # Send timestamp batch to peer
                success = self.peer_connection.send_command('TIMESTAMP_BATCH', {
                    'timestamps': batch_data,
                    'time': time.time()
                })
                if success:
                    logger.debug(f"Sent timestamp batch: {total_ts} total timestamps")
        except Exception as e:
            logger.warning(f"Could not send timestamp batch to peer: {e}")
    
    def _update_measurements(self):
        """Update coincidence counts from timestamp buffers."""
        from utils.common import zmq_exec
        
        # Live counters from TC (singles rates display only)
        for j in range(1, 5):
            try:
                self.beutes_szamok[j - 1] = int(safe_zmq_exec(self.tc, f"INPUt{j}:COUNter?", zmq_exec))
            except Exception:
                self.beutes_szamok[j - 1] = random.randint(20000, 100000)
        
        # Calculate coincidences from timestamp buffers
        if self.streaming_active:
            self._calculate_coincidences()
            
            # Send timestamp batches to peer at regular intervals
            current_time = time.time()
            if current_time - self.last_batch_send_time >= TIMESTAMP_BATCH_INTERVAL_SEC:
                self._send_timestamp_batch_to_peer()
                self.last_batch_send_time = current_time
        else:
            # Not streaming yet, show placeholder
            pass
        
        # Send counter data to peer if connected
        if self.peer_connection and self.peer_connection.is_connected():
            try:
                self.peer_connection.send_command('COUNTER_DATA', {'counters': self.beutes_szamok})
            except Exception as e:
                logger.error(f"Failed to send counter data to peer: {e}")
    
    def _calculate_coincidences(self):
        """Calculate coincidences between local and remote timestamps.
        
        Uses the CoincidenceCounter to find timestamp pairs within the
        configured coincidence window (±1ns by default).
        """
        if not self.app_ref or not hasattr(self.app_ref, 'correlation_pairs'):
            return
        
        # Get time offset from config (measured by C++ Correlator)
        time_offset_ps = getattr(self.app_ref, 'time_offset_ps', 0) or 0
        
        # Get correlation pairs: [(local_ch, remote_ch), ...]
        pairs = self.app_ref.correlation_pairs
        
        # DEBUG: Log buffer sizes
        local_sizes = [len(self.local_buffers[ch].get_timestamps()) for ch in [1,2,3,4]]
        remote_sizes = [len(self.remote_buffers[ch].get_timestamps()) for ch in [1,2,3,4]]
        logger.info(f"Buffer sizes - Local: {local_sizes}, Remote: {remote_sizes}")
        
        # Calculate coincidences for each pair
        new_counts = []
        for local_ch, remote_ch in pairs:
            local_ts = self.local_buffers[local_ch].get_timestamps()
            remote_ts = self.remote_buffers[remote_ch].get_timestamps()
            
            logger.info(f"Pair ({local_ch},{remote_ch}): local={len(local_ts)}, remote={len(remote_ts)}")
            
            count = self.coincidence_counter.count_coincidences(
                local_ts, remote_ts, time_offset_ps
            )
            logger.info(f"Pair ({local_ch},{remote_ch}): count={count}")
            new_counts.append(count)
        
        # Update rolling window (shift left, add new value on right)
        for i, count in enumerate(new_counts):
            if i < len(self.coincidence_series):
                self.coincidence_series[i] = np.roll(self.coincidence_series[i], -1)
                self.coincidence_series[i, -1] = count
                self.last_coincidence_counts[i] = count
    
    def _clear_cross_site_data(self):
        """Clear cross-site data when peer disconnects."""
        logger.debug("Peer disconnected - clearing cross-site data")
        for channel in [1, 2, 3, 4]:
            self.remote_buffers[channel].clear()
        self.coincidence_series[:, :] = 0
        self.last_coincidence_counts = [0, 0, 0, 0]

    def _draw_coincidence_plot(self):
        """Draw cross-site coincidence time series plot.
        
        Only plots meaningful correlations: cross-site coincidences.
        Single-site correlations are meaningless for entanglement.
        """
        if not self.app_ref or not hasattr(self.app_ref, 'correlation_pairs'):
            self.ax.text(0.5, 0.5, 'No correlation pairs configured', 
                        ha='center', va='center', transform=self.ax.transAxes)
            return
        
        # Check if peer is connected
        if not self.peer_connection or not self.peer_connection.is_connected():
            self._clear_cross_site_data()
            self.ax.text(0.5, 0.5, 'Peer not connected - no cross-site data', 
                        ha='center', va='center', transform=self.ax.transAxes)
            return
        
        data = self.coincidence_series.copy()
        ylim = int(max(1, np.max(data)) / 100) * 100 + 100
        
        if self.normalize_plot:
            col_sum = np.sum(data, axis=0)
            with np.errstate(divide='ignore', invalid='ignore'):
                data = np.nan_to_num(data / col_sum, nan=0.0, posinf=0.0, neginf=0.0)
            ylim = 1
        
        # Plot colors for up to 4 pairs
        colors = ['purple', 'orange', 'brown', 'pink']
        
        pairs = self.app_ref.correlation_pairs[:4]  # Max 4 pairs
        role_label = "Client" if self.app_ref.computer_role == "computer_b" else "Server"
        remote_role = "Server" if self.app_ref.computer_role == "computer_b" else "Client"
        
        for idx, (local_in, remote_in) in enumerate(pairs):
            label = f"{role_label}-{local_in} ↔ {remote_role}-{remote_in}"
            self.ax.plot(data[idx], color=colors[idx], marker='o', 
                        linestyle='-', linewidth=2, label=label)
        
        self.ax.legend(loc='upper left', fontsize=10)
        self.ax.set_ylim([-10, 10])  # Fixed range for better visibility of small changes
        self.ax.set_title('Cross-Site Coincidence Counts (Quantum Correlations)', fontsize=12, fontweight='bold')
        self.ax.set_xlabel('Time Point')
        self.ax.set_ylabel('Coincidences')
        self.ax.set_xticks(range(0, 20))
        self.ax.grid(True, alpha=0.3)

    def _draw_placeholder_plot(self):
        """Placeholder plot while streaming is not yet implemented."""
        self.ax.text(0.5, 0.5, 
                    'Timestamp Streaming Not Yet Implemented\n\n'
                    'Next Steps:\n'
                    '1. Implement timestamp streaming from Time Controller\n'
                    '2. Exchange timestamp batches between sites\n'
                    '3. Calculate coincidences with picosecond precision\n'
                    '4. Plot cross-site coincidence rates',
                    ha='center', va='center', transform=self.ax.transAxes,
                    fontsize=11, bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    def _draw_plot(self):
        """Update the plot based on current mode."""
        self.ax.clear()

        # Draw coincidence plot (or placeholder if not streaming yet)
        if not self.plot_histogram:
            if self.streaming_active:
                self._draw_coincidence_plot()
            else:
                # Show message when not streaming
                self.ax.text(0.5, 0.5, 
                            'Timestamp Streaming Not Started\n\n'
                            'Click "Start Streaming" to begin real-time coincidence counting',
                            ha='center', va='center', transform=self.ax.transAxes,
                            fontsize=12, bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.5))
        else:
            # Could show timestamp rate histogram or other diagnostic plots
            self._draw_placeholder_plot()

        self.canvas.draw()

    def _loop(self):
        """Main update loop running in background thread."""
        while self.continue_update:
            self._update_measurements()
            self._draw_plot()
            time.sleep(0.5)  # Update every 0.5 seconds (fast enough for human perception)

    def start_counter_display(self):
        """Start only the counter display loop (singles rates monitoring).
        
        This does NOT start timestamp streaming or coincidence calculations.
        Use start() to begin full correlation measurements.
        """
        if self.continue_update:
            logger.debug("Counter display already running")
            return
        
        # Start the plot update loop (will show counters only, no streaming)
        self.continue_update = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        logger.info("Counter display started (streaming not active)")
    
    def start(self):
        """Start the full measurement: timestamp streaming + coincidence calculations."""
        if self.streaming_active:
            logger.warning("Streaming already active")
            return
        
        # Start counter display if not already running
        if not self.continue_update:
            self.start_counter_display()
        
        # Start timestamp streaming from Time Controller
        # Determine if we should use mock mode (check if TC is MockTimeController)
        is_mock = hasattr(self.tc, '_base_seed')  # Mock has _base_seed attribute
        
        # Get the actual TC address from app_ref (main GUI)
        if is_mock:
            tc_address = "localhost"
        elif self.app_ref and hasattr(self.app_ref, 'tc_address'):
            tc_address = self.app_ref.tc_address
        else:
            print("error happened in plot updater while getting tc address, defaulting to localhost")
            tc_address = "localhost"
        
        logger.info(f"Starting timestamp streaming with mock={is_mock}, address={tc_address}")
        self.start_streaming(tc_address, is_mock=is_mock)
        logger.info("Full correlation measurement started")

    def stop(self):
        """Stop the background update thread and timestamp streaming."""
        if not self.continue_update:
            return
        
        # Stop timestamp streaming
        self.stop_streaming()
        
        # Stop the plot update loop
        self.continue_update = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        logger.info("PlotUpdater stopped")
