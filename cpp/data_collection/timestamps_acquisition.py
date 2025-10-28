"""Run an acquisition and saves the timestamps."""

import sys
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone

sys.path.append(str(Path(__file__).parent.parent))
from utils.common import connect, dlt_connect, DataLinkTargetError, zmq_exec
from utils.acquisitions import close_active_acquisitions, acquire_timestamps

logger = logging.getLogger(__name__)

#################################################################
#################   TO BE FILLED BY USER   ######################
#################################################################

# Folder of the "DataLinkTargetService.exe" executable on your computer.
# Once the GUI installed, you should find it there:
DEFAULT_DLT_PATH = Path("C:/Program Files/IDQ/Time Controller/packages/ScpiClient")

# Default Time Controller IP address
DEFAULT_TC_ADDRESS = "192.168.0.156"

# Default acquisition duration in seconds
DEFAULT_ACQUISITION_DURATION = 5

# Default location where timestamps files are saved
DEFAULT_OUTPUT_PATH = Path("C:\\Users\\DR KIS\\Desktop\\vp\\timestamps")

# Default channels on which timestamps are acquired (possible range: 1-4)
DEFAULT_CHANNELS = [1, 2, 3, 4]

# Include reference index
DEFAULT_WITH_REF_INDEX = True

# Timestamps file format (either "ascii" or "bin")
DEFAULT_TIMESTAMPS_FORMAT = "bin"

# Default log file path where logging output is stored
DEFAULT_LOG_PATH = None

#################################################################
#######################   MAIN FUNCTION   #######################
#################################################################


def main():

    print("Start time: ")
    print(datetime.now(timezone.utc))


    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--duration",
        type=float,
        help="acquisition duration",
        metavar=("SECONDS"),
        default=DEFAULT_ACQUISITION_DURATION,
    )
    parser.add_argument(
        "--address",
        type=str,
        help="Time Controller address",
        metavar=("IP"),
        default=DEFAULT_TC_ADDRESS,
    )
    parser.add_argument(
        "--channels",
        type=int,
        nargs="+",
        choices=(1, 2, 3, 4),
        help="hitograms to plot/save",
        metavar="NUM",
        default=DEFAULT_CHANNELS,
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=("bin", "ascii"),
        help="timestamps output format",
        metavar=("FMT"),
        default=DEFAULT_TIMESTAMPS_FORMAT,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="timestamps output directory",
        metavar=("FULLPATH"),
        default=DEFAULT_OUTPUT_PATH,
    )
    parser.add_argument(
        "--without-ref-index" if DEFAULT_WITH_REF_INDEX else "--with-ref-index",
        action="store_false" if DEFAULT_WITH_REF_INDEX else "store_true",
        dest="with_ref_index",
    )
    parser.add_argument(
        "--dlt-path",
        type=Path,
        help="path to the datalinktarget service binary",
        metavar=("FULLPATH"),
        default=DEFAULT_DLT_PATH,
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        help="store output in log file",
        metavar=("FULLPATH"),
        default=DEFAULT_LOG_PATH,
    )
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
        filename=args.log_path
    )

    try:
        tc = connect(args.address)

        dlt = dlt_connect(args.output_dir, args.dlt_path)

        # Close any ongoing acquisition on the DataLinkTarget
        close_active_acquisitions(dlt)

        success = acquire_timestamps(tc, dlt, args.address, args.duration, args.channels, args.format, args.output_dir, args.with_ref_index,)

    except (ConnectionError, DataLinkTargetError, NotADirectoryError) as e:
        logger.exception(e)
        success = False

    print("End time:")
    print(datetime.now(timezone.utc))

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()