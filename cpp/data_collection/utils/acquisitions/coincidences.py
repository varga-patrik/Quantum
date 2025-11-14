from dataclasses import dataclass
from utils.common import zmq_exec, trim_unit


@dataclass(frozen=True)
class CounterSettings():
    block: str
    begin_coef: float = None
    end_coef: float = None


# Associate counters name to their bloc and, for coincidences, their begin/end delay coefficient
INPUT_COUNTERS_SETTINGS = {
    "start": CounterSettings("STARt"),
    "input 1": CounterSettings("INPU1"),
    "input 2": CounterSettings("INPU2"),
    "input 3": CounterSettings("INPU3"),
    "input 4": CounterSettings("INPU4"), 
}

COINCIDENCE_COUNTER_SETTINGS = {
    "1/2": CounterSettings("TSCO6", 0.5, 1.5),
    "1/3": CounterSettings("TSCO7", 1.5, 2.5),
    "1/4": CounterSettings("TSCO8", 2.5, 3.5),
    "2/3": CounterSettings("TSCO3", 1.5, 2.5),
    "2/4": CounterSettings("TSCO4", 2.5, 3.5),
    "3/4": CounterSettings("TSCO5", 2.5, 3.5),
    "1/2/3": CounterSettings("TSCO13", 0, 2),
    "1/2/4": CounterSettings("TSCO14", 1, 3),
    "1/3/4": CounterSettings("TSCO15", 0, 2),
    "2/3/4": CounterSettings("TSCO16", 0, 2),
    "1/2/3/4": CounterSettings("TSCO24", 1, 3),
}

COUNTERS_SETTINGS = {**INPUT_COUNTERS_SETTINGS, **COINCIDENCE_COUNTER_SETTINGS}



def configure(tc, coincidence_window, counter_integration_time=None):
    zmq_exec(tc, "DEVI:CONFI:LOAD COUNT")  # Apply coincidence counters configuration

    def get_delay(idx: int):
        return int(trim_unit(zmq_exec(tc, f"DELA{idx}:VALU?"), "TB"))

    # Apply coincidence window ...

    # ... on additional input delays (used by coincidence blocks)
    zmq_exec(tc, f"DELA6:VALU {get_delay(2) + coincidence_window*1}")  # INPU2 2nd delay
    zmq_exec(tc, f"DELA7:VALU {get_delay(3) + coincidence_window*2}")  # INPU3 2nd delay
    zmq_exec(tc, f"DELA8:VALU {get_delay(4) + coincidence_window*3}")  # INPU4 2nd delay

    for counter in COUNTERS_SETTINGS.values():
        
        # ... on coincidence blocks
        if counter.begin_coef is not None:
            window_begin_delay = int(coincidence_window * counter.begin_coef)
            zmq_exec(tc, f"{counter.block}:WIND:BEGI:DELA {window_begin_delay}")

        if counter.end_coef is not None:
            window_end_delay = int(coincidence_window * counter.end_coef)
            zmq_exec(tc, f"{counter.block}:WIND:END:DELA {window_end_delay}")

        # Configure counter...
        if counter_integration_time:
            # ... intergration time if supplied
            zmq_exec(
                tc, f"{counter.block}:COUN:MODE CYCL;INTE {counter_integration_time};RESEt"
            )
        else:
            # ... in endless accumulation mode
            zmq_exec(tc, f"{counter.block}:COUN:MODE ACCU;RESEt")


def read_counts(tc):
    # Ask for all counters in a single command
    commands = [f"{counter.block}:COUNter?" for counter in COUNTERS_SETTINGS.values()]
    answer = zmq_exec(tc, ";:".join(commands))

    counters = {
        counter : int(counts)
        for counter, counts in zip(COUNTERS_SETTINGS, answer.splitlines())
    }

    return counters
