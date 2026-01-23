"""
Debug script to inspect raw timestamps from binary files.
Prints first N timestamps from two files to diagnose time offset issues.
"""

import numpy as np
from pathlib import Path
import sys


def read_first_timestamps(filepath: Path, num_to_read: int = 10):
    """
    Read first N timestamp pairs from binary file.
    
    Args:
        filepath: Path to binary timestamp file
        num_to_read: Number of timestamp pairs to read
    
    Returns:
        List of tuples (ps_in_second, ref_second, total_ps)
    """
    if not filepath.exists():
        print(f"ERROR: File not found: {filepath}")
        return []
    
    file_size = filepath.stat().st_size
    num_pairs = file_size // 16  # Each pair is 2x uint64 = 16 bytes
    
    print(f"\nFile: {filepath.name}")
    print(f"  Size: {file_size:,} bytes ({file_size / 1024**2:.2f} MB)")
    print(f"  Total pairs: {num_pairs:,}")
    
    # Read first N pairs
    num_to_read = min(num_to_read, num_pairs)
    bytes_to_read = num_to_read * 2 * 8  # 2 uint64 per pair, 8 bytes each
    
    timestamps = []
    
    with open(filepath, 'rb') as f:
        raw_bytes = f.read(bytes_to_read)
        
        # Show first 128 raw bytes in hex
        print(f"\n  First {min(128, len(raw_bytes))} raw bytes (hex):")
        for i in range(0, min(128, len(raw_bytes)), 16):
            hex_str = ' '.join(f'{b:02x}' for b in raw_bytes[i:i+16])
            print(f"    Offset {i:04d}: {hex_str}")
        
        raw_values = np.frombuffer(raw_bytes, dtype=np.uint64)
        
        # Show raw uint64 values before parsing
        print(f"\n  Raw uint64 values (first {min(20, len(raw_values))}):")
        for i in range(min(20, len(raw_values))):
            print(f"    [{i:2d}] {raw_values[i]:20d}  (0x{raw_values[i]:016x})")
        
        ps_values = raw_values[0::2]  # Picoseconds within second (even indices: 0,2,4,6...)
        sec_values = raw_values[1::2]  # Second counter (odd indices: 1,3,5,7...)
        
        print(f"\n  Parsed as timestamp pairs:")
        print(f"    ps_values (even indices):  {ps_values[:min(5, len(ps_values))]}")
        print(f"    sec_values (odd indices):  {sec_values[:min(5, len(sec_values))]}")
        
        for i in range(len(ps_values)):
            ps = int(ps_values[i])
            sec = int(sec_values[i])
            total_ps = ps + (sec * int(1e12))
            timestamps.append((ps, sec, total_ps))
    
    return timestamps


def format_timestamp(ps_in_sec, ref_sec, total_ps):
    """Format timestamp for display."""
    total_sec = total_ps / 1e12
    return (f"  sec={ref_sec:8d}, ps_in_sec={ps_in_sec:12d}, "
            f"total_ps={total_ps:18d} ({total_sec:.6f} s)")


