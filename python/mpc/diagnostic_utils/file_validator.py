"""
File validation utilities for timestamp binary files.

Checks for corruption, data sanity, and provides diagnostic information.
"""

import numpy as np
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


class TimestampFileValidator:
    """Validates binary timestamp files for corruption and data quality."""
    
    @staticmethod
    def validate_file(filepath: Path, max_samples: int = 10000) -> Dict:
        """
        Comprehensive validation of a timestamp binary file.
        
        Args:
            filepath: Path to the binary file
            max_samples: Number of samples to check (0 = all)
        
        Returns:
            Dictionary with validation results and diagnostics
        """
        result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'info': {},
            'samples': {}
        }
        
        try:
            # Check file exists and size
            if not filepath.exists():
                result['valid'] = False
                result['errors'].append(f"File not found: {filepath}")
                return result
            
            file_size = filepath.stat().st_size
            result['info']['file_size_bytes'] = file_size
            result['info']['file_size_mb'] = file_size / (1024 * 1024)
            
            # Check if size is multiple of 16 bytes (2x uint64)
            if file_size % 16 != 0:
                result['valid'] = False
                result['errors'].append(
                    f"File size {file_size} is not multiple of 16 bytes. "
                    f"Expected [timestamp_ps, ref_second] pairs. Remainder: {file_size % 16} bytes"
                )
                return result
            
            num_pairs = file_size // 16
            result['info']['num_timestamp_pairs'] = num_pairs
            
            if num_pairs == 0:
                result['valid'] = False
                result['errors'].append("File is empty (0 timestamp pairs)")
                return result
            
            logger.info(f"Validating {filepath.name}: {num_pairs:,} timestamp pairs ({file_size/1024/1024:.2f} MB)")
            
            # Read and validate data
            samples_to_read = min(max_samples, num_pairs) if max_samples > 0 else num_pairs
            
            # Read from beginning, middle, and end
            validation_result = TimestampFileValidator._validate_data_samples(
                filepath, num_pairs, samples_to_read
            )
            
            result.update(validation_result)
            
        except Exception as e:
            result['valid'] = False
            result['errors'].append(f"Validation exception: {str(e)}")
            logger.error(f"File validation failed for {filepath}: {e}", exc_info=True)
        
        return result
    
    @staticmethod
    def _validate_data_samples(filepath: Path, total_pairs: int, num_samples: int) -> Dict:
        """Validate all timestamp data in the file."""
        result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'info': {},
            'samples': {}
        }
        
        try:
            # Read entire file for accurate statistics
            logger.info(f"Reading entire file for validation: {total_pairs:,} pairs")
            with open(filepath, 'rb') as f:
                data = np.fromfile(f, dtype=np.uint64)
            
            # Parse [timestamp_ps, ref_second] pairs
            all_ps = data[0::2]
            all_sec = data[1::2]
            
            # Convert to total timestamps (ps + sec*1e12)
            total_times_ps = all_ps.astype(np.uint64) + (all_sec.astype(np.uint64) * np.uint64(int(1e12)))
            
            # Validate timestamp ordering (check full timestamps, not just ps values)
            is_sorted = np.all(total_times_ps[1:] >= total_times_ps[:-1])
            result['info']['timestamps_sorted'] = is_sorted
            if not is_sorted:
                result['warnings'].append("Timestamps are not monotonically increasing")
            
            # Calculate statistics using full timestamps
            first_time = total_times_ps[0]
            last_time = total_times_ps[-1]
            time_span_ps = last_time - first_time
            time_span_sec = float(time_span_ps / 1e12)
            
            result['info']['first_timestamp_ps'] = int(first_time)
            result['info']['last_timestamp_ps'] = int(last_time)
            result['info']['time_span_sec'] = time_span_sec
            result['info']['mean_rate_hz'] = len(all_ps) / time_span_sec if time_span_sec > 0 else 0
            
            # Check for reasonable ref_second values
            unique_secs = np.unique(all_sec)
            result['info']['num_unique_ref_seconds'] = len(unique_secs)
            result['info']['ref_second_min'] = int(np.min(all_sec))
            result['info']['ref_second_max'] = int(np.max(all_sec))
            
            # Check for zeros (might indicate bad data)
            num_zero_ps = np.sum(all_ps == 0)
            # Calculate inter-event times using full timestamps
            if len(total_times_ps) > 1:
                diffs = np.diff(total_times_ps.astype(np.int64))
                
                # Check for negative differences (non-monotonic)
                num_negative = np.sum(diffs < 0)
                if num_negative > 0:
                    result['warnings'].append(f"{num_negative} negative time differences (timestamps go backwards)")
                
                # Check for suspiciously large gaps
                positive_diffs = diffs[diffs > 0]
                if len(positive_diffs) > 0:
                    result['info']['mean_interval_ps'] = float(np.mean(positive_diffs))
                    result['info']['median_interval_ps'] = float(np.median(positive_diffs))
                    result['info']['max_gap_ps'] = float(np.max(positive_diffs))
                    result['info']['max_gap_sec'] = float(np.max(positive_diffs) / 1e12)
                    
                    # Flag if max gap > 1 second (might indicate missing data)
                    if result['info']['max_gap_sec'] > 1.0:
                        result['warnings'].append(
                            f"Large time gap detected: {result['info']['max_gap_sec']:.2f} seconds"
                        )
                
                # Analyze data coverage (check for regions with no events)
                # Bin into 1-second intervals
                num_bins = int(np.ceil(time_span_sec))
                if num_bins > 0 and num_bins < 100000:  # Sanity check
                    bin_edges = np.linspace(0, time_span_ps, num_bins + 1)
                    counts, _ = np.histogram(total_times_ps - first_time, bins=bin_edges)
                    empty_bins = np.sum(counts == 0)
                    if empty_bins > num_bins * 0.1:  # More than 10% empty
                        result['warnings'].append(
                            f"Sparse data coverage: {empty_bins}/{num_bins} seconds ({100*empty_bins/num_bins:.1f}%) have no events"
                        )
            
            # Store sample data
            result['samples']['first_10_ps'] = all_ps[:10].tolist()
            result['samples']['first_10_sec'] = all_sec[:10].tolist()
            result['samples']['last_10_ps'] = all_ps[-10:].tolist()
            result['samples']['last_10_sec'] = all_sec[-10:].tolist()
            
        except Exception as e:
            result['valid'] = False
            result['errors'].append(f"Data validation failed: {str(e)}")
            logger.error(f"Data validation error: {e}", exc_info=True)
        
        return result
    
    @staticmethod
    def _read_chunk(file, start_pair_idx: int, num_pairs: int) -> Dict:
        """Read a chunk of timestamp pairs."""
        raw_bytes = file.read(num_pairs * 16)
        raw_values = np.frombuffer(raw_bytes, dtype=np.uint64)
        
        if len(raw_values) % 2 != 0:
            raw_values = raw_values[:-1]
        
        ps_values = raw_values[0::2]
        sec_values = raw_values[1::2]
        
        # Convert to absolute picoseconds
        total_ps = ps_values.astype(np.uint64) + (sec_values.astype(np.uint64) * np.uint64(int(1e12)))
        
        return {
            'ps': total_ps,
            'sec': sec_values
        }
    
    @staticmethod
    def compare_files(file1: Path, file2: Path) -> Dict:
        """
        Compare two timestamp files to check if they're compatible for correlation.
        
        Returns diagnostics about time overlap, rate compatibility, etc.
        """
        result = {
            'compatible': True,
            'issues': [],
            'info': {}
        }
        
        # Validate both files
        val1 = TimestampFileValidator.validate_file(file1)
        val2 = TimestampFileValidator.validate_file(file2)
        
        if not val1['valid'] or not val2['valid']:
            result['compatible'] = False
            result['issues'].append("One or both files failed validation")
            result['file1_validation'] = val1
            result['file2_validation'] = val2
            return result
        
        # Check time overlap
        f1_start = val1['info']['first_timestamp_ps']
        f1_end = val1['info']['last_timestamp_ps']
        f2_start = val2['info']['first_timestamp_ps']
        f2_end = val2['info']['last_timestamp_ps']
        
        # Calculate overlap
        overlap_start = max(f1_start, f2_start)
        overlap_end = min(f1_end, f2_end)
        overlap_ps = max(0, overlap_end - overlap_start)
        
        result['info']['file1_span_sec'] = val1['info']['time_span_sec']
        result['info']['file2_span_sec'] = val2['info']['time_span_sec']
        result['info']['overlap_sec'] = overlap_ps / 1e12
        result['info']['overlap_percentage_file1'] = 100 * overlap_ps / (f1_end - f1_start) if (f1_end > f1_start) else 0
        result['info']['overlap_percentage_file2'] = 100 * overlap_ps / (f2_end - f2_start) if (f2_end > f2_start) else 0
        
        if overlap_ps <= 0:
            result['compatible'] = False
            result['issues'].append("No time overlap between files")
        elif result['info']['overlap_sec'] < 60:
            result['issues'].append(f"Limited time overlap: {result['info']['overlap_sec']:.1f} seconds")
        
        # Check rate compatibility
        rate1 = val1['info']['mean_rate_hz']
        rate2 = val2['info']['mean_rate_hz']
        
        result['info']['rate1_hz'] = rate1
        result['info']['rate2_hz'] = rate2
        result['info']['rate_ratio'] = rate1 / rate2 if rate2 > 0 else 0
        
        # Flag if rates are extremely different (might indicate different measurement types)
        if rate1 > 0 and rate2 > 0:
            ratio = max(rate1, rate2) / min(rate1, rate2)
            if ratio > 100:
                result['issues'].append(
                    f"Large rate mismatch: {rate1:.0f} Hz vs {rate2:.0f} Hz (ratio: {ratio:.1f}x)"
                )
        
        return result
    
    @staticmethod
    def print_validation_report(filepath: Path, validation: Dict):
        """Print a human-readable validation report."""
        print(f"\n{'='*70}")
        print(f"VALIDATION REPORT: {filepath.name}")
        print(f"{'='*70}")
        
        if validation['valid']:
            print("✅ File appears valid")
        else:
            print("❌ File validation FAILED")
        
        print(f"\n📊 File Info:")
        for key, value in validation['info'].items():
            if isinstance(value, float):
                if 'sec' in key.lower() and value > 1:
                    print(f"  {key}: {value:.2f}")
                elif 'hz' in key.lower():
                    print(f"  {key}: {value:.1f}")
                else:
                    print(f"  {key}: {value:,.0f}")
            elif isinstance(value, int):
                print(f"  {key}: {value:,}")
            else:
                print(f"  {key}: {value}")
        
        if validation['errors']:
            print(f"\n❌ Errors ({len(validation['errors'])}):")
            for err in validation['errors']:
                print(f"  • {err}")
        
        if validation['warnings']:
            print(f"\n⚠️  Warnings ({len(validation['warnings'])}):")
            for warn in validation['warnings']:
                print(f"  • {warn}")
        
        if validation['samples']:
            print(f"\n🔍 Sample Data:")
            if 'first_10_ps' in validation['samples']:
                print(f"  First 3 timestamps (ps): {validation['samples']['first_10_ps'][:3]}")
                print(f"  First 3 ref_seconds: {validation['samples']['first_10_sec'][:3]}")
                print(f"  Last 3 timestamps (ps): {validation['samples']['last_10_ps'][-3:]}")
        
        print(f"{'='*70}\n")
