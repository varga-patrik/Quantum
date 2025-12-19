"""
Timestamp streaming and coincidence counting utilities.

This module handles:
- Receiving timestamp streams from Time Controller
- Parsing binary timestamp data (uint64 pairs)
- Buffering timestamps for coincidence analysis
- Calculating cross-site coincidences with configurable time window
"""

import numpy as np
import struct
import logging
from typing import Dict, List, Tuple, Optional
from collections import deque

logger = logging.getLogger(__name__)


class TimestampBuffer:
    """
    Manages a circular buffer of timestamps for a single channel.
    
    Attributes:
        channel: Channel number (1-4)
        max_duration_sec: Maximum time span to keep in buffer
        max_size: Maximum number of timestamps to keep (safety limit)
    """
    
    def __init__(self, channel: int, max_duration_sec: float = 1.0, max_size: int = 10_000_000):
        self.channel = channel
        self.max_duration_sec = max_duration_sec
        self.max_size = max_size
        
        # Store as (timestamp_ps, ref_second) tuples
        self.timestamps: deque = deque(maxlen=max_size)
        
        logger.debug(f"TimestampBuffer created for channel {channel}, "
                    f"max_duration={max_duration_sec}s, max_size={max_size}")
    
    def add_timestamps(self, binary_data: bytes, with_ref_index: bool = True):
        """
        Add timestamps from binary data.
        
        Args:
            binary_data: Binary timestamp data from Time Controller
            with_ref_index: If True, format is [timestamp, refIndex] pairs (uint64, uint64)
                           If False, format is just timestamp (uint64)
        """
        if not binary_data:
            return
        
        if with_ref_index:
            # Parse as pairs of uint64 (little-endian)
            num_values = len(binary_data) // 8
            if num_values % 2 != 0:
                logger.warning(f"Ch{self.channel}: Odd number of uint64 values, truncating last value")
                num_values -= 1
            
            # Unpack all uint64 values
            values = struct.unpack(f'<{num_values}Q', binary_data[:num_values * 8])
            
            # Group into (timestamp, ref_second) pairs
            for i in range(0, len(values), 2):
                ps_in_second = values[i]
                ref_second = values[i + 1]
                
                # Convert to total picoseconds
                total_ps = ps_in_second + (ref_second * int(1e12))
                self.timestamps.append((total_ps, ref_second))
        else:
            # Just timestamps (uint64)
            num_timestamps = len(binary_data) // 8
            values = struct.unpack(f'<{num_timestamps}Q', binary_data[:num_timestamps * 8])
            
            for ps in values:
                self.timestamps.append((ps, 0))  # No ref_second info
        
        # Cleanup old timestamps based on time span
        self._cleanup_old_timestamps()
        
        logger.debug(f"Ch{self.channel}: Added timestamps, buffer size now {len(self.timestamps)}")
    
    def add_timestamps_array(self, timestamps_ps: np.ndarray, ref_seconds: np.ndarray = None):
        """
        Add timestamps from numpy arrays (used for peer-to-peer exchange).
        
        Args:
            timestamps_ps: Array of timestamps in picoseconds
            ref_seconds: Optional array of reference seconds (if None, uses 0)
        """
        if len(timestamps_ps) == 0:
            return
        
        if ref_seconds is None:
            ref_seconds = np.zeros(len(timestamps_ps), dtype=np.uint64)
        
        # Add each timestamp
        for ps, ref in zip(timestamps_ps, ref_seconds):
            self.timestamps.append((int(ps), int(ref)))
        
        # Cleanup old timestamps
        self._cleanup_old_timestamps()
        
        logger.debug(f"Ch{self.channel}: Added {len(timestamps_ps)} timestamps from array, buffer size now {len(self.timestamps)}")
    
    def _cleanup_old_timestamps(self):
        """Remove timestamps older than max_duration_sec."""
        if not self.timestamps:
            return
        
        # Get the most recent timestamp
        latest_ps = self.timestamps[-1][0]
        cutoff_ps = latest_ps - (self.max_duration_sec * 1e12)
        
        # Remove old timestamps from the left
        while self.timestamps and self.timestamps[0][0] < cutoff_ps:
            self.timestamps.popleft()
    
    def get_timestamps(self) -> np.ndarray:
        """
        Get all timestamps as numpy array (in picoseconds).
        Thread-safe snapshot of current timestamps.
        
        Returns:
            Array of timestamps in picoseconds
        """
        if not self.timestamps:
            return np.array([], dtype=np.uint64)
        
        # Create a snapshot to avoid "deque mutated during iteration" error
        snapshot = list(self.timestamps)
        return np.array([ts[0] for ts in snapshot], dtype=np.uint64)
    
    def clear(self):
        """Clear all timestamps from buffer."""
        self.timestamps.clear()
        logger.debug(f"Ch{self.channel}: Buffer cleared")
    
    def __len__(self):
        return len(self.timestamps)


