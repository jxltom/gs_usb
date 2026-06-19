"""
Demo: device-level features — identify LED, bus termination.

Checks which features the connected device supports and exercises each one.
Run with no arguments to use the first found device.
"""
import time

from gs_usb.gs_usb import GsUsb
from gs_usb.constants import GS_CAN_FEATURE_IDENTIFY, GS_CAN_FEATURE_TERMINATION


def check(label, result, expected=True):
    status = "OK" if result == expected else "FAIL"
    print("  [{}] {}".format(status, label))
    return result == expected


def demo_identify(dev):
    print("\n--- Identify LED ---")
    if not (dev.device_capability.feature & GS_CAN_FEATURE_IDENTIFY):
        print("  Not supported by this device.")
        return

    print("  Turning identify ON  (LED should blink) …")
    check("identify(True) returns True", dev.identify(True), True)
    time.sleep(3)

    print("  Turning identify OFF …")
    check("identify(False) returns True", dev.identify(False), True)
    print("  Done.")


def demo_termination(dev):
    print("\n--- Bus Termination ---")
    if not (dev.device_capability.feature & GS_CAN_FEATURE_TERMINATION):
        print("  Not supported by this device.")
        return

    initial = dev.get_termination()
    print("  Initial state: {}".format("ON" if initial else "OFF"))

    print("  Enabling termination …")
    check("set_termination(True) returns True", dev.set_termination(True), True)
    check("get_termination() is True", dev.get_termination(), True)

    print("  Disabling termination …")
    check("set_termination(False) returns True", dev.set_termination(False), True)
    check("get_termination() is False", dev.get_termination(), False)

    print("  Restoring initial state ({}) …".format("ON" if initial else "OFF"))
    dev.set_termination(initial)
    check("get_termination() restored", dev.get_termination(), initial)
    print("  Done.")


def demo_unsupported(dev):
    print("\n--- Unsupported-feature guard ---")
    if not (dev.device_capability.feature & GS_CAN_FEATURE_IDENTIFY):
        check("identify(True) returns False on unsupported device", dev.identify(True), False)
    if not (dev.device_capability.feature & GS_CAN_FEATURE_TERMINATION):
        check("set_termination(True) returns False on unsupported device", dev.set_termination(True), False)
        check("get_termination() returns None on unsupported device", dev.get_termination(), None)


def main():
    devs = GsUsb.scan()
    if not devs:
        print("No gs_usb device found.")
        return

    dev = devs[0]
    print("Device: {}".format(dev))
    cap = dev.device_capability
    print("Features: 0x{:08x}".format(cap.feature))
    print("  identify    : {}".format("yes" if cap.feature & GS_CAN_FEATURE_IDENTIFY else "no"))
    print("  termination : {}".format("yes" if cap.feature & GS_CAN_FEATURE_TERMINATION else "no"))

    demo_identify(dev)
    demo_termination(dev)
    demo_unsupported(dev)


if __name__ == "__main__":
    main()
