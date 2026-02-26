"""
Live Offset Calibrator — FFT cross-correlation on live timestamp buffers.

Calculates per-pair time offsets from data already in TimestampBuffer objects,
eliminating all file I/O.  Reuses the proven FFT math from TimeOffsetCalculator
via composition.

USAGE (from GUI / PlotUpdater):
    calibrator = LiveOffsetCalibrator()          # uses LIVE_FFT_TAU / LIVE_FFT_N
    result = calibrator.calibrate_pair(local_ts, remote_ts)
    # result.offset_ps, result.confidence, result.peak_sigma, result.success

FFT PARAMETER RATIONALE (for known ~103 µs offset):
    τ  = 4 096 ps   (~4 ns bin width → plenty of resolution)
    N  = 2^17 = 131 072  bins
    Window = N×τ = 536 870 912 ps ≈ 537 µs → max detectable offset ±268 µs
    Memory per histogram: 131 072 × 8 bytes = 1 MB  (vs 64 MB with offline params)
    FFT time: ~2 ms  (vs ~200 ms)

The offline TimeOffsetCalculator (τ=2048, N=2^23) remains available for the
TimeOffsetTab file-based workflow — wider range (±8.6 ms) for unknown offsets.
"""

import numpy as np
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from time_offset_calculator import TimeOffsetCalculator

try:
    from gui_components.config import (
        LIVE_FFT_TAU, LIVE_FFT_N, CALIBRATION_DURATION_SEC, DEBUG_MODE
    )
except ImportError:
    LIVE_FFT_TAU = 4096
    LIVE_FFT_N = 2**17
    CALIBRATION_DURATION_SEC = 30
    DEBUG_MODE = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Result container
# ---------------------------------------------------------------------------

@dataclass
class CalibrationResult:
    """Result of a single pair calibration."""
    success: bool
    offset_ps: int = 0
    peak_sigma: float = 0.0
    confidence: str = "Unknown"       # "High" / "Medium" / "Low" / "Error"
    reliable: bool = False
    message: str = ""
    local_count: int = 0
    remote_count: int = 0
    elapsed_sec: float = 0.0
    # Detailed assessment from TimeOffsetCalculator
    assessment: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
#  Calibrator
# ---------------------------------------------------------------------------

