"""
Plot ref_second progression to diagnose GPS sync issues.

This script reads a timestamp file and plots how ref_second changes over time,
helping identify if GPS synchronization is working properly.
"""

import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import sys


def plot_ref_second_progression(filepath: Path, max_events: int = 1000000):
    """
    Plot ref_second values over the course of the file.
    
    Args:
        filepath: Path to binary timestamp file
        max_events: Maximum number of events to plot (for memory efficiency)
    """
    print(f"Reading file: {filepath.name}")
    
    # Read file
    with open(filepath, 'rb') as f:
        data = np.fromfile(f, dtype=np.uint64)
    
    # Parse [timestamp_ps, ref_second] pairs
    ps_values = data[0::2]
    sec_values = data[1::2]
    
    total_events = len(ps_values)
    print(f"Total events: {total_events:,}")
    
    # Sample if too many events
    if total_events > max_events:
        print(f"Sampling {max_events:,} events for plotting...")
        indices = np.linspace(0, total_events - 1, max_events, dtype=int)
        ps_values = ps_values[indices]
        sec_values = sec_values[indices]
        event_indices = indices
    else:
        event_indices = np.arange(total_events)
    
    # Calculate total time in seconds (event index / total_events * file_duration_estimate)
    # We'll estimate file duration from first and last timestamps
    total_times_ps = ps_values.astype(np.uint64) + (sec_values.astype(np.uint64) * np.uint64(int(1e12)))
    time_span_sec = (total_times_ps[-1] - total_times_ps[0]) / 1e12
    
    print(f"Time span: {time_span_sec:.2f} seconds")
    print(f"ref_second range: [{np.min(sec_values)}, {np.max(sec_values)}]")
    print(f"Unique ref_second values: {len(np.unique(sec_values))}")
    
    # Calculate approximate time axis (seconds since start)
    time_axis = event_indices / total_events * time_span_sec
    
    # Create figure with multiple subplots
    fig, axes = plt.subplots(3, 1, figsize=(14, 10))
    fig.suptitle(f"GPS Sync Diagnosis: {filepath.name}", fontsize=14, fontweight='bold')
    
    # Plot 1: ref_second over time
    ax1 = axes[0]
    ax1.plot(time_axis, sec_values, 'b.', markersize=1, alpha=0.5)
    ax1.set_xlabel('Time since start (seconds)')
    ax1.set_ylabel('ref_second value')
    ax1.set_title('ref_second Progression (Should increase linearly if GPS sync works)')
    ax1.grid(True, alpha=0.3)
    
    # Add expected line if ref_second should match elapsed time
    if time_span_sec > 0:
        expected = time_axis
        ax1.plot(time_axis, expected, 'r--', linewidth=2, alpha=0.7, label='Expected (perfect GPS sync)')
        ax1.legend()
    
    # Plot 2: Histogram of ref_second values
    ax2 = axes[1]
    unique_secs, counts = np.unique(sec_values, return_counts=True)
    ax2.bar(unique_secs, counts, width=0.8, color='green', alpha=0.6)
    ax2.set_xlabel('ref_second value')
    ax2.set_ylabel('Number of events')
    ax2.set_title(f'Distribution of ref_second values ({len(unique_secs)} unique values)')
    ax2.grid(True, alpha=0.3, axis='y')
    
    # Plot 3: ps_values distribution (check if they're properly distributed in [0, 1e12])
    ax3 = axes[2]
    ax3.hist(ps_values / 1e12, bins=100, color='orange', alpha=0.6, edgecolor='black')
    ax3.set_xlabel('ps_value (seconds, should be in [0, 1])')
    ax3.set_ylabel('Frequency')
    ax3.set_title('Distribution of picosecond values within each second')
    ax3.set_xlim([0, 1])
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Save plot
    output_path = filepath.parent / f"{filepath.stem}_ref_second_diagnosis.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\nPlot saved to: {output_path}")
    
    # Diagnosis
    print("\n" + "="*70)
    print("DIAGNOSIS:")
    print("="*70)
    
    if np.all(sec_values == 0):
        print("❌ CRITICAL: All ref_second values are 0!")
        print("   GPS synchronization is NOT working.")
        print("   Check your timestamp acquisition script - it's not getting GPS time.")
    elif len(unique_secs) == 1:
        print(f"⚠️  WARNING: Only ONE unique ref_second value: {unique_secs[0]}")
        print("   GPS sync appears frozen or not incrementing.")
    elif np.max(sec_values) - np.min(sec_values) < time_span_sec * 0.5:
        print(f"⚠️  WARNING: ref_second range ({np.max(sec_values) - np.min(sec_values)}) ")
        print(f"   is much smaller than time span ({time_span_sec:.1f}s)")
        print("   GPS sync may not be working correctly.")
    else:
        print("✅ ref_second values look reasonable - GPS sync appears to be working.")
        # Check if ref_second increments properly
        if np.all(np.diff(sec_values) >= 0):
            print("✅ ref_second values are monotonically increasing.")
        else:
            print("⚠️  WARNING: ref_second values are not monotonic (timestamps may be out of order).")
    
    print("="*70)
    
    plt.show()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m diagnostic_utils.plot_ref_seconds <timestamp_file.bin>")
        print("\nExample:")
        print("  python -m diagnostic_utils.plot_ref_seconds data/timestamps_bme_01-23_15-14-47_C1.bin")
        sys.exit(1)
    
    filepath = Path(sys.argv[1])
    
    if not filepath.exists():
        print(f"Error: File not found: {filepath}")
        sys.exit(1)
    
    plot_ref_second_progression(filepath)
