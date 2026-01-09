"""
Time Offset Calculator - FFT Cross-Correlation Algorithm

Replicates the C++ Correlator::CalculateDeltaT() function to automatically
calculate time offset between two sites' timestamp streams.
"""

import numpy as np
import struct
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

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
            Tshift: Initial time shift guess in picoseconds (default: 100 ms)
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
        
        # Read entire file (or use memory mapping for very large files)
        with open(filepath, 'rb') as f:
            data = f.read(num_values * 8)
        
        # Unpack as uint64 pairs
        raw_values = struct.unpack(f'<{num_values}Q', data)
        
        # Convert to absolute timestamps
        timestamps = []
        for i in range(0, len(raw_values), 2):
            ps_in_second = raw_values[i]
            ref_second = raw_values[i + 1]
            
            # Calculate absolute timestamp in picoseconds
            total_ps = ps_in_second + (ref_second * int(1e12))
            timestamps.append(total_ps)
        
        timestamps = np.array(timestamps, dtype=np.uint64)
        
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
        
        # Bin each timestamp
        for ts in timestamps:
            # Apply shift and calculate bin index
            shifted_time = ts + self.Tshift
            bin_index = int(shifted_time // self.tau) % self.N
            
            # Increment count (real part only, imaginary stays 0)
            buffer[bin_index] += 1.0
        
        # Log histogram statistics
        filled_bins = np.count_nonzero(buffer.real)
        max_count = np.max(buffer.real)
        mean_count = np.mean(buffer.real[buffer.real > 0]) if filled_bins > 0 else 0
        
        logger.info(f"Histogram: {filled_bins}/{self.N} bins filled, "
                   f"max_count={max_count:.0f}, mean_count={mean_count:.2f}")
        
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
        
        return {
            'confidence': confidence,
            'reliable': reliable,
            'peak_sigma': peak_value,
            'second_peak_sigma': second_peak_value,
            'peak_ratio': peak_ratio,
            'near_edge': near_edge,
            'second_peak_index': second_peak_index
        }
    
    def run_correlation(self, local_file: Path, remote_file: Path) -> Dict[str, Any]:
        """
        Main entry point - calculate time offset between two timestamp files.
        
        Args:
            local_file: Path to local site timestamp file
            remote_file: Path to remote site timestamp file
        
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
            logger.info(f"Local file: {local_file.name}")
            logger.info(f"Remote file: {remote_file.name}")
            logger.info("="*60)
            
            # Step 1: Read timestamp files
            local_timestamps, local_info = self.read_timestamp_file(local_file)
            remote_timestamps, remote_info = self.read_timestamp_file(remote_file)
            
            if len(local_timestamps) == 0 or len(remote_timestamps) == 0:
                raise ValueError("One or both files contain no timestamps")
            
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
