from struct import *
import platform

import usb.core
import usb.util

# CAN bus error
CAN_ERR_BUSOFF = 0x00000001
CAN_ERR_RX_TX_WARNING = 0x00000002
CAN_ERR_RX_TX_PASSIVE = 0x00000004
CAN_ERR_OVERLOAD = 0x00000008
CAN_ERR_STUFF = 0x00000010
CAN_ERR_FORM = 0x00000020
CAN_ERR_ACK = 0x00000040
CAN_ERR_BIT_RECESSIVE = 0x00000080
CAN_ERR_BIT_DOMINANT = 0x00000100
CAN_ERR_CRC = 0x00000200

# gs_usb general
GS_USB_ECHO_ID = 0
GS_USB_NONE_ECHO_ID = 0xFFFFFFFF
GS_USB_FRAME_SIZE = 24

# gs_usb mode
GS_USB_MODE_NORMAL = 0
GS_USB_MODE_LISTEN_ONLY = 1 << 0
GS_USB_MODE_LOOP_BACK = 1 << 1
GS_USB_MODE_ONE_SHOT = 1 << 3
GS_USB_MODE_NO_ECHO_BACK = 1 << 8


class GsUsbFrame:
    def __init__(self):
        self.echo_id = GS_USB_ECHO_ID
        self.can_id = 0
        self.can_dlc = 0
        self.channel = 0
        self.flags = 0
        self.reserved = 0
        self.data = [0x00] * 8
        self.timestamp_us = 0

    def __sizeof__(self):
        return GS_USB_FRAME_SIZE


