from struct import *
import platform

from usb.backend import libusb1
import usb.core
import usb.util

# gs_usb general
GS_USB_ID_VENDOR = 0x1D50
GS_USB_ID_PRODUCT = 0x606F

# gs_usb mode
GS_USB_MODE_NORMAL = 0
GS_USB_MODE_LISTEN_ONLY = 1 << 0
GS_USB_MODE_LOOP_BACK = 1 << 1
GS_USB_MODE_ONE_SHOT = 1 << 3
GS_USB_MODE_NO_ECHO_BACK = 1 << 8

# gs_usb control request
_GS_USB_BREQ_HOST_FORMAT = 0
_GS_USB_BREQ_BITTIMING = 1
_GS_USB_BREQ_MODE = 2
_GS_USB_BREQ_BERR = 3
_GS_USB_BREQ_BT_CONST = 4
_GS_USB_BREQ_DEVICE_CONFIG = 5


class GsUsb:
    def __init__(self, gs_usb):
        self.gs_usb = gs_usb

    def start(self, mode=GS_USB_MODE_NORMAL):
        r"""
        Start gs_usb device
        :param mode: GS_USB_MODE_NORMAL, GS_USB_MODE_LISTEN_ONLY, etc.
        """
        # Reset to support restart multiple times
        self.gs_usb.reset()

        # Detach usb from kernel driver in Linux/Unix system to perform IO
        if "windows" not in platform.system().lower() and self.gs_usb.is_kernel_driver_active(
            0
        ):
            self.gs_usb.detach_kernel_driver(0)

        mode_ = 1
        mode |= 1 << 4
        data = pack("II", mode_, mode)
        self.gs_usb.ctrl_transfer(0x41, _GS_USB_BREQ_MODE, 0, 0, data)

        

    def stop(self):
        r"""
        Stop gs_usb device
        """
        mode_ = 0
        mode = 0
        data = pack("II", mode_, mode)

        try:
            self.gs_usb.ctrl_transfer(0x41, _GS_USB_BREQ_MODE, 0, 0, data)
        except usb.core.USBError:
            pass

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
        else:
            return False
        return True

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
        self.gs_usb.ctrl_transfer(0x41, _GS_USB_BREQ_BITTIMING, 0, 0, data)

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
        return True

    def read(self, frame, timeout_ms):
        r"""
        Read frame
        :param frame: GsUsbFrame
        :param timeout_ms: read time out in ms.
                           Note that timeout as 0 will block forever if no message is received 
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

    @property
    def bus(self):
        return self.gs_usb.bus

    @property
    def address(self):
        return self.gs_usb.address

    @property
    def serial_number(self):
        r"""
        Get gs_usb device serial number in string format
        """
        return self.gs_usb.serial_number

    @property
    def device_info(self):
        r"""
        Get gs_usb device info
        """
        data = self.gs_usb.ctrl_transfer(0xC1, _GS_USB_BREQ_DEVICE_CONFIG, 0, 0, 12)
        tup = unpack("4B2I", data)
        info = "fw: " + str(tup[4] / 10) + " hw: " + str(tup[5] / 10)
        return info

    def __str__(self):
        try:
            _ = "{} ({})".format(self.gs_usb.product, repr(self.gs_usb))
        except (ValueError, usb.core.USBError):
            return ""
        return _

    @staticmethod
    def scan():
        r"""
        Retrieve the list of gs_usb devices handle
        :return: list of gs_usb devices handle
        """
        return [
            GsUsb(dev)
            for dev in usb.core.find(
                find_all=True,
                idVendor=GS_USB_ID_VENDOR,
                idProduct=GS_USB_ID_PRODUCT,
                backend=libusb1.get_backend(),
            )
        ]

    @staticmethod
    def find(bus, address):
        gs_usb = usb.core.find(
            idVendor=GS_USB_ID_VENDOR,
            idProduct=GS_USB_ID_PRODUCT,
            bus=bus,
            address=address,
            backend=libusb1.get_backend(),
        )
        if gs_usb:
            return GsUsb(gs_usb)
        return None
