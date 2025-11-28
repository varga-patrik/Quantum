"""GUI configuration constants and theme settings."""

# Hardware IP addresses for SERVER side (Wigner)
SERVER_TC_ADDRESS = "148.6.27.28"
SERVER_FS740_ADDRESS = "148.6.27.165"

# Hardware IP addresses for CLIENT side (BME)
CLIENT_TC_ADDRESS = "169.254.104.112"
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
COINCIDENCE_WINDOW_PS = 1000  # ±1ns coincidence window in picoseconds (tau)
TIMESTAMP_BUFFER_DURATION_SEC = 1.0  # Keep 1 second of timestamps in memory
TIMESTAMP_BUFFER_MAX_SIZE = 10_000_000  # Max timestamps per channel (safety limit)
TIMESTAMP_BATCH_INTERVAL_SEC = 0.5  # Send batches to peer every 0.5 seconds
STREAM_PORTS_BASE = 4241  # Time Controller streaming ports: 4242, 4243, 4244, 4245

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
