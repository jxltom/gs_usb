#!/usr/bin/env python3
"""
canobserver.py — live CAN / CAN FD frame monitor for gs_usb devices.

Usage:
    python canobserver.py [options]

Examples:
    python canobserver.py
    python canobserver.py --bitrate 500000 --data-bitrate 2000000
    python canobserver.py --device 6:14
    python canobserver.py --filter 0x100:0x7FF
    python canobserver.py --log trace.log
    python canobserver.py --no-color
"""
import argparse
import signal
import sys
import time
from datetime import datetime

from gs_usb.gs_usb import GsUsb
from gs_usb.gs_usb_frame import GsUsbFrame
from gs_usb.constants import (
    GS_CAN_MODE_LISTEN_ONLY,
    GS_CAN_MODE_HW_TIMESTAMP,
    GS_CAN_MODE_FD,
    GS_CAN_FEATURE_FD,
)

# ── ANSI colours ──────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RED    = "\033[31m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
WHITE  = "\033[97m"

def _c(enabled, *codes):
    return "".join(codes) if enabled else ""


# ── Formatting ────────────────────────────────────────────────────────────────

def format_frame(frame, wall_time, color):
    """Return a single formatted line for one CAN / CAN FD frame."""
    ts = "{:.6f}".format(wall_time)

    if frame.is_extended_id:
        id_str = "{:08X}".format(frame.arbitration_id)
    else:
        id_str = "     {:03X}".format(frame.arbitration_id)

    dlc = frame.data_length

    if frame.is_error_frame:
        tag  = _c(color, RED, BOLD) + " ERR" + _c(color, RESET)
        data = "--"
    elif frame.is_remote_frame:
        tag  = _c(color, YELLOW) + "  RR" + _c(color, RESET)
        data = "remote request"
    elif frame.is_fd:
        flags = "FD"
        if frame.is_bitrate_switch:
            flags += "+BRS"
        if frame.is_error_state_indicator:
            flags += "+ESI"
        tag  = _c(color, CYAN, BOLD) + "{:>7}".format(flags) + _c(color, RESET)
        data = " ".join("{:02X}".format(b) for b in frame.data[:dlc])
    else:
        tag  = _c(color, DIM) + "     CL" + _c(color, RESET)
        data = " ".join("{:02X}".format(b) for b in frame.data[:dlc])

    dlc_str = "[{:2d}]".format(dlc)

    return "{ts}  {id}  {tag}  {dlc}  {data}".format(
        ts=_c(color, DIM) + ts + _c(color, RESET),
        id=_c(color, WHITE, BOLD) + id_str + _c(color, RESET),
        tag=tag,
        dlc=dlc_str,
        data=data,
    )


def format_log_line(frame, wall_time):
    """candump-compatible log line:  (timestamp) channel id#data"""
    ts = "({:.6f})".format(wall_time)
    if frame.is_extended_id:
        id_str = "{:08X}".format(frame.arbitration_id)
    else:
        id_str = "{:03X}".format(frame.arbitration_id)

    if frame.is_remote_frame:
        id_str += "R"
        data_str = ""
    elif frame.is_error_frame:
        id_str = "{:08X}".format(frame.arbitration_id)
        data_str = "".join("{:02X}".format(b) for b in frame.data[:frame.data_length])
    else:
        data_str = "".join("{:02X}".format(b) for b in frame.data[:frame.data_length])

    sep = "##1" if frame.is_fd else "#"
    return "{} ch0 {}{}{}".format(ts, id_str, sep, data_str)


# ── Device setup ──────────────────────────────────────────────────────────────

