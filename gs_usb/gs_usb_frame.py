from .constants import (
    CAN_EFF_FLAG, CAN_RTR_FLAG, CAN_ERR_FLAG, CAN_EFF_MASK,
    CAN_MAX_DLEN,
    CANFD_MAX_DLEN, CANFD_MAX_DLC, CANFD_DLC_TO_LEN,
    GS_CAN_FLAG_FD, GS_CAN_FLAG_BRS, GS_CAN_FLAG_ESI,
)
from struct import *

# gs_usb general
GS_USB_ECHO_ID = 0
GS_USB_NONE_ECHO_ID = 0xFFFFFFFF

GS_USB_FRAME_SIZE = 20
GS_USB_FRAME_SIZE_HW_TIMESTAMP = 24
GS_USB_FRAME_SIZE_FD = 76
GS_USB_FRAME_SIZE_FD_HW_TIMESTAMP = 80


class GsUsbFrame:
    def __init__(self, can_id=0, data=[], is_fd=False, bitrate_switch=False, error_state_indicator=False):
        self.echo_id = GS_USB_ECHO_ID
        self.can_id = can_id
        self.channel = 0
        self.flags = 0
        self.reserved = 0
        self.timestamp_us = 0

        if isinstance(data, bytes):
            data = list(data)

        if is_fd:
            self.flags |= GS_CAN_FLAG_FD
            if bitrate_switch:
                self.flags |= GS_CAN_FLAG_BRS
            if error_state_indicator:
                self.flags |= GS_CAN_FLAG_ESI
            # Find the smallest valid FD DLC that fits the data
            self.can_dlc = next(
                dlc for dlc, length in enumerate(CANFD_DLC_TO_LEN)
                if length >= len(data)
            )
            self.data = data + [0] * (CANFD_MAX_DLEN - len(data))
        else:
            self.can_dlc = len(data)
            self.data = data + [0] * (CAN_MAX_DLEN - len(data))

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
    def is_fd(self) -> bool:
        return bool(self.flags & GS_CAN_FLAG_FD)

    @property
    def is_bitrate_switch(self) -> bool:
        return bool(self.flags & GS_CAN_FLAG_BRS)

    @property
    def is_error_state_indicator(self) -> bool:
        return bool(self.flags & GS_CAN_FLAG_ESI)

    @property
    def data_length(self) -> int:
        if self.is_fd:
            return CANFD_DLC_TO_LEN[self.can_dlc] if self.can_dlc <= CANFD_MAX_DLC else CANFD_MAX_DLEN
        return self.can_dlc

    @property
    def timestamp(self):
        return self.timestamp_us / 1000000.0

    def __sizeof__(self, hw_timestamp):
        if self.is_fd:
            return GS_USB_FRAME_SIZE_FD_HW_TIMESTAMP if hw_timestamp else GS_USB_FRAME_SIZE_FD
        return GS_USB_FRAME_SIZE_HW_TIMESTAMP if hw_timestamp else GS_USB_FRAME_SIZE

    def __str__(self) -> str:
        if self.is_remote_frame:
            data_str = "remote request"
        else:
            data_str = " ".join("{:02X}".format(b) for b in self.data[:self.data_length])
        fd_flags = ""
        if self.is_fd:
            fd_flags = " FD"
            if self.is_bitrate_switch:
                fd_flags += " BRS"
            if self.is_error_state_indicator:
                fd_flags += " ESI"
        return "{: >8X}   [{}]{} {}".format(self.arbitration_id, self.data_length, fd_flags, data_str)

    def pack(self, hw_timestamp):
        if self.is_fd:
            data = (self.data + [0] * CANFD_MAX_DLEN)[:CANFD_MAX_DLEN]
            if hw_timestamp:
                return pack("<2I4B64BI",
                    self.echo_id, self.can_id, self.can_dlc, self.channel,
                    self.flags, self.reserved, *data, self.timestamp_us & 0xffffffff
                )
            else:
                return pack("<2I4B64B",
                    self.echo_id, self.can_id, self.can_dlc, self.channel,
                    self.flags, self.reserved, *data,
                )
        else:
            data = (self.data + [0] * CAN_MAX_DLEN)[:CAN_MAX_DLEN]
            if hw_timestamp:
                return pack("<2I12BI",
                    self.echo_id, self.can_id, self.can_dlc, self.channel,
                    self.flags, self.reserved, *data, self.timestamp_us & 0xffffffff
                )
            else:
                return pack("<2I12B",
                    self.echo_id, self.can_id, self.can_dlc, self.channel,
                    self.flags, self.reserved, *data,
                )

    @staticmethod
    def unpack_into(frame, data: bytes, hw_timestamp):
        data_len = len(data)
        if data_len in (GS_USB_FRAME_SIZE_FD, GS_USB_FRAME_SIZE_FD_HW_TIMESTAMP):
            if hw_timestamp:
                (
                    frame.echo_id, frame.can_id, frame.can_dlc, frame.channel,
                    frame.flags, frame.reserved, *frame.data, frame.timestamp_us,
                ) = unpack("<2I4B64BI", data)
            else:
                (
                    frame.echo_id, frame.can_id, frame.can_dlc, frame.channel,
                    frame.flags, frame.reserved, *frame.data,
                ) = unpack("<2I4B64B", data)
        else:
            if hw_timestamp:
                (
                    frame.echo_id, frame.can_id, frame.can_dlc, frame.channel,
                    frame.flags, frame.reserved, *frame.data, frame.timestamp_us,
                ) = unpack("<2I12BI", data)
            else:
                (
                    frame.echo_id, frame.can_id, frame.can_dlc, frame.channel,
                    frame.flags, frame.reserved, *frame.data,
                ) = unpack("<2I12B", data)
