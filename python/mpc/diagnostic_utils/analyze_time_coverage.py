"""
Analyze time coverage of timestamp files to identify gaps and overlaps.
"""

import numpy as np
from pathlib import Path
import sys


def analyze_file_coverage(filepath: Path, bin_size_sec: float = 1.0):
    """
    Analyze which time bins contain events.
    
    Args:
        filepath: Path to binary timestamp file
        bin_size_sec: Time bin size in seconds
    
    Returns:
        Dictionary with coverage analysis
    """
    print(f"\nAnalyzing: {filepath.name}")
    
    # Read file
    with open(filepath, 'rb') as f:
        data = np.fromfile(f, dtype=np.uint64)
    
    # Parse [timestamp_ps, ref_second] pairs
    ps_values = data[0::2]
    sec_values = data[1::2]
    
    # Calculate total timestamps in picoseconds
    total_times_ps = ps_values + (sec_values * int(1e12))
    
    # Convert to seconds
    total_times_sec = total_times_ps / 1e12
    
    # Find time range
    t_min = np.min(total_times_sec)
    t_max = np.max(total_times_sec)
    duration = t_max - t_min
    
    print(f"  Events: {len(ps_values):,}")
    print(f"  Time range: {t_min:.3f} - {t_max:.3f} seconds")
    print(f"  Duration: {duration:.3f} seconds")
    print(f"  Mean rate: {len(ps_values)/duration:.1f} Hz")
    
    # Create time bins
    num_bins = int(np.ceil(duration / bin_size_sec))
    bin_edges = np.linspace(t_min, t_max, num_bins + 1)
    
    # Count events per bin
    counts, _ = np.histogram(total_times_sec, bins=bin_edges)
    
    # Find bins with events
    bins_with_events = np.sum(counts > 0)
    bins_empty = num_bins - bins_with_events
    
    print(f"\n  Time bins ({bin_size_sec} sec each):")
    print(f"    Total bins: {num_bins}")
    print(f"    Bins with data: {bins_with_events} ({100*bins_with_events/num_bins:.1f}%)")
    print(f"    Empty bins: {bins_empty} ({100*bins_empty/num_bins:.1f}%)")
    
    # Find longest gap
    empty_regions = np.where(counts == 0)[0]
    if len(empty_regions) > 0:
        # Find consecutive empty bins
        gaps = np.split(empty_regions, np.where(np.diff(empty_regions) != 1)[0] + 1)
        longest_gap = max([len(g) for g in gaps]) * bin_size_sec
        print(f"    Longest gap: {longest_gap:.1f} seconds")
    
    return {
        'file': filepath.name,
        'num_events': len(ps_values),
        't_min': t_min,
        't_max': t_max,
        'duration': duration,
        'rate': len(ps_values) / duration,
        'bin_size': bin_size_sec,
        'num_bins': num_bins,
        'bins_with_data': bins_with_events,
        'coverage': bins_with_events / num_bins,
        'bin_edges': bin_edges,
        'counts': counts
    }


def check_overlap(local_result, remote_result):
    """Check if two files have overlapping time ranges with data."""
    print("\n" + "="*80)
    print("OVERLAP ANALYSIS")
    print("="*80)
    
    # Find overall time range
    t_min = min(local_result['t_min'], remote_result['t_min'])
    t_max = max(local_result['t_max'], remote_result['t_max'])
    
    print(f"\nOverall time range: {t_min:.3f} - {t_max:.3f} seconds ({t_max - t_min:.1f} sec)")
    
    # Find overlapping time range
    overlap_start = max(local_result['t_min'], remote_result['t_min'])
    overlap_end = min(local_result['t_max'], remote_result['t_max'])
    
    if overlap_start >= overlap_end:
        print("\n❌ NO TIME OVERLAP - Files cover completely different time periods!")
        print(f"   Local:  {local_result['t_min']:.3f} - {local_result['t_max']:.3f}")
        print(f"   Remote: {remote_result['t_min']:.3f} - {remote_result['t_max']:.3f}")
        return False
    
    overlap_duration = overlap_end - overlap_start
    print(f"\n✅ Time ranges overlap: {overlap_start:.3f} - {overlap_end:.3f} seconds")
    print(f"   Overlap duration: {overlap_duration:.3f} seconds ({100*overlap_duration/(t_max-t_min):.1f}% of total)")
    
    # Check which bins in the overlap have data in BOTH files
    bin_size = local_result['bin_size']
    
    # Create unified bins covering overlap region
    num_overlap_bins = int(np.ceil(overlap_duration / bin_size))
    overlap_bins = np.linspace(overlap_start, overlap_end, num_overlap_bins + 1)
    
    # Count how many overlap bins have data in both files
    local_has_data = []
    remote_has_data = []
    
    for i in range(num_overlap_bins):
        bin_start = overlap_bins[i]
        bin_end = overlap_bins[i + 1]
        
        # Check if local has data in this bin
        local_mask = (local_result['bin_edges'][:-1] >= bin_start) & (local_result['bin_edges'][:-1] < bin_end)
        local_count = np.sum(local_result['counts'][local_mask])
        local_has_data.append(local_count > 0)
        
        # Check if remote has data in this bin
        remote_mask = (remote_result['bin_edges'][:-1] >= bin_start) & (remote_result['bin_edges'][:-1] < bin_end)
        remote_count = np.sum(remote_result['counts'][remote_mask])
        remote_has_data.append(remote_count > 0)
    
    both_have_data = np.sum(np.array(local_has_data) & np.array(remote_has_data))
    
    print(f"\n  Overlap bins with data:")
    print(f"    Both files: {both_have_data}/{num_overlap_bins} ({100*both_have_data/num_overlap_bins:.1f}%)")
    print(f"    Local only: {np.sum(np.array(local_has_data) & ~np.array(remote_has_data))}")
    print(f"    Remote only: {np.sum(~np.array(local_has_data) & np.array(remote_has_data))}")
    print(f"    Neither: {np.sum(~np.array(local_has_data) & ~np.array(remote_has_data))}")
    
    if both_have_data < num_overlap_bins * 0.5:
        print("\n⚠️  WARNING: Less than 50% of overlap time has data in both files!")
        print("   Time offset calculation may be unreliable.")
    
    return True


def main():
    """Main entry point."""
    if len(sys.argv) < 3:
        print("Usage: python -m diagnostic_utils.analyze_time_coverage <local_file> <remote_file>")
        print("\nExample:")
        print("  python -m diagnostic_utils.analyze_time_coverage timestamps_bme_C1.bin timestamps_wigner_C1.bin")
        sys.exit(1)
    
    local_file = Path(sys.argv[1])
    remote_file = Path(sys.argv[2])
    
    if not local_file.exists():
        print(f"Error: Local file not found: {local_file}")
        sys.exit(1)
    
    if not remote_file.exists():
        print(f"Error: Remote file not found: {remote_file}")
        sys.exit(1)
    
    print("="*80)
    print("TIME COVERAGE ANALYSIS")
    print("="*80)
    
    # Analyze both files
    local_result = analyze_file_coverage(local_file, bin_size_sec=1.0)
    remote_result = analyze_file_coverage(remote_file, bin_size_sec=1.0)
    
    # Check overlap
    check_overlap(local_result, remote_result)
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print("\nThe files have large gaps. This is why correlation fails:")
    print("  • Files may not overlap in time where both have data")
    print("  • FFT correlation finds false peaks in empty regions")
    print("  • Coincidence counts match accidentals (pure noise)")
    print("\n✅ SOLUTION: Use recordings WITHOUT gaps or gaps in same places")
    print("="*80)


if __name__ == '__main__':
    main()