def compare_files(file1: Path, file2: Path, num_to_read: int = 10):
    """
    Compare timestamps from two files.
    
    Args:
        file1: First timestamp file (e.g., local/BME)
        file2: Second timestamp file (e.g., remote/Wigner)
        num_to_read: Number of timestamps to display
    """
    print("="*80)
    print("TIMESTAMP FILE COMPARISON")
    print("="*80)
    
    # Read both files
    ts1 = read_first_timestamps(file1, num_to_read)
    ts2 = read_first_timestamps(file2, num_to_read)
    
    if not ts1 or not ts2:
        print("\nERROR: Could not read one or both files")
        return
    
    # Display File 1
    print(f"\n{'='*80}")
    print(f"FILE 1: {file1.name}")
    print(f"{'='*80}")
    print("\nFirst timestamps:")
    for i, (ps, sec, total) in enumerate(ts1[:num_to_read]):
        print(f"[{i}] {format_timestamp(ps, sec, total)}")
    
    # Display File 2
    print(f"\n{'='*80}")
    print(f"FILE 2: {file2.name}")
    print(f"{'='*80}")
    print("\nFirst timestamps:")
    for i, (ps, sec, total) in enumerate(ts2[:num_to_read]):
        print(f"[{i}] {format_timestamp(ps, sec, total)}")
    
    # Calculate differences
    print(f"\n{'='*80}")
    print("ANALYSIS")
    print(f"{'='*80}")
    
    # First timestamp difference
    first_diff_ps = ts2[0][2] - ts1[0][2]
    first_diff_ms = first_diff_ps / 1e9
    first_diff_sec = first_diff_ps / 1e12
    
    print(f"\nFirst timestamp difference (File2 - File1):")
    print(f"  {first_diff_ps:,} ps")
    print(f"  {first_diff_ms:.6f} ms")
    print(f"  {first_diff_sec:.9f} seconds")
    
    if first_diff_ps > 0:
        print(f"  → File2 starts AFTER File1 by {abs(first_diff_ms):.6f} ms")
    else:
        print(f"  → File2 starts BEFORE File1 by {abs(first_diff_ms):.6f} ms")
    
    # Check time span of displayed timestamps
    if len(ts1) > 1:
        span1_ps = ts1[-1][2] - ts1[0][2]
        span1_ms = span1_ps / 1e9
        print(f"\nFile1 time span (first {len(ts1)} events): {span1_ms:.6f} ms")
    
    if len(ts2) > 1:
        span2_ps = ts2[-1][2] - ts2[0][2]
        span2_ms = span2_ps / 1e9
        print(f"File2 time span (first {len(ts2)} events): {span2_ms:.6f} ms")
    
    # Read last timestamps for overall span
    print(f"\n{'='*80}")
    print("READING LAST TIMESTAMPS FOR OVERALL SPAN...")
    print(f"{'='*80}")
    
    last1 = read_last_timestamps(file1, 5)
    last2 = read_last_timestamps(file2, 5)
    
    if last1 and last2:
        print(f"\nFile1 last timestamps:")
        for i, (ps, sec, total) in enumerate(last1):
            print(f"  [{i}] {format_timestamp(ps, sec, total)}")
        
        print(f"\nFile2 last timestamps:")
        for i, (ps, sec, total) in enumerate(last2):
            print(f"  [{i}] {format_timestamp(ps, sec, total)}")
        
        total_span1 = last1[-1][2] - ts1[0][2]
        total_span2 = last2[-1][2] - ts2[0][2]
        
        print(f"\nFile1 total span: {total_span1 / 1e12:.3f} seconds")
        print(f"File2 total span: {total_span2 / 1e12:.3f} seconds")
        
        overlap_start = max(ts1[0][2], ts2[0][2])
        overlap_end = min(last1[-1][2], last2[-1][2])
        overlap = overlap_end - overlap_start
        
        if overlap > 0:
            print(f"\nTemporal overlap: {overlap / 1e12:.3f} seconds")
        else:
            print(f"\n⚠️  WARNING: Files do NOT overlap in time!")
            print(f"   Gap: {abs(overlap) / 1e12:.3f} seconds")
    
    # Read timestamps from middle of file to see ref_second incrementing
    print(f"\n{'='*80}")
    print("SAMPLES FROM MIDDLE OF FILES (to see ref_second increment)")
    print(f"{'='*80}")
    
    file1_size = file1.stat().st_size // 16
    file2_size = file2.stat().st_size // 16
    
    # Sample at 1 second, 10 seconds, 100 seconds, etc.
    for time_sec in [1, 10, 100, 300]:
        # Estimate position: assume ~10kHz rate
        est_pairs = time_sec * 10000
        
        if est_pairs < file1_size:
            print(f"\nFile1 around {time_sec} seconds (~pair {est_pairs:,}):")
            mid1 = read_timestamps_at_offset(file1, est_pairs, 3)
            for i, (ps, sec, total) in enumerate(mid1):
                print(f"  {format_timestamp(ps, sec, total)}")
        
        if est_pairs < file2_size:
            print(f"\nFile2 around {time_sec} seconds (~pair {est_pairs:,}):")
            mid2 = read_timestamps_at_offset(file2, est_pairs, 3)
            for i, (ps, sec, total) in enumerate(mid2):
                print(f"  {format_timestamp(ps, sec, total)}")


def read_timestamps_at_offset(filepath: Path, pair_offset: int, num_to_read: int = 10):
    """Read N timestamp pairs starting at a specific pair offset."""
    if not filepath.exists():
        return []
    
    file_size = filepath.stat().st_size
    num_pairs = file_size // 16
    
    if pair_offset >= num_pairs:
        print(f"  Offset {pair_offset} exceeds file size ({num_pairs} pairs)")
        return []
    
    num_to_read = min(num_to_read, num_pairs - pair_offset)
    seek_bytes = pair_offset * 16
    
    timestamps = []
    
    with open(filepath, 'rb') as f:
        f.seek(seek_bytes)
        raw_bytes = f.read(num_to_read * 16)
        raw_values = np.frombuffer(raw_bytes, dtype=np.uint64)
        
        ps_values = raw_values[0::2]
        sec_values = raw_values[1::2]
        
        for i in range(len(ps_values)):
            ps = int(ps_values[i])
            sec = int(sec_values[i])
            total_ps = ps + (sec * int(1e12))
            timestamps.append((ps, sec, total_ps))
    
    return timestamps


def read_last_timestamps(filepath: Path, num_to_read: int = 5):
    """Read last N timestamp pairs from file."""
    if not filepath.exists():
        return []
    
    file_size = filepath.stat().st_size
    num_pairs = file_size // 16
    
    if num_pairs < num_to_read:
        num_to_read = num_pairs
    
    # Seek to position for last N pairs
    skip_pairs = num_pairs - num_to_read
    
    return read_timestamps_at_offset(filepath, skip_pairs, num_to_read)


