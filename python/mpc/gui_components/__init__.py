"""GUI components package for the MPC320 controller application."""

from .config import (
    DEFAULT_TC_ADDRESS,
    DEFAULT_ACQ_DURATION,
    DEFAULT_BIN_WIDTH,
    DEFAULT_BIN_COUNT,
    DEFAULT_HISTOGRAMS,
    BG_COLOR,
    FG_COLOR,
    HIGHLIGHT_COLOR,
    PRIMARY_COLOR,
    ACTION_COLOR,
    CORRELATION_COLORS,
    CORRELATION_LABELS,
    HISTOGRAM_COLORS,
    HISTOGRAM_LABELS,
    DEFAULT_SERIALS,
    DEFAULT_LOCAL_SERIALS,
    DEFAULT_REMOTE_SERIALS
)

from .helpers import format_number, format_angles
from .plot_updater import PlotUpdater
from .optimizer_row_extended import OptimizerRowExtended

__all__ = [
    'DEFAULT_TC_ADDRESS',
    'DEFAULT_ACQ_DURATION',
    'DEFAULT_BIN_WIDTH',
    'DEFAULT_BIN_COUNT',
    'DEFAULT_HISTOGRAMS',
    'BG_COLOR',
    'FG_COLOR',
    'HIGHLIGHT_COLOR',
    'PRIMARY_COLOR',
    'ACTION_COLOR',
    'CORRELATION_COLORS',
    'CORRELATION_LABELS',
    'HISTOGRAM_COLORS',
    'HISTOGRAM_LABELS',
    'DEFAULT_SERIALS',
    'DEFAULT_LOCAL_SERIALS',
    'DEFAULT_REMOTE_SERIALS',
    'format_number',
    'format_angles',
    'PlotUpdater',
    'OptimizerRowExtended'
]
