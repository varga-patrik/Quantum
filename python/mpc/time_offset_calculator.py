"""
Time Offset Calculator - FFT Cross-Correlation Algorithm

Replicates the C++ Correlator::CalculateDeltaT() function to automatically
calculate time offset between two sites' timestamp streams.

This implementation matches the C++ version exactly:
- Streaming file reads (low memory usage)
- Full complex FFT (matching FFTW behavior)
"""

import numpy as np
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
import gc

logger = logging.getLogger(__name__)


class TimeOffsetCalculator:
    """
    FFT-based cross-correlation calculator for timestamp synchronization.
    
    - Streaming file reads to minimize memory usage
    - Full complex DFT (not real FFT) to match FFTW behavior
    - Same binning and correlation formula
    """
    
    def __init__(self, tau: int = 2048, N: int = 2**23, Tshift: int = 0):
        """
        Initialize calculator with correlation parameters.
        
        Args:
            tau: Bin width in picoseconds (default: 2048 ps = 2.048 ns)
            N: Number of FFT bins (default: 2^23 = 8,388,608)
            Tshift: Initial time shift in picoseconds (default: 0)
        """
        self.tau = tau
        self.N = N
        self.Tshift = Tshift
        self.chunk_size = 100_000  # Read files in chunks (matches C++ approach)
        
        logger.info(f"TimeOffsetCalculator initialized: tau={tau}ps, N={N}, Tshift={Tshift}ps")
    
    def read_data_streaming(self, filepath: Path) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Read binary file and create histogram buffer using streaming (low memory).
        
        - Reads in chunks (doesn't load whole file into memory)
        - Directly bins into histogram: totalTime = (ps + Tshift) + (second * 1e12)
        - bin_index = (totalTime / tau) % N
        
        Args:
            filepath: Path to binary timestamp file
        
        Returns:
            Tuple of (histogram_buffer, file_info)
            - histogram_buffer: float64 array of size N with counts
            - file_info: metadata dict
        """
        logger.info(f"Reading timestamp file (streaming): {filepath}")
        
        if not filepath.exists():
            raise FileNotFoundError(f"Timestamp file not found: {filepath}")
        
        file_size = filepath.stat().st_size
        num_values = file_size // 8  # uint64 = 8 bytes
        num_pairs = num_values // 2
        
        logger.info(f"Reading {num_pairs:,} timestamp pairs ({file_size / 1024**2:.1f} MB)")
        
        # Initialize histogram buffer
        buffer = np.zeros(self.N, dtype=np.float64)
        
        # Track statistics
        total_events = 0
        first_timestamp = None
        last_timestamp = None
        
        # Read in chunks
        chunk_size = self.chunk_size * 2  # Each pair is 2 uint64 values
        
        with open(filepath, 'rb') as f:
            while True:
                # Read chunk of raw uint64 values
                raw_bytes = f.read(chunk_size * 8)
                if not raw_bytes:
                    break
                
                # Convert to numpy array
                raw_values = np.frombuffer(raw_bytes, dtype=np.uint64)
                num_read = len(raw_values)
                
                if num_read < 2:
                    break
                
                # Ensure we have even number of values (pairs)
                if num_read % 2 != 0:
                    num_read -= 1
                    raw_values = raw_values[:num_read]
                
                # Process pairs: [ps_in_second, ref_second, ps_in_second, ref_second, ...]
                ps_values = raw_values[0::2]  # Even indices: picoseconds within second
                sec_values = raw_values[1::2]  # Odd indices: second counter
                
                # Calculate total time and bin indices
                total_times = (ps_values.astype(np.uint64) + np.uint64(self.Tshift)) + \
                             (sec_values.astype(np.uint64) * np.uint64(int(1e12)))
                bin_indices = (total_times // np.uint64(self.tau)) % np.uint64(self.N)
                total_times = (ps_values.astype(np.uint64) + np.uint64(self.Tshift)) + \
                             (sec_values.astype(np.uint64) * np.uint64(int(1e12)))
                bin_indices = (total_times // np.uint64(self.tau)) % np.uint64(self.N)
                
                # Count into histogram
                np.add.at(buffer, bin_indices.astype(np.int64), 1.0)
                
                total_events += len(ps_values)
                
                # Track first/last timestamps for info
                if first_timestamp is None:
                    first_timestamp = int(total_times[0])
                last_timestamp = int(total_times[-1])
        
        # Calculate file info
        time_span_sec = 0
        if first_timestamp is not None and last_timestamp is not None:
            time_span_sec = (last_timestamp - first_timestamp) / 1e12
        
        file_info = {
            'file_size_bytes': file_size,
            'num_timestamps': total_events,
            'time_span_sec': time_span_sec,
            'first_timestamp': first_timestamp or 0,
            'last_timestamp': last_timestamp or 0,
            'mean_rate_hz': total_events / time_span_sec if time_span_sec > 0 else 0
        }
        
        # Log histogram statistics
        filled_bins = np.count_nonzero(buffer)
        max_count = np.max(buffer)
        total_counts = np.sum(buffer)
        fill_ratio = filled_bins / self.N * 100
        
        logger.info(f"File loaded: {total_events} timestamps, span={time_span_sec:.2f}s, "
                   f"rate={file_info['mean_rate_hz']:.0f} Hz")
        logger.info(f"Histogram: {filled_bins}/{self.N} bins filled ({fill_ratio:.2f}%), "
                   f"max_count={max_count:.0f}, total={total_counts:.0f}")
        
        return buffer, file_info
    
    def merge_data_streaming(self, file_list: List[Path]) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Merge multiple timestamp files into a single histogram buffer using streaming.
        
        Memory-efficient: reads each file in chunks, accumulates into single histogram.
        
        Args:
            file_list: List of timestamp file paths to merge
        
        Returns:
            Tuple of (histogram_buffer, combined_info)
        """
        if not file_list:
            raise ValueError("Empty file list provided")
        
        logger.info(f"Merging {len(file_list)} timestamp files (streaming)...")
        
        # Initialize combined histogram buffer
        buffer = np.zeros(self.N, dtype=np.float64)
        
        total_events = 0
        first_timestamp = None
        last_timestamp = None
        file_infos = []
        
        for filepath in file_list:
            file_buffer, file_info = self.read_data_streaming(filepath)
            
            # Add to combined histogram
            buffer += file_buffer
            
            total_events += file_info['num_timestamps']
            file_infos.append(file_info)
            
            if first_timestamp is None or file_info['first_timestamp'] < first_timestamp:
                first_timestamp = file_info['first_timestamp']
            if last_timestamp is None or file_info['last_timestamp'] > last_timestamp:
                last_timestamp = file_info['last_timestamp']
            
            logger.info(f"  - {filepath.name}: {file_info['num_timestamps']} events")
            
            del file_buffer  # Free memory
        
        time_span_sec = (last_timestamp - first_timestamp) / 1e12 if first_timestamp and last_timestamp else 0
        
        combined_info = {
            'num_files': len(file_list),
            'file_names': [f.name for f in file_list],
            'num_timestamps': total_events,
            'time_span_sec': time_span_sec,
            'first_timestamp': first_timestamp or 0,
            'last_timestamp': last_timestamp or 0,
            'mean_rate_hz': total_events / time_span_sec if time_span_sec > 0 else 0,
            'individual_file_info': file_infos
        }
        
        logger.info(f"Merged result: {total_events} total timestamps, span={time_span_sec:.2f}s")
        
        return buffer, combined_info
    
    def calculate_cross_correlation(self, buff1: np.ndarray, buff2: np.ndarray) -> Tuple[np.ndarray, float, int]:
        """
        Compute FFT cross-correlation between two histogram buffers.
        
        1. Forward FFT on both buffers (full complex FFT)
        2. Cross-multiply: cbuff_c[k] = buff1_c[k] * conj(buff2_c[k])
           This is buff1 * conj(buff2) in complex notation
        3. Inverse FFT to get correlation function
        4. Divide by N (after inverse)
        5. Normalize by (value - mean) / std_dev
        6. Find peak
        
        Args:
            buff1: First histogram buffer (float64 array of counts)
            buff2: Second histogram buffer (float64 array of counts)
        
        Returns:
            Tuple of (correlation_function, peak_value_sigma, peak_index)
        """
        logger.info("Computing FFT cross-correlation (matching C++ exactly)...")
        
        # Step 1: Forward FFT on both buffers
        logger.debug("Forward FFT...")
        fft1 = np.fft.fft(buff1)  # Full complex FFT (matches FFTW on real data)
        fft2 = np.fft.fft(buff2)
        
        # Step 2: Cross-correlation in frequency domain
        logger.debug("Computing cross-correlation...")
        cbuff_c = np.conj(fft1) * fft2
        
        # Free FFT buffers
        del fft1, fft2
        gc.collect()
        
        # Step 3: Inverse FFT
        logger.debug("Inverse FFT...")
        cbuff = np.fft.ifft(cbuff_c) * self.N  # Multiply by N to match FFTW behavior
        del cbuff_c
        gc.collect()
        
        # Step 4: Divide by N and take real part
        cbuffr = (cbuff.real / self.N).copy()
        del cbuff
        gc.collect()
        
        # Step 5: Calculate mean and variance (standard deviation)
        cmean = np.mean(cbuffr)
        cvar = np.std(cbuffr, ddof=1)
        
        logger.info(f"Correlation stats: MEAN={cmean:.10e}, VAR(std)={cvar:.10e}")
        
        # Step 6: Normalize
        S = (cbuffr - cmean) / cvar
        del cbuffr
        gc.collect()
        
        # Step 7: Find maximum
        peak_index = int(np.argmax(S))
        peak_value = float(S[peak_index])
        
        logger.info(f"Peak found at index {peak_index}, value={peak_value:.2f}σ")
        
        return S, peak_value, peak_index
    
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
        del correlation_copy
        
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
    
    def run_correlation(self, local_files: List[Path], remote_files: List[Path]) -> Dict[str, Any]:
        """
        Main entry point - calculate time offset between timestamp file sets.
        
        Uses streaming reads to minimize memory usage for large files.
        
        Args:
            local_files: List of local site timestamp files (can be single file or multiple channels)
            remote_files: List of remote site timestamp files
        
        Returns:
            Dictionary with results including offset, peak value, confidence, etc.
        """
        try:
            logger.info("="*60)
            logger.info("Starting time offset correlation calculation")
            logger.info(f"Local files: {[f.name for f in local_files]}")
            logger.info(f"Remote files: {[f.name for f in remote_files]}")
            logger.info(f"Parameters: tau={self.tau}ps, N={self.N}, Tshift={self.Tshift}ps")
            logger.info("="*60)
            
            # Step 1: Read files and create histogram buffers (streaming)
            if len(local_files) == 1:
                buff1, local_info = self.read_data_streaming(local_files[0])
            else:
                buff1, local_info = self.merge_data_streaming(local_files)
            
            gc.collect()
            
            if len(remote_files) == 1:
                buff2, remote_info = self.read_data_streaming(remote_files[0])
            else:
                buff2, remote_info = self.merge_data_streaming(remote_files)
            
            gc.collect()
            
            if local_info['num_timestamps'] == 0 or remote_info['num_timestamps'] == 0:
                raise ValueError("One or both file sets contain no timestamps")
            
            # Step 2: Calculate cross-correlation
            correlation_func, peak_value, peak_index = self.calculate_cross_correlation(buff1, buff2)
            del buff1, buff2
            gc.collect()
            
            # Step 3: Calculate offset
            offset_ps = self.tau * peak_index
            offset_ms = offset_ps / 1e9  # Convert to milliseconds
            
            # Step 4: Assess confidence
            assessment = self.assess_confidence(peak_value, correlation_func, peak_index)
            
            logger.info("="*60)
            logger.info("RESULTS:")
            logger.info(f"Time Offset: {offset_ps:,} ps ({offset_ms:.6f} ms)")
            logger.info(f"Peak Index (kmax): {peak_index}")
            logger.info(f"Peak Strength: {peak_value:.2f}σ")
            logger.info(f"Confidence: {assessment['confidence']}")
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
