"""Settings for the whole program."""

# Debug mode - set to True for extensive logging
DEBUG_MODE = True  # Set to True to enable detailed diagnostic logs

# Hardware IP addresses for SERVER side (Wigner)
SERVER_TC_ADDRESS = "148.6.27.28"
SERVER_FS740_ADDRESS = "148.6.27.165"

# Hardware IP addresses for CLIENT side (BME)
#CLIENT_TC_ADDRESS = "169.254.104.112"
CLIENT_TC_ADDRESS = "172.26.34.114"
CLIENT_FS740_ADDRESS = "172.26.34.159" 

# Default fallback addresses (used if role not set)
DEFAULT_TC_ADDRESS = SERVER_TC_ADDRESS
DEFAULT_FS740_ADDRESS = SERVER_FS740_ADDRESS
DEFAULT_FS740_PORT = 5025

# Measurement defaults
DEFAULT_ACQ_DURATION = 0.5
DEFAULT_BIN_WIDTH = 100
DEFAULT_BIN_COUNT = 20
DEFAULT_HISTOGRAMS = [1, 2, 3, 4]

# Timestamp streaming settings
COINCIDENCE_WINDOW_PS = 10000  # coincidence window in picoseconds
TIMESTAMP_BUFFER_DURATION_SEC = 12.0  # Local buffer: must be longer than network pipeline delay (~6.5s) so old local data can overlap with delayed remote data
REMOTE_BUFFER_DURATION_SEC = 12.0  # Remote buffer: accumulates multiple batch arrivals (batches arrive every ~6.5s, each covering ~3s)
TIMESTAMP_BUFFER_MAX_SIZE = 10_000_000  # Max timestamps per channel (safety limit)
TIMESTAMP_BATCH_INTERVAL_SEC = 0.1  # Send batches to peer every 0.1 seconds (10 Hz)
STREAM_PORTS_BASE = 4241  # Time Controller streaming ports: 4242, 4243, 4244, 4245

# Live offset calibration
# Duration in seconds to accumulate data before running FFT calibration
CALIBRATION_DURATION_SEC = 300

# Live FFT calibration parameters — optimised for expected ~103 µs offset
# tau=4096 ps, N=2^17=131072 → window ≈ 537 µs (±268 µs), resolution ≈ 4 ns
LIVE_FFT_TAU = 4096
LIVE_FFT_N = 2**17  # 131_072

# Mock Time Controller correlation mode (only used when real hardware unavailable)
# 'cross_site': Site A and Site B detect same photon events (quantum entanglement)
#               → Site A Ch1 correlates with Site B Ch1 (with time offset)
# 'local_pairs': Ch1↔Ch2 and Ch3↔Ch4 correlate locally within each site
MOCK_CORRELATION_MODE = 'cross_site'  # MUST be 'cross_site' or 'local_pairs'

# Mock time offset between sites (in picoseconds)
# Server (Wigner) will be this many picoseconds LATER than Client (BME)
# Used as fallback when MOCK_CHANNEL_OFFSETS_PS is not defined for a channel.
MOCK_TIME_OFFSET_PS = 103673856

# Per-channel mock offsets (in picoseconds) for testing per-pair calibration.
# Each channel can have a DIFFERENT offset so calibration can be verified per-pair.
# Only applied on the SERVER side; CLIENT is always the reference (0 offset).
MOCK_CHANNEL_OFFSETS_PS = {
    1: 103_000_000,   # Ch1: 103.0 µs  (realistic BME↔Wigner range)
    2: 107_500_000,   # Ch2: 107.5 µs  (slightly different cable/detector)
    3:  98_200_000,   # Ch3:  98.2 µs
    4: 110_800_000,   # Ch4: 110.8 µs
}

# Theme colors
BG_COLOR = '#1E1E1E'
FG_COLOR = '#D4D4D4'
HIGHLIGHT_COLOR = '#2E2E2E'
PRIMARY_COLOR = '#282828'
ACTION_COLOR = '#007ACC'

# Plot settings
CORRELATION_COLORS = ['blue', 'green', 'red', 'yellow']
CORRELATION_LABELS = [
    '1-3 koincidencia',
    '1-4 koincidencia',
    '2-3 koincidencia',
    '2-4 koincidencia'
]
HISTOGRAM_COLORS = ['blue', 'green', 'red', 'yellow']
HISTOGRAM_LABELS = ['1-3', '1-4', '2-3', '2-4']

# Default device serials for local optimizer rows (serial, channel)
DEFAULT_LOCAL_SERIALS = [
    ("00000000", 1),
    ("38290024", 2),
    ("00000000", 3),
    ("38442764", 4)
]

# Default device serials for remote optimizer rows (serial, channel)
# These are placeholders - update with actual serial numbers
DEFAULT_REMOTE_SERIALS = [
    ("38532504", 1),
    ("38530254", 2),
    ("38521084", 3),
    ("38530684", 4)
]

# Legacy alias for backward compatibility
DEFAULT_SERIALS = DEFAULT_LOCAL_SERIALS
