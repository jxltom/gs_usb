"""
CAN FD loopback test — requires a CAN FD capable gs_usb device
(e.g. CES CANEXT FD or ABE CAN Debugger FD).

The device is started in loopback mode so no bus or second node is needed.
All sent FD frames are received back and verified.

Usage:
    python demo_fd.py [nominal_bitrate] [data_bitrate]

Defaults: 500000 nominal, 2000000 data
"""
import sys
import time

from gs_usb.gs_usb import GsUsb
from gs_usb.gs_usb_frame import GsUsbFrame
from gs_usb.constants import (
    CAN_EFF_FLAG,
    GS_CAN_MODE_FD, GS_CAN_MODE_LOOP_BACK, GS_CAN_MODE_HW_TIMESTAMP,
    GS_CAN_FEATURE_FD,
    CANFD_DLC_TO_LEN,
)

READ_TIMEOUT_MS = 1000
ECHO_WAIT_MS = 500


def find_fd_device():
    devs = GsUsb.scan()
    if not devs:
        print("No gs_usb device found")
        return None
    for dev in devs:
        if dev.device_capability.feature & GS_CAN_FEATURE_FD:
            return dev
    print("No FD-capable device found (found {} classic device(s))".format(len(devs)))
    return None


def check_equal(label, sent, received):
    ok = True

    if received.arbitration_id != sent.arbitration_id:
        print("  FAIL {}: ID mismatch: sent 0x{:X} got 0x{:X}".format(
            label, sent.arbitration_id, received.arbitration_id))
        ok = False

    if received.data_length != sent.data_length:
        print("  FAIL {}: data_length mismatch: sent {} got {}".format(
            label, sent.data_length, received.data_length))
        ok = False

    sent_payload = sent.data[:sent.data_length]
    recv_payload = received.data[:received.data_length]
    if recv_payload != sent_payload:
        print("  FAIL {}: data mismatch".format(label))
        print("    sent: {}".format(sent_payload))
        print("    got:  {}".format(recv_payload))
        ok = False

    # Devices may echo FD frames with DLC 0-8 back as classic CAN frames —
    # valid behavior since the payload fits. Only require FD echo for DLC 9+.
    if sent.data_length > 8 and not received.is_fd:
        print("  FAIL {}: expected FD echo for {}-byte payload, got classic".format(
            label, sent.data_length))
        ok = False

    fd_note = ""
    if received.is_fd != sent.is_fd:
        fd_note = " (echoed as {})".format("FD" if received.is_fd else "classic")

    if ok:
        print("  OK   {}{}  {}".format(label, fd_note, received))
    return ok


def run_loopback(dev, nominal_bitrate, data_bitrate):
    print("Device: {}".format(dev))
    cap = dev.device_capability
    print("Clock:  {} MHz".format(cap.fclk_can // 1_000_000))
    print("Feature flags: 0x{:08X}".format(cap.feature))
    print()

    if not dev.set_bitrate(nominal_bitrate):
        print("ERROR: could not set nominal bitrate {}".format(nominal_bitrate))
        return False

    if not dev.set_data_bitrate(data_bitrate):
        print("ERROR: could not set data bitrate {} (try set_data_timing() for custom rates)".format(data_bitrate))
        return False

    flags = GS_CAN_MODE_FD | GS_CAN_MODE_LOOP_BACK | GS_CAN_MODE_HW_TIMESTAMP
    dev.start(flags)
    print("Started: nominal={} bps  data={} bps  loopback".format(nominal_bitrate, data_bitrate))
    print()

    # Build a set of test frames covering the interesting FD DLC values
    test_cases = []

    # Standard FD frame, classic payload sizes
    test_cases.append(("FD 0-byte",   GsUsbFrame(can_id=0x100, data=[],          is_fd=True, bitrate_switch=True)))
    test_cases.append(("FD 1-byte",   GsUsbFrame(can_id=0x101, data=[0xAA],       is_fd=True, bitrate_switch=True)))
    test_cases.append(("FD 8-byte",   GsUsbFrame(can_id=0x108, data=list(range(8)), is_fd=True, bitrate_switch=True)))
    # FD-only payload sizes
    test_cases.append(("FD 12-byte",  GsUsbFrame(can_id=0x10C, data=list(range(12)), is_fd=True, bitrate_switch=True)))
    test_cases.append(("FD 16-byte",  GsUsbFrame(can_id=0x110, data=list(range(16)), is_fd=True, bitrate_switch=True)))
    test_cases.append(("FD 20-byte",  GsUsbFrame(can_id=0x114, data=list(range(20)), is_fd=True, bitrate_switch=True)))
    test_cases.append(("FD 24-byte",  GsUsbFrame(can_id=0x118, data=list(range(24)), is_fd=True, bitrate_switch=True)))
    test_cases.append(("FD 32-byte",  GsUsbFrame(can_id=0x120, data=list(range(32)), is_fd=True, bitrate_switch=True)))
    test_cases.append(("FD 48-byte",  GsUsbFrame(can_id=0x130, data=list(range(48)), is_fd=True, bitrate_switch=True)))
    test_cases.append(("FD 64-byte",  GsUsbFrame(can_id=0x140, data=list(range(64)), is_fd=True, bitrate_switch=True)))
    # Extended ID
    test_cases.append(("FD EFF 32-byte", GsUsbFrame(
        can_id=0x12345678 | CAN_EFF_FLAG,
        data=[0xFF] * 32,
        is_fd=True,
        bitrate_switch=True,
    )))
    # Without BRS
    test_cases.append(("FD no-BRS 8-byte", GsUsbFrame(can_id=0x200, data=list(range(8)), is_fd=True)))

    passed = 0
    failed = 0

    for label, frame in test_cases:
        dev.send(frame)

        # Drain echo and any TX-echo frames; match by arbitration_id
        deadline = time.time() + ECHO_WAIT_MS / 1000.0
        received = None
        while time.time() < deadline:
            rx = GsUsbFrame()
            if dev.read(rx, READ_TIMEOUT_MS):
                if rx.arbitration_id == frame.arbitration_id:
                    received = rx
                    break

        if received is None:
            print("  FAIL {}: no frame received within {}ms".format(label, ECHO_WAIT_MS))
            failed += 1
        else:
            if check_equal(label, frame, received):
                passed += 1
            else:
                failed += 1

    print()
    print("Results: {}/{} passed".format(passed, passed + failed))
    dev.stop()
    return failed == 0


def main():
    nominal = int(sys.argv[1]) if len(sys.argv) > 1 else 500000
    data    = int(sys.argv[2]) if len(sys.argv) > 2 else 2000000

    dev = find_fd_device()
    if dev is None:
        sys.exit(1)

    ok = run_loopback(dev, nominal, data)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
