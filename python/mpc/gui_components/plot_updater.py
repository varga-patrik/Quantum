"""Plot updater component for real-time timestamp streaming and coincidence measurement."""

import threading
import time
import numpy as np
import random
import logging
from typing import Optional
from pathlib import Path

from mock_time_controller import safe_zmq_exec
from streaming.timestamp_stream import TimestampBuffer, CoincidenceCounter
from streaming.stream_client import TimeControllerStreamClient
from gui_components.config import (
    COINCIDENCE_WINDOW_PS,
    TIMESTAMP_BUFFER_DURATION_SEC,
    TIMESTAMP_BUFFER_MAX_SIZE,
    TIMESTAMP_BATCH_INTERVAL_SEC,
    DEBUG_MODE
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
        self.streaming_is_mock = False

        # File-tail streaming (DLT writes timestamps to files; we can read incrementally)
        self._file_tail_stop_event = threading.Event()
        self._file_tail_threads: dict[int, threading.Thread] = {}
        self._file_tail_offsets: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0}
        
        # Batch sending for peer exchange
        self.last_batch_send_time = time.time()
        self.last_sent_counts = {1: 0, 2: 0, 3: 0, 4: 0}  # Track how many timestamps we've already sent per channel

    def start_streaming(self, tc_address: str, is_mock: bool = False, 
                       local_save_channels: list = None, remote_save_channels: list = None):
        """
        Start timestamp streaming from Time Controller via DLT service.
        
        Args:
            tc_address: Time Controller IP address
            is_mock: Use mock streaming for testing
            local_save_channels: List of local channels to save to files (default: all [1,2,3,4])
            remote_save_channels: List of remote channels to save to files (default: none [])
        """
        # Default to saving all local channels if not specified
        if local_save_channels is None:
            local_save_channels = [1, 2, 3, 4]
        if remote_save_channels is None:
            remote_save_channels = []
        if self.streaming_active:
            logger.warning("Streaming already active")
            return

        self.streaming_is_mock = is_mock
        
        # Re-read config to get latest COINCIDENCE_WINDOW_PS value
        import importlib
        import gui_components.config as config_module
        importlib.reload(config_module)
        self.coincidence_counter.window_ps = config_module.COINCIDENCE_WINDOW_PS
        logger.info(f"Starting streaming with coincidence window ±{config_module.COINCIDENCE_WINDOW_PS} ps")
        
        # Clear all buffers to ensure fresh data for this session
        # This prevents mixing old timestamps with new ones (different ref_second epochs)
        logger.info("Clearing all timestamp buffers for fresh streaming session")
        for ch in [1, 2, 3, 4]:
            self.local_buffers[ch].clear()
            self.remote_buffers[ch].clear()
        
        # Reset coincidence tracking
        self.coincidence_series = np.zeros((4, 20))
        self.last_coincidence_counts = [0, 0, 0, 0]
        self.last_sent_counts = {1: 0, 2: 0, 3: 0, 4: 0}
        
        # Reset file-tail offsets (will be set properly when tailing starts on NEW files)
        self._file_tail_offsets = {1: 0, 2: 0, 3: 0, 4: 0}
        
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
            
            # STEP 1: Configure Time Controller REC settings FIRST (before DLT acquisitions)
            # This follows the correct workflow from acquire_timestamps()
            try:
                # Trigger RECord signal manually (PLAY command)
                zmq_exec(self.tc, "REC:TRIG:ARM:MODE MANUal")
                # Enable the RECord generator
                zmq_exec(self.tc, "REC:ENABle ON")
                # STOP any already ongoing acquisition
                zmq_exec(self.tc, "REC:STOP")
                # Infinite number of records (continuous streaming)
                zmq_exec(self.tc, "REC:NUM 0")
                # Set very long duration per record (1000 seconds = ~16.7 minutes in picoseconds)
                zmq_exec(self.tc, "REC:DURation 1000000000000000")  # 1000 seconds
                logger.info("Configured Time Controller REC settings (1000s duration, infinite records)")
            except Exception as e:
                logger.error(f"Failed to configure REC settings: {e}")
                return
            
            # STEP 2: Start DLT acquisitions for ALL channels (required for streaming)
            # DLT must run to create ZMQ streaming endpoints
            # Save to permanent files for checked channels, temp files for unchecked
            import tempfile
            
            output_dir = Path.home() / "Documents" / "AgodSolt" / "data"
            output_dir.mkdir(parents=True, exist_ok=True)
            temp_dir = Path(tempfile.gettempdir()) / "mpc_streaming"
            temp_dir.mkdir(exist_ok=True)
            
            logger.info(f"Starting DLT acquisitions for all channels (streaming), saving: {local_save_channels}")
            
            for channel in [1, 2, 3, 4]:
                try:
                    # Clear any previous errors
                    zmq_exec(self.tc, f"RAW{channel}:ERRORS:CLEAR")
                    
                    # Determine file path: permanent for saved channels, temp for streaming-only
                    timestr = time_module.strftime("%Y%m%d_%H%M%S")
                    if channel in local_save_channels:
                        filepath = output_dir / f"timestamps_live_ch{channel}_{timestr}.bin"
                        is_temp = False
                        logger.info(f"Channel {channel}: saving to {filepath}")
                    else:
                        filepath = temp_dir / f"timestamps_temp_ch{channel}_{timestr}.bin"
                        is_temp = True
                        logger.debug(f"Channel {channel}: streaming only (temp file: {filepath})")
                    
                    filepath_escaped = str(filepath).replace("\\", "\\\\")
                    
                    # Tell DLT to start acquisition (creates streaming endpoint + file)
                    command = f'start-save --address {tc_address} --channel {channel} --filename "{filepath_escaped}" --format bin --with-ref-index'
                    answer = dlt_exec(dlt, command)
                    acq_id = answer["id"]
                    
                    # Parse acquisition ID to get streaming port
                    # Format is "address:port" like "169.254.104.112:5556"
                    if ':' in acq_id:
                        stream_port = int(acq_id.split(':')[1])
                        self.acquisition_ids[channel] = {
                            'id': acq_id, 
                            'port': stream_port, 
                            'filepath': filepath,
                            'is_temp': is_temp
                        }
                        logger.info(f"Channel {channel}: DLT started, ID={acq_id}, port={stream_port}")
                    else:
                        self.acquisition_ids[channel] = {
                            'id': acq_id, 
                            'port': None, 
                            'filepath': filepath,
                            'is_temp': is_temp
                        }
                        logger.warning(f"Could not parse port from acquisition ID: {acq_id}")
                    
                    # Enable timestamp transfer for this channel immediately after DLT starts
                    # (Following the pattern from open_timestamps_acquisition)
                    zmq_exec(self.tc, f"RAW{channel}:SEND ON")
                    logger.info(f"Channel {channel}: RAW:SEND enabled")
                    
                except Exception as e:
                    logger.error(f"Failed to start DLT acquisition for channel {channel}: {e}")
                    # Continue with other channels even if one fails
            
            # STEP 3: Start the Time Controller acquisition (REC:PLAY)
            try:
                zmq_exec(self.tc, "REC:PLAY")
                time_module.sleep(0.2)  # Give it a moment to transition
                rec_stage = zmq_exec(self.tc, "REC:STAGe?")
                logger.info(f"Started Time Controller recording - REC stage: {rec_stage}")
                
                if rec_stage.strip().upper() != "PLAYING":
                    logger.warning(f"Time Controller did not enter PLAYING state (still {rec_stage})")
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
        
        # Create stream client connected to DLT streaming ports
        # Mark streaming active before starting background ingestion workers.
        self.streaming_active = True

        # NOTE: In practice, the DLT/TC streaming ports may be single-consumer or not usable
        # in parallel with DLT saving. Since DLT is already writing the timestamps to files,
        # we tail those files for reliable live updates.
        if is_mock:
            self.stream_client = TimeControllerStreamClient(tc_address, is_mock=True)
            for channel in [1, 2, 3, 4]:
                callback = lambda data, ch=channel: self._on_timestamp_batch(ch, data)
                self.stream_client.start_stream(channel, callback, port=None)
        else:
            self.stream_client = None
            self._start_file_tail_threads()  # Read timestamps from DLT output files
            logger.info("File tailing ENABLED - reading timestamps from DLT output files")
        logger.info("Timestamp streaming started for all channels (file tailing enabled for live reading)")
    
    def stop_streaming(self):
        """Stop timestamp streaming and DLT acquisitions."""
        if not self.streaming_active:
            logger.debug("stop_streaming called but streaming not active, ignoring")
            return
        
        # Set flag immediately to prevent re-entry
        self.streaming_active = False
        
        logger.info("Stopping timestamp streaming")
        
        # Stop file-tail threads (if used)
        self._stop_file_tail_threads()

        # Stop stream clients (mock mode)
        if self.stream_client is not None:
            self.stream_client.stop_all_streams()
        
        # Stop DLT acquisitions (if not mock)
        if not self.streaming_is_mock and hasattr(self, 'acquisition_ids'):
            from utils.common import zmq_exec, dlt_exec
            
            # Get DLT connection from app_ref
            dlt = getattr(self.app_ref, 'dlt', None) if self.app_ref else None
            
            if dlt:
                # Stop DLT acquisitions and clean up temporary files
                for channel, acq_info in self.acquisition_ids.items():
                    try:
                        acq_id = acq_info['id'] if isinstance(acq_info, dict) else acq_info
                        status = dlt_exec(dlt, f"stop --id {acq_id}")
                        logger.info(f"Stopped DLT acquisition for channel {channel}")
                        
                        # Delete temporary files (streaming-only channels)
                        if isinstance(acq_info, dict) and acq_info.get('is_temp', False):
                            filepath = acq_info.get('filepath')
                            if filepath and Path(filepath).exists():
                                try:
                                    Path(filepath).unlink()
                                    logger.info(f"Deleted temporary file: {filepath}")
                                except Exception as e:
                                    logger.warning(f"Could not delete temp file {filepath}: {e}")
                    except Exception as e:
                        logger.error(f"Error stopping DLT acquisition for channel {channel}: {e}")
                
                # Stop Time Controller recording
                try:
                    zmq_exec(self.tc, "REC:STOP")
                    logger.info("Stopped Time Controller recording (REC:STOP)")
                except Exception as e:
                    logger.error(f"Failed to stop TC recording: {e}")
                
                # Disable RAW streaming on Time Controller (for all channels, not just saved ones)
                for channel in [1, 2, 3, 4]:
                    try:
                        zmq_exec(self.tc, f"RAW{channel}:SEND OFF")
                        logger.info(f"Disabled RAW{channel}:SEND on Time Controller")
                    except Exception as e:
                        logger.error(f"Failed to disable streaming on channel {channel}: {e}")

    def _start_file_tail_threads(self):
        """Start background readers that tail the DLT output files and fill local buffers."""
        # Reset stop flag
        self._file_tail_stop_event.clear()
        
        # Set offsets to END of existing files (to skip old data from previous recordings)
        for ch in [1, 2, 3, 4]:
            acq = getattr(self, 'acquisition_ids', {}).get(ch)
            filepath = None
            if isinstance(acq, dict):
                filepath = acq.get('filepath')
            
            if filepath:
                try:
                    path = Path(filepath)
                    if path.exists():
                        # Seek to end of file to only read NEW data
                        file_size = path.stat().st_size
                        # Align to 16-byte boundary (timestamp pairs are 2x uint64 = 16 bytes)
                        self._file_tail_offsets[ch] = (file_size // 16) * 16
                        logger.info(f"Ch{ch}: File-tail starting at offset {self._file_tail_offsets[ch]} (skipping existing data)")
                    else:
                        self._file_tail_offsets[ch] = 0
                except Exception as e:
                    logger.warning(f"Ch{ch}: Could not get file size: {e}, starting at 0")
                    self._file_tail_offsets[ch] = 0
            else:
                self._file_tail_offsets[ch] = 0

        for channel in [1, 2, 3, 4]:
            t = threading.Thread(
                target=self._file_tail_worker,
                args=(channel,),
                daemon=True,
                name=f"DLTFileTail-Ch{channel}",
            )
            self._file_tail_threads[channel] = t
            t.start()
        logger.info("Started DLT file-tail threads for live timestamps")

    def _stop_file_tail_threads(self):
        """Stop file-tail background readers."""
        try:
            self._file_tail_stop_event.set()
            for ch, t in list(self._file_tail_threads.items()):
                if t.is_alive():
                    t.join(timeout=1.0)
            self._file_tail_threads.clear()
        except Exception:
            pass

    def _file_tail_worker(self, channel: int):
        """Continuously read newly appended bytes from the channel's DLT file."""
        chunk_size = 256 * 1024  # bytes
        sleep_sec = 0.05

        while not self._file_tail_stop_event.is_set():
            acq = getattr(self, 'acquisition_ids', {}).get(channel)
            filepath = None
            if isinstance(acq, dict):
                filepath = acq.get('filepath')
            if not filepath:
                time.sleep(sleep_sec)
                continue

            try:
                path = Path(filepath)
                if not path.exists():
                    time.sleep(sleep_sec)
                    continue

                with path.open('rb') as f:
                    offset = self._file_tail_offsets.get(channel, 0)
                    try:
                        f.seek(offset)
                    except Exception:
                        # If file was rotated/truncated, restart from 0.
                        offset = 0
                        f.seek(0)

                    data = f.read(chunk_size)
                    if not data:
                        time.sleep(sleep_sec)
                        continue

                    # Keep offset at a multiple of 16 bytes (2x uint64) to avoid splitting pairs.
                    valid_len = (len(data) // 16) * 16
                    if valid_len <= 0:
                        time.sleep(sleep_sec)
                        continue

                    payload = data[:valid_len]
                    self._file_tail_offsets[channel] = offset + valid_len

                    self.local_buffers[channel].add_timestamps(payload, with_ref_index=True)
            except Exception:
                # File may be temporarily locked or unavailable; retry.
                time.sleep(0.2)
    
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
            
            # Send only NEW timestamps since last batch (prevent re-sending same data)
            # Collect timestamps from all channels as compressed binary
            batch_data = {}
            total_ts = 0
            for channel in [1, 2, 3, 4]:
                all_timestamps = self.local_buffers[channel].get_timestamps()
                
                # Only send NEW timestamps since last batch
                last_sent = self.last_sent_counts[channel]
                new_timestamps = all_timestamps[last_sent:]  # Slice from last sent position to end
                
                if len(new_timestamps) > 0:
                    # Update tracking
                    self.last_sent_counts[channel] = len(all_timestamps)
                    
                    # Convert to binary (much more efficient than JSON)
                    binary = new_timestamps.tobytes()
                    # Compress to reduce network load
                    compressed = zlib.compress(binary, level=1)  # Fast compression
                    # Encode as base64 for JSON transport
                    encoded = base64.b64encode(compressed).decode('ascii')
                    batch_data[channel] = {
                        'data': encoded,
                        'count': len(new_timestamps)
                    }
                    total_ts += len(new_timestamps)
            
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
            # Calculate cross-site coincidences (both sites do this with their local+remote data)
            self._calculate_coincidences()
            
            # ONE-WAY TCP: Only send timestamps from Wigner (server/computer_a) to BME (client/computer_b)
            # Wigner has ~10x fewer timestamps, so it's the sender
            if self.app_ref and hasattr(self.app_ref, 'computer_role'):
                if self.app_ref.computer_role == "computer_a":  # Wigner (server)
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
        configured coincidence window.
        """
        if not self.app_ref or not hasattr(self.app_ref, 'correlation_pairs'):
            return
        
        # Get time offset from config (measured by C++ Correlator)
        time_offset_ps = getattr(self.app_ref, 'time_offset_ps', 0) or 0
        
        # Get correlation pairs: [(local_ch, remote_ch), ...]
        pairs = self.app_ref.correlation_pairs
        
        # Debug logging only when enabled
        if DEBUG_MODE:
            local_sizes = [len(self.local_buffers[ch].get_timestamps()) for ch in [1,2,3,4]]
            remote_sizes = [len(self.remote_buffers[ch].get_timestamps()) for ch in [1,2,3,4]]
            logger.debug(f"Coincidence calc: window=±{self.coincidence_counter.window_ps}ps, offset={time_offset_ps}ps")
            logger.debug(f"  Buffer sizes - Local: {local_sizes}, Remote: {remote_sizes}")
        
        # Calculate coincidences for each pair
        new_counts = []
        for local_ch, remote_ch in pairs:
            local_ts = self.local_buffers[local_ch].get_timestamps()
            remote_ts = self.remote_buffers[remote_ch].get_timestamps()
            
            # Debug: show timestamp ranges to verify overlap
            if DEBUG_MODE and len(local_ts) > 0 and len(remote_ts) > 0:
                logger.info(f"  Pair ({local_ch},{remote_ch}): local range [{local_ts[0]:,} - {local_ts[-1]:,}], "
                           f"remote range [{remote_ts[0]:,} - {remote_ts[-1]:,}]")
                # Check overlap after applying offset
                remote_adjusted_first = int(remote_ts[0]) - time_offset_ps
                remote_adjusted_last = int(remote_ts[-1]) - time_offset_ps
                local_first, local_last = int(local_ts[0]), int(local_ts[-1])
                overlap = min(local_last, remote_adjusted_last) - max(local_first, remote_adjusted_first)
                logger.info(f"    After offset: remote range [{remote_adjusted_first:,} - {remote_adjusted_last:,}], overlap={overlap/1e12:.3f}s")
            
            count = self.coincidence_counter.count_coincidences(
                local_ts, remote_ts, time_offset_ps
            )
            
            if DEBUG_MODE:
                logger.debug(f"  Pair ({local_ch},{remote_ch}): local={len(local_ts)}, remote={len(remote_ts)}, coincidences={count}")
            
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
        import datetime
        
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
        
        # Check if this is server (Wigner) - it doesn't receive remote timestamps
        if self.app_ref.computer_role == "computer_a":
            current_time = datetime.datetime.now().strftime('%H:%M:%S')
            self.ax.text(0.5, 0.5, 
                        f'Server Mode (Wigner) - Sending timestamps to BME\n\n'
                        f'Coincidence detection runs on BME (client) side\n'
                        f'because BME receives timestamps from both sites.\n\n'
                        f'Last update: {current_time}',
                        ha='center', va='center', transform=self.ax.transAxes,
                        fontsize=11, bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))
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
        
        # Auto-scale y-axis based on data (with some padding)
        if self.normalize_plot:
            self.ax.set_ylim([-0.05, 1.05])
        else:
            max_count = max(1, np.max(data))
            # Use minimum y-limit of 10 so zeros are clearly visible as flat line
            y_max = max(10, max_count * 1.2)
            self.ax.set_ylim([-y_max * 0.05, y_max])
        
        # Show current time and window info in title for visual feedback
        import datetime
        current_time = datetime.datetime.now().strftime('%H:%M:%S')
        window_ps = self.coincidence_counter.window_ps
        self.ax.set_title(f'Cross-Site Coincidences | Window: ±{window_ps:,} ps | {current_time}', 
                         fontsize=11, fontweight='bold')
        self.ax.set_xlabel('Time Point (0.5s intervals)')
        self.ax.set_ylabel('Coincidences' if not self.normalize_plot else 'Normalized')
        self.ax.set_xticks(range(0, 20))
        self.ax.grid(True, alpha=0.3)

    def _draw_plot(self):
        """Update the plot based on current mode."""
        self.ax.clear()

        # Draw coincidence plot (or placeholder if not streaming yet)
        if not self.plot_histogram:
            if self.streaming_active:
                # Draw live coincidence plot
                self._draw_coincidence_plot()
            else:
                # Show message when not streaming
                self.ax.text(0.5, 0.5, 
                            'Timestamp Streaming Not Started\n\n'
                            'Click "Start" to begin recording\n'
                            'and see live coincidence measurements',
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
    
    def start(self, local_save_channels: list = None, remote_save_channels: list = None, 
              recording_duration_sec: int = None):
        """Start the full measurement: timestamp streaming + coincidence calculations.
        
        Args:
            local_save_channels: List of local channels to save to files (default: all [1,2,3,4])
            remote_save_channels: List of remote channels to save to files (default: none [])
            recording_duration_sec: Optional recording duration in seconds (None = unlimited)
        """
        if self.streaming_active:
            logger.warning("Streaming already active")
            return
        
        # Store duration for reference (auto-stop handled by main_gui)
        self.recording_duration_sec = recording_duration_sec
        if recording_duration_sec:
            logger.info(f"Recording will run for {recording_duration_sec} seconds")
        
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
        self.start_streaming(tc_address, is_mock=is_mock, 
                           local_save_channels=local_save_channels,
                           remote_save_channels=remote_save_channels)
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
