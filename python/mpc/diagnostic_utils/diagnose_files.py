"""
Standalone diagnostic tool for timestamp file analysis.

Run this script to validate and diagnose timestamp binary files.
Helps identify corruption, data quality issues, and compatibility problems.

Usage:
    cd Quantum/python/mpc
    python -m diagnostic_utils.diagnose_files <file1.bin> [file2.bin]
    
    Or set DEBUG_MODE = True in gui_components/config.py and run the GUI
"""

import sys
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('file_diagnostics.log', mode='w')
    ]
)

logger = logging.getLogger(__name__)

# Import validation tools
try:
    from .file_validator import TimestampFileValidator
except ImportError:
    # If run directly, adjust path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from diagnostic_utils.file_validator import TimestampFileValidator


def main():
    """Run diagnostic analysis on timestamp files."""
    print("\n" + "="*80)
    print("TIMESTAMP FILE DIAGNOSTIC TOOL")
    print("="*80)
    
    if len(sys.argv) < 2:
        print("\nUsage: python -m diagnostic_utils.diagnose_files <file1.bin> [file2.bin]")
        print("\nExample:")
        print("  cd Quantum/python/mpc")
        print("  python -m diagnostic_utils.diagnose_files data/timestamps_bme_C1.bin")
        print("  python -m diagnostic_utils.diagnose_files local.bin remote.bin")
        sys.exit(1)
    
    file1 = Path(sys.argv[1])
    file2 = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    
    # Validate first file
    print(f"\n{'='*80}")
    print(f"ANALYZING FILE 1: {file1.name}")
    print(f"{'='*80}\n")
    
    val1 = TimestampFileValidator.validate_file(file1, max_samples=10000)
    TimestampFileValidator.print_validation_report(file1, val1)
    
    # Validate second file if provided
    if file2:
        print(f"\n{'='*80}")
        print(f"ANALYZING FILE 2: {file2.name}")
        print(f"{'='*80}\n")
        
        val2 = TimestampFileValidator.validate_file(file2, max_samples=10000)
        TimestampFileValidator.print_validation_report(file2, val2)
        
        # Compare files
        print(f"\n{'='*80}")
        print(f"COMPATIBILITY ANALYSIS")
        print(f"{'='*80}\n")
        
        comparison = TimestampFileValidator.compare_files(file1, file2)
        
        if comparison['compatible']:
            print("✅ Files appear compatible for correlation analysis")
        else:
            print("❌ Files may NOT be compatible for correlation")
        
        print(f"\nTime Overlap:")
        print(f"  File 1 span: {comparison['info']['file1_span_sec']:.2f} seconds")
        print(f"  File 2 span: {comparison['info']['file2_span_sec']:.2f} seconds")
        print(f"  Overlap: {comparison['info']['overlap_sec']:.2f} seconds "
              f"({comparison['info']['overlap_percentage_file1']:.1f}% of file1, "
              f"{comparison['info']['overlap_percentage_file2']:.1f}% of file2)")
        
        print(f"\nRate Analysis:")
        print(f"  File 1 rate: {comparison['info']['rate1_hz']:.1f} Hz")
        print(f"  File 2 rate: {comparison['info']['rate2_hz']:.1f} Hz")
        print(f"  Rate ratio: {comparison['info']['rate_ratio']:.3f}")
        
        if comparison['issues']:
            print(f"\n⚠️  Issues Detected:")
            for issue in comparison['issues']:
                print(f"  • {issue}")
    
    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}\n")
    
    if val1['valid'] and (not file2 or val2['valid']):
        print("✅ All files passed validation")
        
        if file2 and not comparison['compatible']:
            print("⚠️  However, files may not be compatible for correlation")
            print("   Check the compatibility analysis above for details")
    else:
        print("❌ One or more files FAILED validation")
        print("   Files may be corrupted or in wrong format")
        print("   Expected format: binary [timestamp_ps:uint64, ref_second:uint64] pairs")
    
    print(f"\nDiagnostic log saved to: file_diagnostics.log")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
