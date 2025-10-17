from typing import Any, Dict, List, Tuple
from utils.common import zmq_exec, adjust_bin_width
from .coincidences import (
    configure as configure_coincidences,
    COINCIDENCE_COUNTER_SETTINGS
)
from .histograms import acquire_histograms, save_histograms

INPUT_TO_HIST_CHANNEL_BLOCK_MAP = {
    "start": "STAR",
    "1": "TSCO5",
    "2": "TSCO6",
    "3": "TSCO7",
    "4": "TSCO8",
}

COINCIDENCE_TO_HIST_CHANNEL_BLOCK_MAP = { 
    coincidence: settings.block
    for coincidence, settings in COINCIDENCE_COUNTER_SETTINGS.items()
}

COUNT_OVER_TIME_INPUTS = list(INPUT_TO_HIST_CHANNEL_BLOCK_MAP.keys())
COUNT_OVER_TIME_COINCIDENCES = list(COINCIDENCE_TO_HIST_CHANNEL_BLOCK_MAP.keys())

REC_TSCO = "TSCO1"


def setup_counts_over_time_acquisition(
    tc,
    integration_time: int,
    counters: Any,
    counter_to_hist_block_map: Dict[Any, str]
) -> Tuple[Dict[int, Any], int]:

    # Link RECord generator to its TSCO 
    zmq_exec(tc, f"{REC_TSCO}:FIR:LINK REC")
    # Set RECord TSCO to just forward the signal
    zmq_exec(tc, f"{REC_TSCO}:OPIN ONLYFIR;OPOUt ONLYFIR;WIND:ENAB OFF")

    hist_to_counter_map = {
        hist_channel: counter
        for hist_channel, counter in enumerate(counters, 1)
    }

    for hist_channel, counter in hist_to_counter_map.items():
        # Link histogram REF to the REC TSCO configured above
        zmq_exec(tc, f"HIST{hist_channel}:REF:LINK {REC_TSCO}")
        channel_block = counter_to_hist_block_map[counter]

        if channel_block.startswith("TSCO"):
            zmq_exec(tc, f"{channel_block}:OPIN ONLYFIR;OPOUt ONLYFIR;WIND:ENAB OFF")

        # Link histogram STOP to the input channel TSCO
        zmq_exec(tc, f"HIST{hist_channel}:STOP:LINK {channel_block}")

    actual_integration_time = adjust_bin_width(tc, integration_time)

    return hist_to_counter_map, actual_integration_time


def setup_input_counts_over_time_acquisition(tc, integration_time: int, counters: Any):
    zmq_exec(tc, f"DEVIce:CONF:LOAD HISTO")

    return setup_counts_over_time_acquisition(
        tc,
        integration_time,
        counters,
        INPUT_TO_HIST_CHANNEL_BLOCK_MAP
    )

def setup_coincidence_counts_over_time_acquisition(tc, integration_time: int, counters: Any, window: int):
    configure_coincidences(tc, window, 1000)

    return setup_counts_over_time_acquisition(
        tc,
        integration_time,
        counters,
        COINCIDENCE_TO_HIST_CHANNEL_BLOCK_MAP
    )

def acquire_counts_over_time(tc, integration_time: int, nb_acquisitions: int, hist_to_counter_map: Dict[int, Any]):
    duration = integration_time * nb_acquisitions * 1e-12

    counts_over_time_histograms = acquire_histograms(
        tc, duration, integration_time, nb_acquisitions, hist_to_counter_map
    )

    counts_over_time = {
        hist_to_counter_map[hist_channel]: counts
        for hist_channel, counts in counts_over_time_histograms.items()
    }

    return counts_over_time


def save_counts_over_time(
    counts_over_time: Dict[Any, List[int]],
    actual_integration_time: int,
    filepath: str
):
    save_histograms(
        counts_over_time,
        actual_integration_time,
        filepath,
        center_bins=False,
    )
