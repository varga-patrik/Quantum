"""Diagnostic utility to list available MPC (polarizer) device serial numbers.

Run:
  python -m codes.list_mpc_devices 

If --simulate is supplied, attempts to initialize simulation before building the device list.
"""
from __future__ import annotations
import argparse
import logging

import clr  # type: ignore

# Add references (mirror those in device_hander)
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.DeviceManagerCLI.dll")

from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)


def build_and_list():
    DeviceManagerCLI.BuildDeviceList()
    devices = list(DeviceManagerCLI.GetDeviceList())
    logger.info("Found %d device(s)", len(devices))
    for d in devices:
        logger.info(" - %s", d)
    if not devices:
        logger.warning("No devices found. If expecting simulation, try the GUI or --simulate")


def main():
    build_and_list()


if __name__ == "__main__":
    main()
