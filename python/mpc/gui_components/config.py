"""GUI configuration constants and theme settings."""

# Default Time Controller IP address
DEFAULT_TC_ADDRESS = "169.254.104.112"

# Measurement defaults
DEFAULT_ACQ_DURATION = 0.5
DEFAULT_BIN_WIDTH = 100
DEFAULT_BIN_COUNT = 20
DEFAULT_HISTOGRAMS = [1, 2, 3, 4]

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
    ("38530254", 1),
    ("38532504", 2),
    ("38521084", 3),
    ("38530684", 4)
]

# Default device serials for remote optimizer rows (serial, channel)
# These are placeholders - update with actual serial numbers
DEFAULT_REMOTE_SERIALS = [
    ("38442764", 1),
    ("00000000", 2),
    ("00000000", 3),
    ("38290024", 4)
]

# Legacy alias for backward compatibility
DEFAULT_SERIALS = DEFAULT_LOCAL_SERIALS
