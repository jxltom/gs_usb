from struct import *
import platform

from usb.backend import libusb1
import usb.core
import usb.util

from .gs_usb_structures import DeviceMode, DeviceBitTiming, DeviceInfo, DeviceCapability, DeviceBtConstExtended, DeviceState
from .gs_usb_frame import (
    GsUsbFrame,
    GS_USB_FRAME_SIZE, GS_USB_FRAME_SIZE_HW_TIMESTAMP,
    GS_USB_FRAME_SIZE_FD, GS_USB_FRAME_SIZE_FD_HW_TIMESTAMP,
)
from .constants import (
    GS_CAN_MODE_NORMAL, GS_CAN_MODE_LISTEN_ONLY, GS_CAN_MODE_LOOP_BACK,
    GS_CAN_MODE_ONE_SHOT, GS_CAN_MODE_HW_TIMESTAMP,
    GS_CAN_MODE_PAD_PKTS_TO_MAX_PKT_SIZE, GS_CAN_MODE_FD,
    GS_CAN_FEATURE_BT_CONST_EXT, GS_CAN_FEATURE_IDENTIFY,
    GS_CAN_FEATURE_TERMINATION, GS_CAN_FEATURE_GET_STATE,
)

# gs_usb VIDs/PIDs (devices currently in the linux kernel driver)
GS_USB_ID_VENDOR = 0x1D50
GS_USB_ID_PRODUCT = 0x606F

GS_USB_CANDLELIGHT_VENDOR_ID = 0x1209
GS_USB_CANDLELIGHT_PRODUCT_ID = 0x2323

GS_USB_CES_CANEXT_FD_VENDOR_ID = 0x1CD2
GS_USB_CES_CANEXT_FD_PRODUCT_ID = 0x606F

GS_USB_ABE_CANDEBUGGER_FD_VENDOR_ID = 0x16D0
GS_USB_ABE_CANDEBUGGER_FD_PRODUCT_ID = 0x10B8

GS_USB_CANNECTIVITY_VENDOR_ID = 0x1209
GS_USB_CANNECTIVITY_PRODUCT_ID = 0xCA01

#gs_usb mode
GS_CAN_MODE_RESET = 0
GS_CAN_MODE_START = 1

# gs_usb control request
_GS_USB_BREQ_HOST_FORMAT = 0
_GS_USB_BREQ_BITTIMING = 1
_GS_USB_BREQ_MODE = 2
_GS_USB_BREQ_BERR = 3
_GS_USB_BREQ_BT_CONST = 4
_GS_USB_BREQ_DEVICE_CONFIG = 5
_GS_USB_BREQ_IDENTIFY = 7
_GS_USB_BREQ_DATA_BITTIMING = 10
_GS_USB_BREQ_BT_CONST_EXT = 11
_GS_USB_BREQ_SET_TERMINATION = 12
_GS_USB_BREQ_GET_TERMINATION = 13
_GS_USB_BREQ_GET_STATE = 14


