from .can import CAN_EFF_FLAG, CAN_RTR_FLAG, CAN_ERR_FLAG, CAN_EFF_MASK

# gs_usb general
GS_USB_ECHO_ID = 0
GS_USB_NONE_ECHO_ID = 0xFFFFFFFF
GS_USB_FRAME_SIZE = 24


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

        if not self.can_id:
            raise ValueError("CAN ID is not set")

    def __sizeof__(self):
        return GS_USB_FRAME_SIZE

    @property
    def arbitration_id(self) -> int:
        return self.can_id & CAN_EFF_MASK

    @property
    def is_extended_id(self) -> bool:
        return bool(self.can_id & CAN_EFF_FLAG)

    @property
    def is_remote_frame(self) -> bool:
        return bool(self.can_id & CAN_RTR_FLAG)

    @property
    def is_error_frame(self) -> bool:
        return bool(self.can_id & CAN_ERR_FLAG)

    @property
    def timestamp(self):
        return self.timestamp_us / 1000000.0
