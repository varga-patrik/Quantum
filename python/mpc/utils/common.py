import os
import time
import zmq
import json
import socket
import logging
import subprocess
from pathlib import Path
import __main__


DLT_PORT = 6060
SCPI_PORT = 5555
DEFAULT_DLT_PATH = Path("C:/Program Files/IDQ/Time Controller/packages/ScpiClient")
DEFAULT_DLT_FILENAME = "DataLinkTargetService.exe"

logger = logging.getLogger(__name__)

def check_host(address: str, port: int):
    s = socket.socket()
    s.settimeout(5)
    try:
        s.connect((address, port))
        s.settimeout(None)
        return True
    except socket.error:
        return False


def connect(address: str, port=SCPI_PORT):
    # Check if Time Controller is listening
    if not check_host(address, port):
        raise ConnectionError(f'Unable to connect to "{address}" on port {port}.')

    # Create zmq socket and connect to the Time Controller
    context = zmq.Context()
    tc = context.socket(zmq.REQ)
    tc.connect(f"tcp://{address}:{port}")

    logger.info("connection to DLT successful")

    return tc


def zmq_exec(zmq, cmd: str) -> str:
    zmq.send_string(cmd)
    ans = zmq.recv().decode("utf-8")
    logger.debug(f"[command] {cmd}\n{ans}")
    return ans


def trim_unit(value: str, unit: str ="TB") -> str:
    if unit and value.endswith(unit):
        return value[: -len(unit)]
    return value


def adjust_bin_width(tc, bwid: int) -> int:
    resolution_bwid = int(zmq_exec(tc, "DEVI:RES:BWID?"))
    if bwid == None:
        bwid = resolution_bwid
    elif bwid % resolution_bwid != 0:
        bwid = ((bwid // resolution_bwid) + 1) * resolution_bwid
    return bwid


def assert_arg_range(arg_name, arg_value, range):
    assert arg_value in range, f"{arg_name} must be between {range.start} and {range.stop-1}"


class DataLinkTargetError(Exception):
    pass


def dlt_exec(zmq, cmd: str) -> str:
    answer = zmq_exec(zmq, cmd)
    answer = json.loads(answer) if answer.strip() else None

    if isinstance(answer, dict) and "error" in answer:
        message = answer.get("error", {}).get("description")
        raise DataLinkTargetError(message or "unknown error")

    return answer


def dlt_connect(output_dir: Path, dlt_path: Path = DEFAULT_DLT_PATH):    
    # Check target folder exists
    if not output_dir.exists():
        raise NotADirectoryError(f'Output folder "{output_dir}" does not exist.')

    # Check DataLinkTarget binary exists
    if dlt_path.is_dir():
        dlt_dir = dlt_path
        dlt_bin = dlt_path / DEFAULT_DLT_FILENAME
    else:
        dlt_dir = dlt_path.parent
        dlt_bin = dlt_path

    if not dlt_bin.exists():
        raise FileExistsError(f'DataLinkTarget binary "{dlt_bin}" not found.')

    # Check configuraiton template exists  
    config_template_path = dlt_dir / "config" / "DataLinkTargetService.log.conf"
    if not config_template_path.exists():
        raise FileExistsError(f'Configuration file template "{config_template_path}" not found.')

    # Start the DataLinkTargetService if it's not already running
    if not check_host("localhost", DLT_PORT):
        # Build Datalink log configuration file
        script_path = Path(os.path.realpath(__main__.__file__)).parent
        log_conf_path = script_path / "DataLinkTargetService.log.conf"

        with config_template_path.open("r") as template:
            with log_conf_path.open("w") as log_conf_file:
                for line in template:
                    log_conf_file.write(
                        line.replace(
                            "log4cplus.appender.AppenderFile.File=",
                            f"log4cplus.appender.AppenderFile.File={script_path}/",
                        )
                    )

        # Launch DataLinkTargetService
        dlt_command = [str(dlt_bin)]
        dlt_command += ["-f", str(output_dir)]
        dlt_command += ["--logconf", str(log_conf_path)]
        _ = subprocess.Popen(dlt_command, stdout=subprocess.PIPE)

        time.sleep(0.1)

    logger.info("attempt to connect to DLT")

    # Create zmq socket and connect to the DataLink
    return connect("localhost", port=DLT_PORT)