class GsUsb:
    def __init__(self, gs_usb):
        self.gs_usb = gs_usb
        self.capability = None
        self.device_flags = None

    def start(self, flags=(GS_CAN_MODE_NORMAL | GS_CAN_MODE_HW_TIMESTAMP)):
        r"""
        Start gs_usb device
        :param flags: GS_CAN_MODE_LISTEN_ONLY, GS_CAN_MODE_HW_TIMESTAMP, GS_CAN_MODE_FD, etc.
        """
        # Reset to support restart multiple times
        self.gs_usb.reset()

        # Detach usb from kernel driver in Linux/Unix system to perform IO
        if "windows" not in platform.system().lower() and self.gs_usb.is_kernel_driver_active(
            0
        ):
            self.gs_usb.detach_kernel_driver(0)

        # Only allow features that the device supports
        flags &= self.device_capability.feature

        # Only allow features that this driver supports
        supported = (
            GS_CAN_MODE_LISTEN_ONLY | GS_CAN_MODE_LOOP_BACK | GS_CAN_MODE_ONE_SHOT
            | GS_CAN_MODE_HW_TIMESTAMP | GS_CAN_MODE_FD | GS_CAN_MODE_PAD_PKTS_TO_MAX_PKT_SIZE
        )
        flags &= supported
        self.device_flags = flags

        mode = DeviceMode(GS_CAN_MODE_START, flags)
        self.gs_usb.ctrl_transfer(0x41, _GS_USB_BREQ_MODE, 0, 0, mode.pack())

    def stop(self):
        r"""
        Stop gs_usb device
        """
        mode = DeviceMode(GS_CAN_MODE_RESET, 0)
        try:
            self.gs_usb.ctrl_transfer(0x41, _GS_USB_BREQ_MODE, 0, 0, mode.pack())
        except usb.core.USBError:
            pass


    def set_bitrate(self, bitrate, sample_point=87.5):
        r"""
        Set bitrate with sample point 87.5% and clock rate 48MHz.
        Ported from https://github.com/HubertD/cangaroo/blob/b4a9d6d8db7fe649444d835a76dbae5f7d82c12f/src/driver/CandleApiDriver/CandleApiInterface.cpp#L17-L112

        It can also be calculated in http://www.bittiming.can-wiki.info/ with sample point 87.5% and clock rate 48MHz
        """
        prop_seg = 1
        sjw = 1

        if ((self.device_capability.fclk_can == 48000000) and (sample_point == 87.5)):
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
                self.set_timing(prop_seg, 12, 2, sjw, 3)
            else:
                return False
            return True
        elif ((self.device_capability.fclk_can == 80000000) and (sample_point == 87.5)):
            if bitrate == 10000:
                self.set_timing(prop_seg, 12, 2, sjw, 500)
            elif bitrate == 20000:
                self.set_timing(prop_seg, 12, 2, sjw, 250)
            elif bitrate == 50000:
                self.set_timing(prop_seg, 12, 2, sjw, 100)
            elif bitrate == 83333:
                self.set_timing(prop_seg, 12, 2, sjw, 60)
            elif bitrate == 100000:
                self.set_timing(prop_seg, 12, 2, sjw, 50)
            elif bitrate == 125000:
                self.set_timing(prop_seg, 12, 2, sjw, 40)
            elif bitrate == 250000:
                self.set_timing(prop_seg, 12, 2, sjw, 20)
            elif bitrate == 500000:
              self.set_timing(prop_seg, 12, 2, sjw, 10)
            elif bitrate == 800000:
                self.set_timing(prop_seg, 7, 1, sjw, 10)
            elif bitrate == 1000000:
                self.set_timing(prop_seg, 12, 2, sjw, 5)
            else:
                return False
            return True
        else:
            #device clk or sample point currently unsupported
            return False

    def set_timing(self, prop_seg, phase_seg1, phase_seg2, sjw, brp):
        r"""
        Set CAN bit timing
        :param prop_seg: propagation Segment (const 1)
        :param phase_seg1: phase segment 1 (1~15)
        :param phase_seg2: phase segment 2 (1~8)
        :param sjw: synchronization segment (1~4)
        :param brp: prescaler for quantum where base_clk = 48MHz (1~1024)
        """
        bit_timing = DeviceBitTiming(prop_seg, phase_seg1, phase_seg2, sjw, brp)
        self.gs_usb.ctrl_transfer(0x41, _GS_USB_BREQ_BITTIMING, 0, 0, bit_timing.pack())

    def set_data_bitrate(self, bitrate):
        r"""
        Set CAN FD data phase bitrate (80 MHz clock devices).
        Common rates: 1000000, 2000000, 4000000, 5000000, 8000000
        Returns True on success, False if bitrate is unsupported.
        """
        if self.device_capability.fclk_can == 80000000:
            # prop=0, timing computed for ~80% sample point
            if bitrate == 1000000:
                return self.set_data_timing(0, 15, 4, 4, 4)
            elif bitrate == 2000000:
                return self.set_data_timing(0, 15, 4, 4, 2)
            elif bitrate == 4000000:
                return self.set_data_timing(0, 15, 4, 4, 1)
            elif bitrate == 5000000:
                return self.set_data_timing(0, 12, 3, 3, 1)
            elif bitrate == 8000000:
                return self.set_data_timing(0, 7, 2, 2, 1)
        return False

    def set_data_timing(self, prop_seg, phase_seg1, phase_seg2, sjw, brp):
        r"""
        Set CAN FD data phase bit timing.
        :param prop_seg: propagation segment
        :param phase_seg1: phase segment 1
        :param phase_seg2: phase segment 2
        :param sjw: synchronization jump width
        :param brp: bit rate prescaler
        :return: True
        """
        bit_timing = DeviceBitTiming(prop_seg, phase_seg1, phase_seg2, sjw, brp)
        self.gs_usb.ctrl_transfer(0x41, _GS_USB_BREQ_DATA_BITTIMING, 0, 0, bit_timing.pack())
        return True

    def send(self, frame):
        r"""
        Send frame.
        :param frame: GsUsbFrame
        :return: True on success, False if the device rejected the write (e.g. bus-off)
        """
        # TX frames never carry a hardware timestamp (that field is RX-only, added by the device)
        try:
            self.gs_usb.write(0x02, frame.pack(hw_timestamp=False))
        except usb.core.USBTimeoutError:
            return False
        return True

    def read(self, frame, timeout_ms):
        r"""
        Read frame
        :param frame: GsUsbFrame
        :param timeout_ms: read time out in ms.
                           Note that timeout as 0 will block forever if no message is received
        :return: return True if success else False
        """
        hw_timestamps = bool(self.device_flags & GS_CAN_MODE_HW_TIMESTAMP)
        fd_mode = bool(self.device_flags & GS_CAN_MODE_FD)

        if fd_mode:
            max_size = GS_USB_FRAME_SIZE_FD_HW_TIMESTAMP if hw_timestamps else GS_USB_FRAME_SIZE_FD
        else:
            max_size = GS_USB_FRAME_SIZE_HW_TIMESTAMP if hw_timestamps else GS_USB_FRAME_SIZE

        try:
            data = self.gs_usb.read(0x81, max_size, timeout_ms)
        except usb.core.USBError:
            return False

        GsUsbFrame.unpack_into(frame, data, hw_timestamps)
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
        return DeviceInfo.unpack(data)

    @property
    def device_capability(self):
        r"""
        Get gs_usb device capability. Returns DeviceBtConstExtended for FD-capable devices
        that support the extended bit timing constant, DeviceCapability otherwise.
        """
        if self.capability is None:
            data = self.gs_usb.ctrl_transfer(0xC1, _GS_USB_BREQ_BT_CONST, 0, 0, 40)
            cap = DeviceCapability.unpack(data)
            if cap.feature & GS_CAN_FEATURE_BT_CONST_EXT:
                ext_data = self.gs_usb.ctrl_transfer(0xC1, _GS_USB_BREQ_BT_CONST_EXT, 0, 0, 72)
                self.capability = DeviceBtConstExtended.unpack(ext_data)
            else:
                self.capability = cap
        return self.capability

    def get_state(self):
        r"""
        Query the CAN controller state (error counters, bus-off, etc.).
        Returns a DeviceState, or None if the device does not support this request.
        """
        if not (self.device_capability.feature & GS_CAN_FEATURE_GET_STATE):
            return None
        try:
            data = self.gs_usb.ctrl_transfer(0xC1, _GS_USB_BREQ_GET_STATE, 0, 0, 12)
            return DeviceState.unpack(data)
        except usb.core.USBError:
            return None

    def identify(self, on):
        r"""
        Turn the device identify LED on or off.
        Returns True on success, False if the device does not support identify.
        """
        if not (self.device_capability.feature & GS_CAN_FEATURE_IDENTIFY):
            return False
        mode = 1 if on else 0
        self.gs_usb.ctrl_transfer(0x41, _GS_USB_BREQ_IDENTIFY, 0, 0, pack("<I", mode))
        return True

    def get_termination(self):
        r"""
        Read the built-in bus termination resistor state.
        Returns True if termination is active, False if off, None if unsupported.
        """
        if not (self.device_capability.feature & GS_CAN_FEATURE_TERMINATION):
            return None
        try:
            data = self.gs_usb.ctrl_transfer(0xC1, _GS_USB_BREQ_GET_TERMINATION, 0, 0, 4)
            return unpack("<I", data)[0] != 0
        except usb.core.USBError:
            return None

    def set_termination(self, on):
        r"""
        Enable or disable the built-in bus termination resistor.
        Returns True on success, False if the device does not support termination.
        """
        if not (self.device_capability.feature & GS_CAN_FEATURE_TERMINATION):
            return False
        state = 1 if on else 0
        self.gs_usb.ctrl_transfer(0x41, _GS_USB_BREQ_SET_TERMINATION, 0, 0, pack("<I", state))
        return True

    def __str__(self):
        try:
            _ = "{} ({})".format(self.gs_usb.product, repr(self.gs_usb))
        except (ValueError, usb.core.USBError):
            return ""
        return _

    is_gs_usb_device = staticmethod(lambda dev : (dev.idVendor == GS_USB_ID_VENDOR and dev.idProduct == GS_USB_ID_PRODUCT)\
            or (dev.idVendor == GS_USB_CANDLELIGHT_VENDOR_ID and dev.idProduct == GS_USB_CANDLELIGHT_PRODUCT_ID) \
            or (dev.idVendor == GS_USB_CES_CANEXT_FD_VENDOR_ID and dev.idProduct == GS_USB_CES_CANEXT_FD_PRODUCT_ID) \
            or (dev.idVendor == GS_USB_ABE_CANDEBUGGER_FD_VENDOR_ID and dev.idProduct == GS_USB_ABE_CANDEBUGGER_FD_PRODUCT_ID) \
            or (dev.idVendor == GS_USB_CANNECTIVITY_VENDOR_ID and dev.idProduct == GS_USB_CANNECTIVITY_PRODUCT_ID)) \

    @classmethod
    def scan(cls):
        r"""
        Retrieve the list of gs_usb devices handle
        :return: list of gs_usb devices handle
        """
        return [
            GsUsb(dev)
            for dev in usb.core.find(
                find_all=True,
                custom_match = cls.is_gs_usb_device,
                backend=libusb1.get_backend(),
            )
        ]

    @classmethod
    def find(cls, bus, address):
        r"""
        Find a specific gs_usb device
        :return: The gs_usb device handle if found, else None
        """
        gs_usb = usb.core.find(
            custom_match = cls.is_gs_usb_device,
            bus=bus,
            address=address,
            backend=libusb1.get_backend(),
        )
        if gs_usb:
            return GsUsb(gs_usb)
        return None