class GsUsb:
    # gs_usb control request
    __GS_USB_BREQ_BITTIMING = 1
    __GS_USB_BREQ_MODE = 2
    __GS_USB_BREQ_DEVICE_CONFIG = 5

    def __init__(self, gs_usb):
        self.gs_usb = gs_usb

    def start(self, mode=GS_USB_MODE_NORMAL):
        r"""
        Start gs_usb device
        :param mode: GS_USB_MODE_NORMAL, GS_USB_MODE_LISTEN_ONLY, etc.
        """
        mode_ = 1
        mode |= 1 << 4
        data = pack("II", mode_, mode)
        self.gs_usb.ctrl_transfer(0x41, __GS_USB_BREQ_MODE, 0, 0, data)

        # Detach usb from kernel driver in Linux/Unix system to perform IO
        if "windows" not in platform.system().lower() and self.gs_usb.is_kernel_driver_active(
            0
        ):
            self.gs_usb.detach_kernel_driver(0)

    def stop(self):
        r"""
        Stop gs_usb device
        """
        mode_ = 0
        mode = 0
        data = pack("II", mode_, mode)
        self.gs_usb.ctrl_transfer(0x41, __GS_USB_BREQ_MODE, 0, 0, data)

    def set_bitrate(self, bitrate):
        """
        Set bitrate with sample point 87.5% and clock rate 48MHz.
        Ported from https://github.com/HubertD/cangaroo/blob/b4a9d6d8db7fe649444d835a76dbae5f7d82c12f/src/driver/CandleApiDriver/CandleApiInterface.cpp#L17-L112

        It can also be calculated in http://www.bittiming.can-wiki.info/ with sample point 87.5% and clock rate 48MHz
        """
        prop_seg = 1
        sjw = 1

        if bitrate == 10000:
            self.set_timing(prop_seg, 12, 2, sjw, 300)
        elif bitrate == 20000:
            self.set_timing(prop_seg, 12, 2, sjw, 150)
        elif bitrate == 50000:
            self.set_timing(prop_seg, 12, 2, sjw, 60)
        elif bitrate == 83333:
            self.set_timing(prop_seg, 12, 2, sjw, 36)
        elif bitrate == 100000:
            self.set_timing(prop_seg, 12, 2, sjw, 30)
        elif bitrate == 125000:
            self.set_timing(prop_seg, 12, 2, sjw, 24)
        elif bitrate == 250000:
            self.set_timing(prop_seg, 12, 2, sjw, 12)
        elif bitrate == 500000:
            self.set_timing(prop_seg, 12, 2, sjw, 6)
        elif bitrate == 800000:
            self.set_timing(prop_seg, 11, 2, sjw, 4)
        elif bitrate == 1000000:
            self.set_timing(prop_seg, 11, 2, sjw, 3)

    def set_timing(self, prop_seg, phase_seg1, phase_seg2, sjw, brp):
        r"""
        Set CAN bit timing
        :param prop_seg: propagation Segment (const 1)
        :param phase_seg1: phase segment 1 (1~15)
        :param phase_seg2: phase segment 2 (1~8)
        :param sjw: synchronization segment (1~4)
        :param brp: prescaler for quantum where base_clk = 48MHz (1~1024)
        """
        data = pack("5I", prop_seg, phase_seg1, phase_seg2, sjw, brp)
        self.gs_usb.ctrl_transfer(0x41, __GS_USB_BREQ_BITTIMING, 0, 0, data)

    def get_serial_number(self):
        r"""
        Get gs_usb device serial number in string format
        """
        return self.gs_usb.serial_number

    def get_device_info(self):
        r"""
        Get gs_usb device info
        """
        data = self.gs_usb.ctrl_transfer(0xC1, __GS_USB_BREQ_DEVICE_CONFIG, 0, 0, 12)
        tup = unpack("4B2I", data)
        info = "fw: " + str(tup[4] / 10) + " hw: " + str(tup[5] / 10)
        return info

    def send(self, frame):
        r"""
        Send frame
        :param frame: GsUsbFrame
        """
        data = pack(
            "2I12BI",
            frame.echo_id,
            frame.can_id,
            frame.can_dlc,
            frame.channel,
            frame.flags,
            frame.reserved,
            *frame.data,
            frame.timestamp_us
        )
        self.gs_usb.write(0x02, data)

    def read(self, frame, timeout_ms):
        r"""
        Read frame
        :param frame: GsUsbFrame
        :param timeout_ms: read time out in ms
        :return: return True if success else False
        """
        try:
            data = self.gs_usb.read(0x81, frame.__sizeof__(), timeout_ms)
        except usb.core.USBError:
            return False
        (
            frame.echo_id,
            frame.can_id,
            frame.can_dlc,
            frame.channel,
            frame.flags,
            frame.reserved,
            *frame.data,
            frame.timestamp_us,
        ) = unpack("2I12BI", data)
        return True

    @staticmethod
    def scan():
        r"""
        Retrieve the list of gs_usb devices handle
        :return: list of gs_usb devices handle
        """
        return list(usb.core.find(find_all=True, idVendor=0x1D50, idProduct=0x606F))

    @staticmethod
    def parse_err_frame(frame):
        r"""
        Parse can bus error status
        :param frame: error frame
        :return: a tuple of error code, err_tx, err_rx
        """
        error_code = 0

        if frame.can_id & 0x00000040:
            error_code |= CAN_ERR_BUSOFF

        if frame.data[1] & 0x04:
            error_code |= CAN_ERR_RX_TX_WARNING
        elif frame.data[1] & 0x10:
            error_code |= CAN_ERR_RX_TX_PASSIVE

        if frame.flags & 0x00000001:
            error_code |= CAN_ERR_OVERLOAD

        if frame.data[2] & 0x04:
            error_code |= CAN_ERR_STUFF

        if frame.data[2] & 0x02:
            error_code |= CAN_ERR_FORM

        if frame.can_id & 0x00000020:
            error_code |= CAN_ERR_ACK

        if frame.data[2] & 0x10:
            error_code |= CAN_ERR_BIT_RECESSIVE

        if frame.data[2] & 0x08:
            error_code |= CAN_ERR_BIT_DOMINANT

        if frame.data[3] & 0x08:
            error_code |= CAN_ERR_CRC

        return error_code, int(frame.data[6]), int(frame.data[7])