def export_to_txt(filepath: Path, output_path: Path = None, max_lines: int = 1000):
    """
    Export binary timestamp file to human-readable text format.
    
    Args:
        filepath: Path to binary timestamp file
        output_path: Output text file path (defaults to same name with .txt)
        max_lines: Maximum number of timestamp lines to export (None for all)
    """
    if not filepath.exists():
        print(f"ERROR: File not found: {filepath}")
        return
    
    if output_path is None:
        output_path = filepath.with_suffix('.txt')
    
    file_size = filepath.stat().st_size
    num_pairs = file_size // 16
    
    print(f"\nExporting {filepath.name} to text format...")
    print(f"  Total timestamps: {num_pairs:,}")
    
    if max_lines is not None and num_pairs > max_lines:
        print(f"  Limiting to first {max_lines:,} lines")
        num_pairs = max_lines
    
    with open(filepath, 'rb') as f_in, open(output_path, 'w') as f_out:
        # Write header
        f_out.write(f"# Timestamp file: {filepath.name}\n")
        f_out.write(f"# Format: index, ref_second, ps_in_second, total_ps, total_seconds\n")
        f_out.write(f"# Total timestamps: {num_pairs:,}\n")
        f_out.write("#" + "="*78 + "\n\n")
        
        # Process in chunks
        chunk_size = 10000
        processed = 0
        
        while processed < num_pairs:
            chunk = min(chunk_size, num_pairs - processed)
            raw_bytes = f_in.read(chunk * 16)
            
            if not raw_bytes:
                break
            
            raw_values = np.frombuffer(raw_bytes, dtype=np.uint64)
            ps_values = raw_values[0::2]
            sec_values = raw_values[1::2]
            
            for i in range(len(ps_values)):
                ps = int(ps_values[i])
                sec = int(sec_values[i])
                total_ps = ps + (sec * int(1e12))
                total_sec = total_ps / 1e12
                
                idx = processed + i
                f_out.write(f"{idx:8d}  {sec:8d}  {ps:12d}  {total_ps:18d}  {total_sec:15.6f}\n")
            
            processed += len(ps_values)
            
            if processed % 50000 == 0:
                print(f"  Processed {processed:,} / {num_pairs:,} timestamps...")
    
    print(f"\n✓ Exported to: {output_path}")
    print(f"  File size: {output_path.stat().st_size / 1024:.1f} KB")


def main():
    """Main entry point."""
    if len(sys.argv) >= 2:
        # Check if export mode
        if sys.argv[1] == "export" or sys.argv[1] == "--export":
            if len(sys.argv) < 3:
                print("Usage: python debug_timestamps.py export <file.bin> [max_lines]")
                return
            
            bin_file = Path(sys.argv[2])
            max_lines = int(sys.argv[3]) if len(sys.argv) > 3 else None
            export_to_txt(bin_file, max_lines=max_lines)
            return
        
        # Compare mode
        if len(sys.argv) >= 3:
            file1 = Path(sys.argv[1])
            file2 = Path(sys.argv[2])
            num_to_read = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        else:
            print("Usage:")
            print("  Compare: python debug_timestamps.py <file1> <file2> [num_to_read]")
            print("  Export:  python debug_timestamps.py export <file.bin> [max_lines]")
            return
    else:
        # Default paths - modify these to your actual files
        print("Usage:")
        print("  Compare: python debug_timestamps.py <file1> <file2> [num_to_read]")
        print("  Export:  python debug_timestamps.py export <file.bin> [max_lines]")
        print("\nTrying default paths for comparison...")
        
        # Example default paths - adjust to your setup
        data_dir = Path(r"C:/Users/kvantum/Documents/AgodSolt/data/10min")
        
        if not data_dir.exists():
            data_dir = Path.home() / "Documents" / "AgodSolt" / "data"
        
        if not data_dir.exists():
            print(f"\nERROR: Data directory not found: {data_dir}")
            print("\nPlease specify files manually:")
            print("  python debug_timestamps.py <local_file.bin> <remote_file.bin>")
            return
        
        # Find most recent BME and Wigner files for channel 1
        bme_files = sorted(data_dir.glob("*bme*C1*.bin"), 
                          key=lambda f: f.stat().st_mtime, reverse=True)
        wigner_files = sorted(data_dir.glob("*wigner*C1*.bin"), 
                             key=lambda f: f.stat().st_mtime, reverse=True)
        
        if not bme_files or not wigner_files:
            print(f"\nERROR: Could not find timestamp files in {data_dir}")
            print("\nPlease specify files manually:")
            print("  python debug_timestamps.py <local_file.bin> <remote_file.bin>")
            return
        
        file1 = bme_files[0]
        file2 = wigner_files[0]
        num_to_read = 10
        
        print(f"Using files:")
        print(f"  File1 (BME):    {file1}")
        print(f"  File2 (Wigner): {file2}")
    
    compare_files(file1, file2, num_to_read)


if __name__ == "__main__":
    main()
