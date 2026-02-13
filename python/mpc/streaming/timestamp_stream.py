"""
Timestamp streaming and coincidence counting utilities.

This module handles:
- Receiving timestamp streams from Time Controller
- Parsing binary timestamp data (uint64 pairs)
- Buffering timestamps for coincidence analysis
- Calculating cross-site coincidences with configurable time window
"""

import numpy as np
import threading
import logging
from typing import Dict, List, Tuple, Optional
from gui_components.config import DEBUG_MODE

logger = logging.getLogger(__name__)


class TimestampBuffer:
    """
    Manages a time-windowed buffer of timestamps for a single channel.
    
    Uses pre-allocated numpy arrays with start/end pointers for O(1) amortized
    appends. Avoids np.concatenate (which copies the entire buffer every call).
    
    All public methods are thread-safe via a lock.
    
    Attributes:
        channel: Channel number (1-4)
        max_duration_sec: Maximum time span to keep in buffer
        max_size: Maximum number of timestamps to keep (safety limit)
    """
    
    # Extra capacity beyond max_size to reduce compaction frequency
    _HEADROOM = 2_000_000
    
    def __init__(self, channel: int, max_duration_sec: float = 1.0, max_size: int = 10_000_000):
        self.channel = channel
        self.max_duration_sec = max_duration_sec
        self.max_size = max_size
        self._lock = threading.Lock()
        
        # Pre-allocate arrays; _start/_end track the valid data window
        cap = max_size + self._HEADROOM
        self._ts = np.empty(cap, dtype=np.int64)      # total_ps
        self._ref = np.empty(cap, dtype=np.uint64)     # ref_second
        self._start = 0   # index of first valid entry
        self._end = 0     # index past last valid entry
        
        logger.debug(f"TimestampBuffer created for channel {channel}, "
                    f"max_duration={max_duration_sec}s, capacity={cap}")
    
    def _make_room(self, needed: int):
        """Ensure space for `needed` more entries. Called with lock held."""
        if self._end + needed <= len(self._ts):
            return  # Already have room
        
        count = self._end - self._start
        cap = len(self._ts)
        
        # Try compacting first (shift valid data to front)
        if self._start > 0 and count + needed <= cap:
            self._ts[:count] = self._ts[self._start:self._end]
            self._ref[:count] = self._ref[self._start:self._end]
            self._start = 0
            self._end = count
            return
        
        # Need a bigger array
        new_cap = max(cap * 2, count + needed + self._HEADROOM)
        new_ts = np.empty(new_cap, dtype=np.int64)
        new_ref = np.empty(new_cap, dtype=np.uint64)
        if count > 0:
            new_ts[:count] = self._ts[self._start:self._end]
            new_ref[:count] = self._ref[self._start:self._end]
        self._ts = new_ts
        self._ref = new_ref
        self._start = 0
        self._end = count
    
    def add_timestamps(self, binary_data: bytes, with_ref_index: bool = True):
        """
        Add timestamps from binary data (from file tail or DLT stream).
        O(n_new) amortized — only copies the new data, not the entire buffer.
        """
        if not binary_data:
            return
        
        if with_ref_index:
            valid_len = (len(binary_data) // 16) * 16
            if valid_len == 0:
                return
            raw = np.frombuffer(binary_data[:valid_len], dtype=np.uint64).reshape(-1, 2)
            new_total = raw[:, 0].astype(np.int64) + raw[:, 1].astype(np.int64) * 1_000_000_000_000
            new_refs = raw[:, 1]
        else:
            num_timestamps = len(binary_data) // 8
            if num_timestamps == 0:
                return
            new_total = np.frombuffer(binary_data[:num_timestamps * 8], dtype=np.uint64).astype(np.int64)
            new_refs = np.zeros(num_timestamps, dtype=np.uint64)
        
        n = len(new_total)
        with self._lock:
            self._make_room(n)
            self._ts[self._end:self._end + n] = new_total
            self._ref[self._end:self._end + n] = new_refs
            self._end += n
            self._cleanup()
    
    def add_timestamps_array(self, timestamps_ps: np.ndarray, ref_seconds: np.ndarray = None):
        """
        Add timestamps from numpy arrays (used for peer-to-peer exchange).
        """
        if len(timestamps_ps) == 0:
            return
        
        new_total = timestamps_ps.astype(np.int64)
        if ref_seconds is None:
            new_refs = np.zeros(len(new_total), dtype=np.uint64)
        else:
            new_refs = ref_seconds.astype(np.uint64)
        
        n = len(new_total)
        with self._lock:
            self._make_room(n)
            self._ts[self._end:self._end + n] = new_total
            self._ref[self._end:self._end + n] = new_refs
            self._end += n
            self._cleanup()
    
    def _cleanup(self):
        """Remove old timestamps and enforce max_size. Must be called with lock held."""
        count = self._end - self._start
        if count == 0:
            return
        
        cutoff = self._ts[self._end - 1] - int(self.max_duration_sec * 1e12)
        valid = self._ts[self._start:self._end]
        trim = int(np.searchsorted(valid, cutoff, side='left'))
        self._start += trim
        
        # Enforce max_size
        if self._end - self._start > self.max_size:
            self._start = self._end - self.max_size
    
    def get_timestamps(self) -> np.ndarray:
        """Get all timestamps as numpy array (in picoseconds). Thread-safe snapshot."""
        with self._lock:
            if self._end <= self._start:
                return np.array([], dtype=np.int64)
            return self._ts[self._start:self._end].copy()
    
    def get_timestamps_with_ref(self) -> tuple:
        """Get timestamps and reference seconds. Thread-safe snapshot."""
        with self._lock:
            if self._end <= self._start:
                return (np.array([], dtype=np.int64), np.array([], dtype=np.uint64))
            return (self._ts[self._start:self._end].copy(),
                    self._ref[self._start:self._end].copy())
    
    def clear(self):
        """Clear all timestamps from buffer."""
        with self._lock:
            self._start = 0
            self._end = 0
        logger.debug(f"Ch{self.channel}: Buffer cleared")
    
    def __len__(self):
        return max(0, self._end - self._start)


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
        
        Uses vectorized binary search for O(n log m) performance.
        For each local timestamp, checks if ANY remote timestamp falls within ±window_ps.
        
        A single local timestamp can only be counted ONCE per pair (even if multiple
        remote timestamps fall within the window). However, across DIFFERENT pairs
        (e.g., (1,1) and (1,4)), the same local timestamp CAN produce a coincidence
        in both pairs — this is correct and standard in quantum coincidence counting,
        since each detector pair is measured independently.
        
        Args:
            local_timestamps: Local timestamps in picoseconds (sorted)
            remote_timestamps: Remote timestamps in picoseconds (sorted)
            time_offset_ps: Time offset to apply to remote timestamps.
                           Photons travel FROM BME (local) TO Wigner (remote).
                           Remote detects LATER → positive offset → we SUBTRACT
                           from remote to align with local time.
        
        Returns:
            Number of local timestamps that have at least one matching remote timestamp
        """
        if len(local_timestamps) == 0 or len(remote_timestamps) == 0:
            return 0
        
        # Apply time offset to remote timestamps - SUBTRACT because positive offset 
        # means remote is ahead, so we shift it back to align with local
        remote_adjusted = remote_timestamps.astype(np.int64) - time_offset_ps
        local_int = local_timestamps.astype(np.int64)
        
        # Vectorized binary search: for each local, find if ANY remote is in window
        left_bounds = np.searchsorted(remote_adjusted, local_int - self.window_ps, side='left')
        right_bounds = np.searchsorted(remote_adjusted, local_int + self.window_ps, side='right')
        
        # Count local timestamps that have at least one match
        has_match = right_bounds > left_bounds
        coincidences = int(np.sum(has_match))
        
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
