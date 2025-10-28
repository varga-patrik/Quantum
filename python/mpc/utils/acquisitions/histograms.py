import time
from typing import Any, Dict, Iterable, List
from utils.common import zmq_exec


def wait_end_of_acquisition(tc):
    # Wait while RECord is playing
    while zmq_exec(tc, "REC:STAGe?").upper() == "PLAYING":
        #time.sleep(1)
        None


def acquire_histograms(tc, duration: int, bwid: int, bcount: int, hist_numbers: Iterable[int]) -> Dict[int, List[int]]:

    ### Configure the acquisition timer

    # Trigger RECord signal manually (PLAY command)
    zmq_exec(tc, "REC:TRIG:ARM:MODE MANUal")
    # Enable the RECord generator
    zmq_exec(tc, "REC:ENABle ON")
    # STOP any already ongoing acquisition
    zmq_exec(tc, "REC:STOP")
    # Record a single acquisition
    zmq_exec(tc, "REC:NUM 1")
    # Record for the request duration (in ps)
    zmq_exec(tc, f"REC:DURation {duration * 1e12}")

    for i in hist_numbers:
        zmq_exec(tc, f"HIST{i}:BCOUnt {bcount}")  # Set histogram maximum bin count
        zmq_exec(tc, f"HIST{i}:BWID {bwid}")  # Set histogram bin width
        zmq_exec(tc, f"HIST{i}:FLUSh")  # Flush histogram

    zmq_exec(tc, "REC:PLAY")  # Start the acquisition

    wait_end_of_acquisition(tc)

    # Get histogram data
    histograms = {i: eval(zmq_exec(tc, f"HIST{i}:DATA?")) for i in hist_numbers}
 
    return histograms


def save_histograms(histograms: Dict[Any, int], bin_width: int, filepath: str, center_bins: bool=True):

    with open(filepath, "w") as file:
        histogram_names = (
            f"histogram {key}" if isinstance(key, int) else key
            for key in histograms
        )

        histograms_headers = ";".join(histogram_names)

        bin_times_header = "bin center" if center_bins else "bin" 

        file.write(f"{bin_times_header} (ps);{histograms_headers}\n")

        # Bin center and values
        for i, bin_values in enumerate(zip(*histograms.values()), 1):
            bin_time = i * bin_width
            if center_bins:
                bin_time -= bin_width / 2

            bins = ";".join(str(bin_value) for bin_value in bin_values)
            file.write(f"{bin_time};{bins}\n")

