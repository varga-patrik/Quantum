"""
Quick integration test for LiveOffsetCalibrator with mock data.

Verifies that the calibrator can detect per-channel offsets from
MockTimeController-generated timestamps.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import time
from streaming.live_offset_calibrator import LiveOffsetCalibrator, CalibrationResult
from streaming.timestamp_stream import TimestampBuffer
from mock_time_controller import MockTimeController
from gui_components.config import MOCK_CHANNEL_OFFSETS_PS


def generate_mock_data(channel: int, site: str, duration_sec: float = 30.0) -> TimestampBuffer:
    """Generate mock timestamps for a channel using MockTimeController."""
    mock = MockTimeController(site_name=site)
    buf = TimestampBuffer(channel, max_duration_sec=duration_sec + 5, max_size=10_000_000)
    
    # Generate in 0.1s chunks (like the real streaming)
    chunk_ps = int(0.1 * 1e12)
    n_chunks = int(duration_sec / 0.1)
    for _ in range(n_chunks):
        data = mock.generate_timestamps(channel, chunk_ps, with_ref_index=True)
        buf.add_timestamps(data, with_ref_index=True)
    
    return buf


def main():
    print("=" * 70)
    print("LiveOffsetCalibrator Integration Test")
    print("=" * 70)
    print(f"\nExpected per-channel offsets: {MOCK_CHANNEL_OFFSETS_PS}")
    print(f"Generating 30s of mock data per channel...\n")
    
    calibrator = LiveOffsetCalibrator()
    
    results = {}
    for ch in [1, 2, 3, 4]:
        expected_offset = MOCK_CHANNEL_OFFSETS_PS.get(ch, 0)
        print(f"--- Channel {ch} (expected offset: {expected_offset:,} ps = {expected_offset/1e6:.1f} µs) ---")
        
        t0 = time.perf_counter()
        
        # Generate data for both sites
        local_buf = generate_mock_data(ch, "CLIENT", duration_sec=30.0)
        remote_buf = generate_mock_data(ch, "SERVER", duration_sec=30.0)
        gen_time = time.perf_counter() - t0
        
        local_ts = local_buf.get_timestamps()
        remote_ts = remote_buf.get_timestamps()
        
        print(f"  Data: local={len(local_ts):,} ts, remote={len(remote_ts):,} ts ({gen_time:.1f}s to generate)")
        
        # Run calibration
        result = calibrator.calibrate_pair(local_ts, remote_ts)
        results[ch] = result
        
        if result.success:
            error_ps = result.offset_ps - expected_offset
            error_us = error_ps / 1e6
            print(f"  Result: {result.offset_ps:,} ps ({result.offset_ps/1e6:.3f} µs)")
            print(f"  Confidence: {result.confidence} ({result.peak_sigma:.1f}σ)")
            print(f"  Error: {error_ps:,} ps ({error_us:.3f} µs)")
            print(f"  Compute time: {result.elapsed_sec*1000:.0f} ms")
            
            if abs(error_us) < 10:  # Within 10 µs
                print(f"  ✅ PASS")
            else:
                print(f"  ❌ FAIL — error too large!")
        else:
            print(f"  ❌ FAILED: {result.message}")
        print()
    
    print("=" * 70)
    print("SUMMARY:")
    for ch, result in results.items():
        expected = MOCK_CHANNEL_OFFSETS_PS.get(ch, 0)
        if result.success:
            error = abs(result.offset_ps - expected)
            status = "✅" if error < 10_000_000 else "❌"  # within 10 µs
            print(f"  Ch{ch}: expected={expected/1e6:.1f}µs, got={result.offset_ps/1e6:.1f}µs, "
                  f"error={error/1e6:.3f}µs {status}")
        else:
            print(f"  Ch{ch}: FAILED")
    print("=" * 70)


if __name__ == "__main__":
    main()