class LiveOffsetCalibrator:
    """FFT cross-correlation on live numpy timestamp arrays.

    Uses optimised FFT parameters for the expected ~103 µs offset range,
    and delegates the actual FFT math to TimeOffsetCalculator.
    """

    def __init__(self, tau: int = None, N: int = None):
        """
        Args:
            tau: Bin width in picoseconds (default: LIVE_FFT_TAU from config)
            N:   Number of FFT bins   (default: LIVE_FFT_N   from config)
        """
        self.tau = tau or LIVE_FFT_TAU
        self.N = N or LIVE_FFT_N

        # Compose — reuse FFT math from TimeOffsetCalculator
        self._calc = TimeOffsetCalculator(tau=self.tau, N=self.N, Tshift=0)

        max_offset_us = (self.N * self.tau / 2) / 1e6
        logger.info(
            f"LiveOffsetCalibrator: τ={self.tau} ps, N={self.N}, "
            f"window=±{max_offset_us:.1f} µs, "
            f"resolution={self.tau/1e3:.1f} ns, "
            f"histogram={self.N * 8 / 1024:.0f} KB"
        )

    # ------------------------------------------------------------------
    #  Core: build histogram from in-memory timestamp array
    # ------------------------------------------------------------------

    def _build_histogram(self, timestamps_ps: np.ndarray) -> np.ndarray:
        """Bin raw picosecond timestamps into an FFT-ready histogram.

        Same maths as TimeOffsetCalculator.read_data_streaming() but works
        on a numpy array instead of a file.

        Args:
            timestamps_ps: 1-D int64 array of absolute timestamps in ps.

        Returns:
            float64 histogram of length N.
        """
        buf = np.zeros(self.N, dtype=np.float64)
        if len(timestamps_ps) == 0:
            return buf

        # bin_index = (total_ps / tau) % N   — identical to file reader
        indices = (timestamps_ps.astype(np.uint64) // np.uint64(self.tau)) % np.uint64(self.N)
        np.add.at(buf, indices.astype(np.int64), 1.0)

        if DEBUG_MODE:
            filled = np.count_nonzero(buf)
            logger.info(
                f"[DEBUG] Histogram: {len(timestamps_ps):,} ts → "
                f"{filled}/{self.N} bins filled ({filled/self.N*100:.1f}%), "
                f"max_count={np.max(buf):.0f}"
            )
        return buf

    # ------------------------------------------------------------------
    #  Calibrate a single pair
    # ------------------------------------------------------------------

    def calibrate_pair(
        self,
        local_ts: np.ndarray,
        remote_ts: np.ndarray,
    ) -> CalibrationResult:
        """Run FFT cross-correlation on two timestamp arrays.

        Args:
            local_ts:  int64 array — LOCAL  timestamps in ps (sorted).
            remote_ts: int64 array — REMOTE timestamps in ps (sorted).

        Returns:
            CalibrationResult with offset, confidence, etc.
        """
        t0 = time.perf_counter()

        # --- sanity checks ---
        if len(local_ts) == 0 or len(remote_ts) == 0:
            return CalibrationResult(
                success=False,
                message=f"Insufficient data (local={len(local_ts)}, remote={len(remote_ts)})",
                local_count=len(local_ts), remote_count=len(remote_ts),
            )

        logger.info(
            f"LiveCalibrator: local={len(local_ts):,} ts, remote={len(remote_ts):,} ts, "
            f"τ={self.tau}, N={self.N}"
        )

        try:
            # 1) Build histograms
            hist_local = self._build_histogram(local_ts)
            hist_remote = self._build_histogram(remote_ts)

            # 2) FFT cross-correlation (reuses proven TimeOffsetCalculator code)
            corr_func, peak_value, peak_index = self._calc.calculate_cross_correlation(
                hist_local, hist_remote
            )

            # 3) Wraparound handling (same as run_correlation)
            offset_pos = self.tau * peak_index
            offset_neg = self.tau * (peak_index - self.N)
            offset_ps = offset_neg if abs(offset_neg) < abs(offset_pos) else offset_pos

            # 4) Confidence assessment
            assessment = self._calc.assess_confidence(peak_value, corr_func, peak_index)

            elapsed = time.perf_counter() - t0

            # Format human-readable message
            if offset_ps >= 0:
                direction = f"remote AHEAD by {offset_ps/1e6:.3f} µs"
            else:
                direction = f"remote BEHIND by {-offset_ps/1e6:.3f} µs"

            msg = (
                f"Offset: {offset_ps:,} ps ({offset_ps/1e6:.3f} µs) — {direction}\n"
                f"Peak: {peak_value:.2f}σ, Confidence: {assessment['confidence']}\n"
                f"Computed in {elapsed*1000:.0f} ms"
            )

            logger.info(f"LiveCalibrator result: {offset_ps:,} ps, "
                        f"{peak_value:.2f}σ, {assessment['confidence']}, "
                        f"{elapsed*1000:.0f} ms")

            return CalibrationResult(
                success=True,
                offset_ps=int(offset_ps),
                peak_sigma=float(peak_value),
                confidence=assessment['confidence'],
                reliable=assessment['reliable'],
                message=msg,
                local_count=len(local_ts),
                remote_count=len(remote_ts),
                elapsed_sec=elapsed,
                assessment=assessment,
            )

        except Exception as e:
            elapsed = time.perf_counter() - t0
            logger.error(f"LiveCalibrator failed: {e}", exc_info=True)
            return CalibrationResult(
                success=False,
                message=f"Calibration error: {e}",
                local_count=len(local_ts),
                remote_count=len(remote_ts),
                elapsed_sec=elapsed,
            )

    # ------------------------------------------------------------------
    #  Calibrate all offset slots that have at least one pair using them
    # ------------------------------------------------------------------

    def calibrate_all(
        self,
        pairs: list,
        local_buffers: dict,
        remote_buffers: dict,
    ) -> Dict[int, CalibrationResult]:
        """Calibrate every offset slot referenced by the active pairs.

        For each unique offset_idx, finds the FIRST pair that uses it,
        extracts timestamps from the relevant buffers, and runs the FFT.

        Args:
            pairs:          List of 5-tuples (src_a, ch_a, src_b, ch_b, offset_idx)
            local_buffers:  {ch: TimestampBuffer}  — local channels
            remote_buffers: {ch: TimestampBuffer}  — remote channels

        Returns:
            {offset_idx: CalibrationResult}
        """
        # Group pairs by offset_idx (first pair per slot wins)
        slot_pairs: Dict[int, tuple] = {}
        for src_a, ch_a, src_b, ch_b, ofs_idx in pairs:
            if ofs_idx not in slot_pairs:
                slot_pairs[ofs_idx] = (src_a, ch_a, src_b, ch_b)

        results: Dict[int, CalibrationResult] = {}
        for ofs_idx, (src_a, ch_a, src_b, ch_b) in slot_pairs.items():
            bufs_a = local_buffers if src_a == "L" else remote_buffers
            bufs_b = local_buffers if src_b == "L" else remote_buffers

            ts_a = bufs_a[ch_a].get_timestamps() if ch_a in bufs_a else np.array([], dtype=np.int64)
            ts_b = bufs_b[ch_b].get_timestamps() if ch_b in bufs_b else np.array([], dtype=np.int64)

            logger.info(f"Calibrating offset slot {ofs_idx+1} from "
                        f"{src_a}{ch_a}↔{src_b}{ch_b}: "
                        f"a={len(ts_a):,}, b={len(ts_b):,}")

            results[ofs_idx] = self.calibrate_pair(ts_a, ts_b)

        return results