def open_device(bus_addr):
    if bus_addr:
        bus, addr = bus_addr
        dev = GsUsb.find(bus, addr)
        if dev is None:
            print("Device {}:{} not found.".format(bus, addr), file=sys.stderr)
            return None
        return dev

    devs = GsUsb.scan()
    if not devs:
        print("No gs_usb device found.", file=sys.stderr)
        print("  Linux:   check USB connection and permissions (udev rules)", file=sys.stderr)
        print("  Windows: use Zadig to bind WinUSB/libusb driver to the device", file=sys.stderr)
        return None
    if len(devs) > 1:
        print("Multiple devices found — picking first. Use --device bus:addr to select:", file=sys.stderr)
        for d in devs:
            print("  {}:{} — {}".format(d.bus, d.address, d), file=sys.stderr)
    return devs[0]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Live CAN / CAN FD frame monitor for gs_usb devices.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--device", metavar="BUS:ADDR",
        help="USB bus and address (e.g. 6:14). Default: first found.",
    )
    parser.add_argument(
        "--bitrate", type=int, default=500000, metavar="BPS",
        help="Nominal CAN bitrate in bps (default: 500000).",
    )
    parser.add_argument(
        "--data-bitrate", type=int, default=None, metavar="BPS",
        help="CAN FD data-phase bitrate. Enables FD mode when set.",
    )
    parser.add_argument(
        "--filter", metavar="ID:MASK",
        help="Only show frames matching ID & MASK (hex). E.g. 0x100:0x7FF",
    )
    parser.add_argument(
        "--fd-only", action="store_true",
        help="Only show CAN FD frames.",
    )
    parser.add_argument(
        "--classic-only", action="store_true",
        help="Only show classic CAN frames.",
    )
    parser.add_argument(
        "--log", metavar="FILE",
        help="Also write candump-compatible log to FILE.",
    )
    parser.add_argument(
        "--no-color", action="store_true",
        help="Disable ANSI color output.",
    )
    parser.add_argument(
        "--active", action="store_true",
        help="Start in active (non-listen-only) mode. Default is listen-only.",
    )
    args = parser.parse_args()

    color = not args.no_color

    # Parse --device
    bus_addr = None
    if args.device:
        try:
            bus, addr = args.device.split(":")
            bus_addr = (int(bus), int(addr))
        except ValueError:
            print("--device must be BUS:ADDR (e.g. 6:14)", file=sys.stderr)
            sys.exit(1)

    # Parse --filter
    id_filter = mask_filter = None
    if args.filter:
        try:
            parts = args.filter.split(":")
            id_filter   = int(parts[0], 16)
            mask_filter = int(parts[1], 16)
        except (ValueError, IndexError):
            print("--filter must be ID:MASK in hex (e.g. 0x100:0x7FF)", file=sys.stderr)
            sys.exit(1)

    dev = open_device(bus_addr)
    if dev is None:
        sys.exit(1)

    cap = dev.device_capability
    fd_capable = bool(cap.feature & GS_CAN_FEATURE_FD)
    fd_mode = args.data_bitrate is not None

    if fd_mode and not fd_capable:
        print("Device does not support CAN FD — ignoring --data-bitrate.", file=sys.stderr)
        fd_mode = False

    # Print header
    print(_c(color, BOLD) + str(dev) + _c(color, RESET))
    print("  Bus {:d}  Address {:d}  Clock {} MHz  Features 0x{:04X}{}".format(
        dev.bus, dev.address,
        cap.fclk_can // 1_000_000,
        cap.feature,
        "  [FD capable]" if fd_capable else "",
    ))
    print("  Nominal bitrate: {:,} bps".format(args.bitrate), end="")
    if fd_mode:
        print("  Data bitrate: {:,} bps".format(args.data_bitrate), end="")
    print()

    mode_desc = []
    if not args.active:
        mode_desc.append("listen-only")
    if fd_mode:
        mode_desc.append("FD")
    if id_filter is not None:
        mode_desc.append("filter {:X}:{:X}".format(id_filter, mask_filter))
    print("  Mode: {}".format(", ".join(mode_desc) if mode_desc else "active"))
    print()

    # Column header
    col_header = (
        _c(color, DIM) + "    timestamp       " + _c(color, RESET) +
        _c(color, BOLD) + "      ID  " + _c(color, RESET) +
        "   type    [len]  data"
    )
    print(col_header)
    print(_c(color, DIM) + "-" * 72 + _c(color, RESET))

    # Configure device
    if not dev.set_bitrate(args.bitrate):
        print("Failed to set bitrate {:,}. Check --bitrate value.".format(args.bitrate),
              file=sys.stderr)
        sys.exit(1)

    if fd_mode:
        if not dev.set_data_bitrate(args.data_bitrate):
            print(
                "Failed to set data bitrate {:,}.\n"
                "Use a supported rate (1M, 2M, 4M, 5M, 8M) or call set_data_timing() directly.".format(
                    args.data_bitrate),
                file=sys.stderr,
            )
            sys.exit(1)

    flags = GS_CAN_MODE_HW_TIMESTAMP
    if not args.active:
        flags |= GS_CAN_MODE_LISTEN_ONLY
    if fd_mode:
        flags |= GS_CAN_MODE_FD

    dev.start(flags)

    # Open log file
    log_file = None
    if args.log:
        try:
            log_file = open(args.log, "w")
            log_file.write("# canobserver log started {}\n".format(
                datetime.utcnow().isoformat() + "Z"))
        except OSError as e:
            print("Cannot open log file: {}".format(e), file=sys.stderr)
            sys.exit(1)

    # Stats
    t_start = time.monotonic()
    count_total = 0
    count_fd    = 0
    count_shown = 0

    def print_stats():
        elapsed = time.monotonic() - t_start
        rate = count_total / elapsed if elapsed > 0 else 0
        print(
            _c(color, DIM) +
            "\n──  {:,} frames received ({:,} FD)  {:.1f} frames/s  {:.1f}s  ──".format(
                count_total, count_fd, rate, elapsed) +
            _c(color, RESET)
        )

    def handle_sigint(sig, frame_):
        print_stats()
        if log_file:
            log_file.close()
        dev.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)

    # Read loop
    frame = GsUsbFrame()
    while True:
        if not dev.read(frame, timeout_ms=100):
            continue

        wall_time = time.time()
        count_total += 1
        if frame.is_fd:
            count_fd += 1

        # Filtering
        if id_filter is not None:
            if (frame.arbitration_id & mask_filter) != (id_filter & mask_filter):
                continue
        if args.fd_only and not frame.is_fd:
            continue
        if args.classic_only and frame.is_fd:
            continue

        line = format_frame(frame, wall_time, color)
        print(line)

        if log_file:
            log_file.write(format_log_line(frame, wall_time) + "\n")
            log_file.flush()

        count_shown += 1


if __name__ == "__main__":
    main()
