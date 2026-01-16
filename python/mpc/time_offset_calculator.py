"""
Time Offset Calculator - FFT Cross-Correlation Algorithm

Replicates the C++ Correlator::CalculateDeltaT() function to automatically
calculate time offset between two sites' timestamp streams.
"""

import numpy as np
import struct
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

logger = logging.getLogger(__name__)


class TimeOffsetCalculator:
    """
    FFT-based cross-correlation calculator for timestamp synchronization.
    
    Matches C++ Correlator implementation:
    - Bins timestamps into histogram
    - Performs FFT cross-correlation
    - Finds peak to determine time offset
    """
    
    def __init__(self, tau: int = 2048, N: int = 2**20, Tshift: int = 100_000_000):
        """
        Initialize calculator with correlation parameters.
        
        Args:
            tau: Bin width in picoseconds (default: 2048 ps = 2.048 ns)
            N: Number of FFT bins (default: 2^20 = 1,048,576)
            Tshift: Initial time shift guess in picoseconds (default: 100,000,000 ps = 0.1 ms)
        """
        self.tau = tau
        self.N = N
        self.Tshift = Tshift
        self.chunk_size = 100_000  # Read files in chunks for memory efficiency
        
        logger.info(f"TimeOffsetCalculator initialized: tau={tau}ps, N={N}, Tshift={Tshift}ps")
    
    def read_timestamp_file(self, filepath: Path) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Read binary timestamp file with format: [timestamp_ps, ref_second] pairs.
        
        Args:
            filepath: Path to binary timestamp file
        
        Returns:
            Tuple of (timestamps_array, file_info_dict)
            - timestamps_array: uint64 array of absolute timestamps in picoseconds
            - file_info: metadata (file_size, num_timestamps, time_span_sec, etc.)
        """
        logger.info(f"Reading timestamp file: {filepath}")
        
        if not filepath.exists():
            raise FileNotFoundError(f"Timestamp file not found: {filepath}")
        
        file_size = filepath.stat().st_size
        num_values = file_size // 8  # uint64 = 8 bytes
        
        if num_values % 2 != 0:
            logger.warning(f"File has odd number of uint64 values, truncating last value")
            num_values -= 1
        
        num_timestamp_pairs = num_values // 2
        
        # Use numpy to read directly - 10x faster and uses far less memory than struct.unpack
        logger.info(f"Reading {num_timestamp_pairs:,} timestamp pairs ({file_size / 1024**2:.1f} MB)")
        
        with open(filepath, 'rb') as f:
            # Read as uint64 array directly into numpy (little-endian)
            raw_values = np.fromfile(f, dtype=np.uint64, count=num_values)
        
        # Convert pairs to absolute timestamps using vectorized operations (100x faster than loop)
        ps_in_second = raw_values[0::2]  # Every even index
        ref_second = raw_values[1::2]    # Every odd index
        
        # Calculate absolute timestamps (vectorized - processes millions in milliseconds)
        timestamps = ps_in_second + (ref_second * np.uint64(1e12))
        
        # DEBUG: Check for timestamp issues
        if len(timestamps) > 10:
            logger.debug(f"First 10 timestamps: {timestamps[:10]}")
            logger.debug(f"Last 10 timestamps: {timestamps[-10:]}")
            
            # Check if timestamps are monotonically increasing
            if not np.all(np.diff(timestamps) >= 0):
                non_monotonic = np.sum(np.diff(timestamps) < 0)
                logger.warning(f"⚠️  {non_monotonic} timestamp decreases detected! "
                             f"Data may have counter resets or wrong format.")
        
        # Calculate file info
        time_span_sec = 0
        if len(timestamps) > 1:
            time_span_sec = (timestamps[-1] - timestamps[0]) / 1e12
        
        file_info = {
            'file_size_bytes': file_size,
            'num_timestamps': len(timestamps),
            'time_span_sec': time_span_sec,
            'first_timestamp': timestamps[0] if len(timestamps) > 0 else 0,
            'last_timestamp': timestamps[-1] if len(timestamps) > 0 else 0,
            'mean_rate_hz': len(timestamps) / time_span_sec if time_span_sec > 0 else 0
        }
        
        logger.info(f"File loaded: {len(timestamps)} timestamps, "
                   f"span={time_span_sec:.2f}s, rate={file_info['mean_rate_hz']:.0f} Hz")
        
        return timestamps, file_info
    
    def create_histogram_buffer(self, timestamps: np.ndarray) -> np.ndarray:
        """
        Convert timestamps to histogram bins for FFT.
        
        Matches C++ read_data() function:
        - Formula: bin_index = (timestamp + Tshift) / tau % N
        - Creates complex buffer with real part = counts, imaginary = 0
        
        Args:
            timestamps: Array of absolute timestamps in picoseconds
        
        Returns:
            Complex array of size N ready for FFT
        """
        logger.info(f"Creating histogram buffer for {len(timestamps)} timestamps")
        
        # Initialize complex buffer (matches fftw_complex in C++)
        buffer = np.zeros(self.N, dtype=np.complex128)
        
        # Bin timestamps using vectorized operations (1000x faster than Python loop)
        # Apply shift and calculate bin indices for all timestamps at once
        shifted_times = timestamps.astype(np.int64) + self.Tshift
        bin_indices = (shifted_times // self.tau) % self.N
        
        # Count timestamps in each bin using numpy's bincount (optimized C code)
        # This is equivalent to the loop but runs in compiled C code
        counts = np.bincount(bin_indices.astype(np.int64), minlength=self.N)
        buffer.real = counts[:self.N]  # Set real part to counts, imaginary stays 0
        
        # Log histogram statistics
        filled_bins = np.count_nonzero(buffer.real)
        max_count = np.max(buffer.real)
        mean_count = np.mean(buffer.real[buffer.real > 0]) if filled_bins > 0 else 0
        total_counts = np.sum(buffer.real)
        fill_ratio = filled_bins / self.N * 100
        
        logger.info(f"Histogram: {filled_bins}/{self.N} bins filled ({fill_ratio:.2f}%), "
                   f"max_count={max_count:.0f}, mean_count={mean_count:.2f}, total={total_counts:.0f}")
        
        # Check for wrap-around issues
        edge_bins = int(0.05 * self.N)  # 5% from edges
        counts_near_start = np.sum(buffer.real[:edge_bins])
        counts_near_end = np.sum(buffer.real[-edge_bins:])
        
        if counts_near_start > 0 and counts_near_end > 0:
            logger.warning(f"⚠️  Data near BOTH edges (start={counts_near_start:.0f}, end={counts_near_end:.0f}) - "
                         f"possible wrap-around! Consider adjusting Tshift or increasing N.")
        
        return buffer
    
    def calculate_cross_correlation(self, buff1: np.ndarray, buff2: np.ndarray) -> Tuple[np.ndarray, float, int]:
        """
        Compute FFT cross-correlation between two histogram buffers.
        
        Matches C++ CalculateDeltaT() function:
        1. Forward FFT on both buffers
        2. Multiply FFT(buff1) * conj(FFT(buff2))
        3. Inverse FFT to get correlation function
        4. Normalize by (value - mean) / std_dev
        5. Find peak
        
        Args:
            buff1: First histogram buffer (complex array)
            buff2: Second histogram buffer (complex array)
        
        Returns:
            Tuple of (correlation_function, peak_value_sigma, peak_index)
        """
        logger.info("Computing FFT cross-correlation...")
        
        # Step 1: Forward FFT
        logger.debug("Forward FFT...")
        fft1 = np.fft.fft(buff1)
        fft2 = np.fft.fft(buff2)
        
        # Step 2: Cross-correlation in frequency domain
        logger.debug("Computing cross-correlation in frequency domain...")
        cross_corr_freq = fft1 * np.conj(fft2)
        
        # Step 3: Inverse FFT
        logger.debug("Inverse FFT...")
        correlation = np.fft.ifft(cross_corr_freq)
        
        # Normalize by N (matches C++ cbuff[n][0] /= N)
        correlation = correlation / self.N
        
        # Take real part only (imaginary should be negligible)
        correlation_real = correlation.real
        
        # Step 4: Normalize by statistics (matches C++ S[n] = (cbuffr[n] - cmean) / cvar)
        mean = np.mean(correlation_real)
        std = np.std(correlation_real, ddof=1)  # ddof=1 for sample std (n-1 denominator)
        
        logger.info(f"Correlation stats: mean={mean:.6f}, std={std:.6f}")
        
        # Normalized correlation (in units of standard deviations)
        correlation_normalized = (correlation_real - mean) / std
        
        # Step 5: Find peak
        peak_index = np.argmax(correlation_normalized)
        peak_value = correlation_normalized[peak_index]
        
        logger.info(f"Peak found at index {peak_index}, value={peak_value:.2f}σ")
        
        return correlation_normalized, peak_value, peak_index
    
    def assess_confidence(self, peak_value: float, correlation_func: np.ndarray, 
                         peak_index: int) -> Dict[str, Any]:
        """
        Assess confidence in the correlation result.
        
        Args:
            peak_value: Peak value in standard deviations
            correlation_func: Full correlation function
            peak_index: Index of the peak
        
        Returns:
            Dict with confidence metrics
        """
        # Find second-highest peak (to check for ambiguity)
        correlation_copy = correlation_func.copy()
        correlation_copy[peak_index] = -np.inf
        second_peak_value = np.max(correlation_copy)
        second_peak_index = np.argmax(correlation_copy)
        
        # Calculate peak-to-second ratio
        peak_ratio = peak_value / second_peak_value if second_peak_value > 0 else np.inf
        
        # Determine confidence level
        if peak_value > 4.0 and peak_ratio > 1.5:
            confidence = "High"
            reliable = True
        elif peak_value > 3.0 and peak_ratio > 1.2:
            confidence = "Medium"
            reliable = True
        else:
            confidence = "Low"
            reliable = False
        
        # Check if peak is near edge (potential wrapping issue)
        edge_threshold = int(0.05 * self.N)  # 5% from edges
        near_edge = peak_index < edge_threshold or peak_index > (self.N - edge_threshold)
        
        if near_edge:
            logger.warning(f"⚠️  Peak at index {peak_index} is near edge (within 5% of boundaries). "
                         f"This suggests wrap-around issues. Try adjusting Tshift!")
        
        return {
            'confidence': confidence,
            'reliable': reliable,
            'peak_sigma': peak_value,
            'second_peak_sigma': second_peak_value,
            'peak_ratio': peak_ratio,
            'near_edge': near_edge,
            'second_peak_index': second_peak_index
        }
    
    def merge_timestamp_files(self, file_list: List[Path]) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Merge multiple timestamp files into a single sorted array.
        
        Used for multi-channel correlation: combine Ch1, Ch2, Ch3, Ch4 from same site.
        
        Args:
            file_list: List of timestamp file paths to merge
        
        Returns:
            Tuple of (merged_timestamps, combined_info)
        """
        if not file_list:
            raise ValueError("Empty file list provided")
        
        logger.info(f"Merging {len(file_list)} timestamp files...")
        
        all_timestamps = []
        total_events = 0
        file_infos = []
        
        for filepath in file_list:
            timestamps, info = self.read_timestamp_file(filepath)
            all_timestamps.append(timestamps)
            total_events += len(timestamps)
            file_infos.append(info)
            logger.info(f"  - {filepath.name}: {len(timestamps)} events")
        
        # Merge all arrays
        merged = np.concatenate(all_timestamps)
        
        # Sort by timestamp (important for correlation algorithm)
        merged = np.sort(merged)
        
        # Calculate combined statistics
        time_span_sec = (merged[-1] - merged[0]) / 1e12 if len(merged) > 1 else 0
        
        combined_info = {
            'num_files': len(file_list),
            'file_names': [f.name for f in file_list],
            'num_timestamps': len(merged),
            'time_span_sec': time_span_sec,
            'first_timestamp': merged[0] if len(merged) > 0 else 0,
            'last_timestamp': merged[-1] if len(merged) > 0 else 0,
            'mean_rate_hz': len(merged) / time_span_sec if time_span_sec > 0 else 0,
            'individual_file_info': file_infos
        }
        
        logger.info(f"Merged result: {len(merged)} total timestamps, span={time_span_sec:.2f}s")
        
        return merged, combined_info
    
    def run_correlation(self, local_files: List[Path], remote_files: List[Path]) -> Dict[str, Any]:
        """
        Main entry point - calculate time offset between timestamp file sets.
        
        Args:
            local_files: List of local site timestamp files (can be single file or multiple channels)
            remote_files: List of remote site timestamp files
        
        Returns:
            Dictionary with results:
            {
                'success': bool,
                'offset_ps': int,              # Time offset in picoseconds
                'offset_ms': float,            # Time offset in milliseconds
                'peak_index': int,             # kmax
                'peak_value': float,           # Peak strength (σ)
                'confidence': str,             # 'High', 'Medium', 'Low'
                'reliable': bool,              # Overall reliability flag
                'correlation_func': np.ndarray,  # For plotting
                'local_info': dict,            # Local file metadata
                'remote_info': dict,           # Remote file metadata
                'assessment': dict,            # Detailed confidence metrics
                'error': str or None           # Error message if failed
            }
        """
        try:
            logger.info("="*60)
            logger.info("Starting time offset correlation calculation")
            logger.info(f"Local files: {[f.name for f in local_files]}")
            logger.info(f"Remote files: {[f.name for f in remote_files]}")
            logger.info("="*60)
            
            # Step 1: Read and merge timestamp files
            if len(local_files) == 1:
                local_timestamps, local_info = self.read_timestamp_file(local_files[0])
            else:
                local_timestamps, local_info = self.merge_timestamp_files(local_files)
            
            if len(remote_files) == 1:
                remote_timestamps, remote_info = self.read_timestamp_file(remote_files[0])
            else:
                remote_timestamps, remote_info = self.merge_timestamp_files(remote_files)
            
            if len(local_timestamps) == 0 or len(remote_timestamps) == 0:
                raise ValueError("One or both file sets contain no timestamps")
            
            # Step 2: Create histogram buffers
            buff1 = self.create_histogram_buffer(local_timestamps)
            buff2 = self.create_histogram_buffer(remote_timestamps)
            
            # Step 3: Calculate cross-correlation
            correlation_func, peak_value, peak_index = self.calculate_cross_correlation(buff1, buff2)
            
            # Step 4: Calculate offset
            offset_ps = self.tau * peak_index
            offset_ms = offset_ps / 1e9  # Convert to milliseconds
            
            # Step 5: Assess confidence
            assessment = self.assess_confidence(peak_value, correlation_func, peak_index)
            
            logger.info("="*60)
            logger.info("RESULTS:")
            logger.info(f"Time Offset: {offset_ps:,} ps ({offset_ms:.3f} ms)")
            logger.info(f"Peak Index: {peak_index}")
            logger.info(f"Peak Strength: {peak_value:.2f}σ")
            logger.info(f"Confidence: {assessment['confidence']}")
            logger.info(f"Reliable: {assessment['reliable']}")
            logger.info("="*60)
            
            return {
                'success': True,
                'offset_ps': int(offset_ps),
                'offset_ms': float(offset_ms),
                'peak_index': int(peak_index),
                'peak_value': float(peak_value),
                'confidence': assessment['confidence'],
                'reliable': assessment['reliable'],
                'correlation_func': correlation_func,
                'local_info': local_info,
                'remote_info': remote_info,
                'assessment': assessment,
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Correlation calculation failed: {e}", exc_info=True)
            return {
                'success': False,
                'offset_ps': 0,
                'offset_ms': 0.0,
                'peak_index': 0,
                'peak_value': 0.0,
                'confidence': 'Error',
                'reliable': False,
                'correlation_func': None,
                'local_info': {},
                'remote_info': {},
                'assessment': {},
                'error': str(e)
            }