class CoincidenceCounter:
    """
    Counts coincidences between local and remote timestamp streams.
    
    Uses a simple sliding window algorithm optimized for live streaming.
    """
    
    def __init__(self, window_ps: int = 1000):
        """
        Initialize coincidence counter.
        
        Args:
            window_ps: Coincidence window in picoseconds (±window_ps)
        """
        self.window_ps = window_ps
        logger.info(f"CoincidenceCounter initialized with window ±{window_ps} ps")
    
    def count_coincidences(self, 
                          local_timestamps: np.ndarray, 
                          remote_timestamps: np.ndarray,
                          time_offset_ps: int = 0) -> int:
        """
        Count coincidences between local and remote timestamps.
        
        Uses optimized O(n+m) sliding window algorithm with consumption.
        Each remote timestamp is matched AT MOST ONCE (physically accurate for entangled pairs).
        Finds the CLOSEST remote timestamp within the window for each local timestamp.
        
        Args:
            local_timestamps: Local timestamps in picoseconds (sorted)
            remote_timestamps: Remote timestamps in picoseconds (sorted)
            time_offset_ps: Time offset to apply to remote timestamps (from C++ Correlator)
        
        Returns:
            Number of coincidences found (each photon matched at most once)
        """
        if len(local_timestamps) == 0 or len(remote_timestamps) == 0:
            return 0
        
        # Apply time offset to remote timestamps
        remote_adjusted = remote_timestamps + time_offset_ps
        
        # Track which remote timestamps have been consumed
        consumed = np.zeros(len(remote_adjusted), dtype=bool)
        
        coincidences = 0
        j = 0  # Pointer for start of search window
        
        # For each local timestamp
        for local_ts in local_timestamps:
            # Move window start pointer forward (skip consumed and out-of-window timestamps)
            while j < len(remote_adjusted) and (consumed[j] or remote_adjusted[j] < local_ts - self.window_ps):
                j += 1
            
            if j >= len(remote_adjusted):
                break  # No more remote timestamps to check
            
            # Find the CLOSEST remote timestamp within window [local_ts - window, local_ts + window]
            best_idx = -1
            best_distance = self.window_ps + 1  # Initialize to larger than window
            
            k = j
            while k < len(remote_adjusted) and remote_adjusted[k] <= local_ts + self.window_ps:
                if not consumed[k]:
                    distance = abs(remote_adjusted[k] - local_ts)
                    if distance <= self.window_ps and distance < best_distance:
                        best_distance = distance
                        best_idx = k
                k += 1
            
            # If we found a match, consume it and count the coincidence
            if best_idx != -1:
                consumed[best_idx] = True
                coincidences += 1
        
        return coincidences
    
    def count_all_pairs(self,
                       local_buffers: Dict[int, TimestampBuffer],
                       remote_buffers: Dict[int, TimestampBuffer],
                       time_offset_ps: int = 0) -> Dict[Tuple[int, int], int]:
        """
        Count coincidences for all channel pairs.
        
        Args:
            local_buffers: Dictionary of local timestamp buffers (keyed by channel 1-4)
            remote_buffers: Dictionary of remote timestamp buffers (keyed by channel 1-4)
            time_offset_ps: Time offset to apply to remote timestamps
        
        Returns:
            Dictionary mapping (local_ch, remote_ch) -> coincidence_count
        """
        results = {}
        
        for local_ch in [1, 2, 3, 4]:
            for remote_ch in [1, 2, 3, 4]:
                if local_ch not in local_buffers or remote_ch not in remote_buffers:
                    results[(local_ch, remote_ch)] = 0
                    continue
                
                local_ts = local_buffers[local_ch].get_timestamps()
                remote_ts = remote_buffers[remote_ch].get_timestamps()
                
                count = self.count_coincidences(local_ts, remote_ts, time_offset_ps)
                results[(local_ch, remote_ch)] = count
        
        return results


def parse_binary_timestamps(binary_data: bytes, with_ref_index: bool = True) -> np.ndarray:
    """
    Parse binary timestamp data into structured numpy array.
    
    Args:
        binary_data: Raw binary data from Time Controller
        with_ref_index: If True, expects [timestamp, refIndex] pairs
    
    Returns:
        Structured numpy array with 'timestamp' and 'refIndex' fields
    """
    if not binary_data:
        dtype = np.dtype([("timestamp", np.uint64), ("refIndex", np.uint64)])
        return np.array([], dtype=dtype)
    
    if with_ref_index:
        # Format: alternating uint64 pairs [timestamp, refIndex, timestamp, refIndex, ...]
        dtype = np.dtype([("timestamp", np.uint64), ("refIndex", np.uint64)])
        timestamps = np.frombuffer(binary_data, dtype=dtype)
    else:
        # Format: just timestamps [timestamp, timestamp, ...]
        timestamps = np.frombuffer(binary_data, dtype=np.uint64)
    
    return timestamps


def format_timestamp(timestamp_ps: int) -> str:
    """
    Format timestamp in picoseconds to human-readable string.
    
    Args:
        timestamp_ps: Timestamp in picoseconds
    
    Returns:
        Formatted string (e.g., "1.234567 s")
    """
    seconds = timestamp_ps / 1e12
    return f"{seconds:.6f} s"


def calculate_detection_rate(timestamps: np.ndarray, duration_sec: float) -> float:
    """
    Calculate detection rate in Hz.
    
    Args:
        timestamps: Array of timestamps
        duration_sec: Time duration over which to calculate rate
    
    Returns:
        Detection rate in Hz (photons per second)
    """
    if duration_sec <= 0:
        return 0.0
    
    return len(timestamps) / duration_sec
