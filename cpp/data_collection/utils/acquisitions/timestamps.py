import time
import logging
from utils.common import zmq_exec, dlt_exec
import time

logger = logging.getLogger(__name__)

def _report_acquisition_status(channel, channel_errors, channel_status):

    closing_status = (
        "with errors and timestamp loss" if len(channel_errors) > 0 else "gracefully"
    )

    nb_timestamps = channel_status.get("timestamps_count")

    logger.info(
        f"[channel {channel}] acquisition closed {closing_status} ({nb_timestamps} timestamps)"
    )

    for error in channel_errors:
        logger.error(f"[channel {channel}] {error}")


def wait_end_of_timestamps_acquisition(tc, dlt, acquisitions_id, timeout=10):
    """Wait until timestamps acquisitions are all done or encounered an error."""

    SLEEP_TIME = 1  # time between each end of acquisition check
    NATURAL_INACTIVITY = 1  # allowed natural inactivity after end of acquisition

    timeout = max(timeout, SLEEP_TIME + 1, NATURAL_INACTIVITY)

    done = {channel: False for channel in acquisitions_id}

    try:
        number_of_record = int(zmq_exec(tc, "REC:NUMber?"))
    except ValueError:
        number_of_record = None
        timeout += NATURAL_INACTIVITY

    while not all(done.values()):
        time.sleep(1)

        acquisition_playing = zmq_exec(tc, "REC:STAGe?").upper() == "PLAYING"

        active_channels_status = {
            channel: dlt_exec(dlt, f"status --id {acqu_id}")
            for channel, acqu_id in acquisitions_id.items()
            if not done[channel]
        }

        max_acqu_count = max(
            status["acquisitions_count"] for status in active_channels_status.values()
        )

        for channel, status in active_channels_status.items():
            # Consider channel acquisition done if an arror occured
            if status.get("error"):
                done[channel] = True
                continue

            if not acquisition_playing:

                # Infinite number of records...
                if not number_of_record:
                    # ... Channel properly registered all end of sub-acquisitions
                    #
                    # We wait that NATURAL_INACTIVITY is exceeded before we accept to beleive that
                    # max_acqu_count is indeed the final number recorded of sub-acquisitions across
                    # all channels.
                    if (
                        status["acquisitions_count"] > 0
                        and status["acquisitions_count"] == max_acqu_count
                        and status["inactivity"] > NATURAL_INACTIVITY
                    ):
                        done[channel] = True
                        continue

                # Channel properly registered the end of the acquisition
                elif status["acquisitions_count"] >= number_of_record:
                    done[channel] = True
                    continue

                # Channel did not receive any message for too long after end of acquisition
                if status["inactivity"] > timeout:
                    logger.error(f"[channel {channel}] timestamp transfert timeout")
                    done[channel] = True
                    continue


def close_active_acquisitions(dlt):
    active_aquisitions = dlt_exec(dlt, "list")
    for acquisition_id in active_aquisitions:
        logger.warning(f"closing active acquisition '{acquisition_id}'")
        dlt_exec(dlt, f"stop --id {acquisition_id}")


def open_timestamps_acquisition(
    tc, dlt, tc_address, channels, fmt, output_dir, with_ref_index
):
    acquisitions_id = {}

    for channel in channels:
        # Reset error counter
        zmq_exec(tc, f"RAW{channel}:ERRORS:CLEAR")

        # Tell the DataLink to start listening and store the timestamps in a file.
        # Command: start-save --address <time controller ip> --channel <1-4> --filename <relative/full path> --format <bin|ascii>
        # Returns the ID of the started acquisition

        ext = "bin" if fmt == "bin" else "txt"

        timestr = time.strftime("%m-%d_%H-%M-%S")
        filepath = output_dir / f"timestamps_wigner_{timestr}_C{channel}.{ext}"
        filepath_escaped = str(filepath).replace("\\", "\\\\")

        command = f'start-save --address {tc_address} --channel {channel} --filename "{filepath_escaped}" --format {fmt}'
        if with_ref_index:
            command += " --with-ref-index"
        answer = dlt_exec(dlt, command)

        acquisitions_id[channel] = answer["id"]

        # Start transfer of timestamps
        zmq_exec(tc, f"RAW{channel}:SEND ON")

    return acquisitions_id


def close_timestamps_acquisition(tc, dlt, acquisitions_id):

    success = True

    dlt_exec(dlt, f"list")

    # Stop all channels acquisition and store their status
    channels_status = {
        channel: dlt_exec(dlt, f"stop --id {acqu_id}").get("status")
        for channel, acqu_id in acquisitions_id.items()
    }

    expected_acqu_count = max(
        1, max(status["acquisitions_count"] for status in channels_status.values())
    )

    for channel, status in channels_status.items():

        channel_errors = []
        for error in status.get("errors", []):
            channel_errors.append(error.get("description"))

        acqu_count = status["acquisitions_count"]
        if acqu_count < expected_acqu_count:
            channel_errors.append(
                f"End of acquisition(s) not properly registered ({acqu_count}/{expected_acqu_count})"
            )

        zmq_exec(tc, f"RAW{channel}:SEND OFF")

        if int(zmq_exec(tc, f"RAW{channel}:ERRORS?")):
            channel_errors.append(
                f"The Time Controller reports timestamps acquisition errors"
            )

        _report_acquisition_status(channel, channel_errors, status)

        success &= len(channel_errors) < 0

    return success


def acquire_timestamps(
    tc, dlt, tc_address, duration, channels, fmt, output_dir, with_ref_index
):
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

    acquisitions_id = open_timestamps_acquisition(
        tc, dlt, tc_address, channels, fmt, output_dir, with_ref_index
    )

    zmq_exec(tc, "REC:PLAY")  # Start the acquisition

    wait_end_of_timestamps_acquisition(tc, dlt, acquisitions_id)

    success = close_timestamps_acquisition(tc, dlt, acquisitions_id)

    return success
