import sys

from pathlib import Path
from utils.common import connect, dlt_connect, DataLinkTargetError
from utils.acquisitions import close_active_acquisitions
from utils.common import zmq_exec
from datetime import datetime, timezone

# Folder of the "DataLinkTargetService.exe" executable on your computer.
# Once the GUI installed, you should find it there:
DEFAULT_DLT_PATH = Path("C:/Program Files/IDQ/Time Controller/packages/ScpiClient")

# Default Time Controller IP address
DEFAULT_TC_ADDRESS = "148.6.27.28"

# Default location where timestamps files are saved
DEFAULT_OUTPUT_PATH = Path("C:\\Users\\DR KIS\\Desktop\\vp\\timestamps")

def main():

    print("Start time: ")
    print(datetime.now(timezone.utc))

    try:
        tc = connect(DEFAULT_TC_ADDRESS)

        dlt = dlt_connect(DEFAULT_OUTPUT_PATH, DEFAULT_DLT_PATH)

        # Close any ongoing acquisition on the DataLinkTarget
        close_active_acquisitions(dlt)

        zmq_exec(tc, "input1:enable on")
        zmq_exec(tc, "input2:enable on")
        #zmq_exec(tc, "input3:enable on")
        #zmq_exec(tc, "input4:enable on")
        zmq_exec(tc, "start:enable on")

        zmq_exec(tc, "start:edge rising")
        zmq_exec(tc, "input1:edge falling")
        zmq_exec(tc, "input2:edge falling")
        #zmq_exec(tc, "input3:edge falling")
        #zmq_exec(tc, "input4:edge falling")

    except (ConnectionError, DataLinkTargetError, NotADirectoryError):
        #success = False
        print("Error")

    print("End time:")
    print(datetime.now(timezone.utc))

    sys.exit(0)


if __name__ == "__main__":
    main()