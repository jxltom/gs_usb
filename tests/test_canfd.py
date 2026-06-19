"""Unit tests for CAN FD support — no hardware required."""
import pytest
from struct import pack, unpack

from gs_usb.gs_usb_frame import (
    GsUsbFrame,
    GS_USB_FRAME_SIZE, GS_USB_FRAME_SIZE_HW_TIMESTAMP,
    GS_USB_FRAME_SIZE_FD, GS_USB_FRAME_SIZE_FD_HW_TIMESTAMP,
    GS_USB_ECHO_ID,
)
from gs_usb.gs_usb_structures import DeviceBtConstExtended
from gs_usb.constants import (
    CAN_EFF_FLAG, CAN_RTR_FLAG, CAN_ERR_FLAG,
    CANFD_DLC_TO_LEN, CANFD_MAX_DLC, CANFD_MAX_DLEN,
    GS_CAN_FLAG_FD, GS_CAN_FLAG_BRS, GS_CAN_FLAG_ESI,
)


# ---------------------------------------------------------------------------
# CANFD_DLC_TO_LEN table
# ---------------------------------------------------------------------------

class TestDlcToLen:
    def test_classic_range(self):
        for dlc in range(9):
            assert CANFD_DLC_TO_LEN[dlc] == dlc

    def test_fd_range(self):
        expected = {9: 12, 10: 16, 11: 20, 12: 24, 13: 32, 14: 48, 15: 64}
        for dlc, length in expected.items():
            assert CANFD_DLC_TO_LEN[dlc] == length

    def test_max_dlc(self):
        assert CANFD_MAX_DLC == 15
        assert CANFD_DLC_TO_LEN[CANFD_MAX_DLC] == CANFD_MAX_DLEN


# ---------------------------------------------------------------------------
# Frame sizes
# ---------------------------------------------------------------------------

class TestFrameSizes:
    def test_classic_sizes(self):
        assert GS_USB_FRAME_SIZE == 20
        assert GS_USB_FRAME_SIZE_HW_TIMESTAMP == 24

    def test_fd_sizes(self):
        assert GS_USB_FRAME_SIZE_FD == 76
        assert GS_USB_FRAME_SIZE_FD_HW_TIMESTAMP == 80


# ---------------------------------------------------------------------------
# Classic frame creation
# ---------------------------------------------------------------------------

class TestClassicFrame:
    def test_default_frame(self):
        f = GsUsbFrame()
        assert f.can_id == 0
        assert f.can_dlc == 0
        assert f.data == [0] * 8
        assert f.is_fd is False
        assert f.is_bitrate_switch is False
        assert f.is_error_state_indicator is False
        assert f.data_length == 0

    def test_frame_with_bytes(self):
        data = b"\x01\x02\x03\x04"
        f = GsUsbFrame(can_id=0x123, data=data)
        assert f.can_dlc == 4
        assert f.data_length == 4
        assert f.data[:4] == [1, 2, 3, 4]
        assert f.data[4:] == [0, 0, 0, 0]

    def test_frame_with_list(self):
        data = [0xAA, 0xBB]
        f = GsUsbFrame(can_id=0x7FF, data=data)
        assert f.can_dlc == 2
        assert f.data[:2] == [0xAA, 0xBB]

    def test_extended_id_flag(self):
        f = GsUsbFrame(can_id=0x12345678 | CAN_EFF_FLAG)
        assert f.is_extended_id is True
        assert f.arbitration_id == 0x12345678

    def test_rtr_flag(self):
        f = GsUsbFrame(can_id=0x7FF | CAN_RTR_FLAG)
        assert f.is_remote_frame is True

    def test_err_flag(self):
        f = GsUsbFrame(can_id=0x7FF | CAN_ERR_FLAG)
        assert f.is_error_frame is True

    def test_is_not_fd(self):
        f = GsUsbFrame(can_id=0x100, data=[1, 2, 3])
        assert f.is_fd is False
        assert f.flags & GS_CAN_FLAG_FD == 0


# ---------------------------------------------------------------------------
# FD frame creation
# ---------------------------------------------------------------------------

class TestFdFrame:
    def test_fd_flag_set(self):
        f = GsUsbFrame(can_id=0x1, data=[0] * 8, is_fd=True)
        assert f.is_fd is True
        assert f.flags & GS_CAN_FLAG_FD != 0

    def test_brs_flag(self):
        f = GsUsbFrame(can_id=0x1, data=[], is_fd=True, bitrate_switch=True)
        assert f.is_bitrate_switch is True
        assert f.flags & GS_CAN_FLAG_BRS != 0

    def test_esi_flag(self):
        f = GsUsbFrame(can_id=0x1, data=[], is_fd=True, error_state_indicator=True)
        assert f.is_error_state_indicator is True
        assert f.flags & GS_CAN_FLAG_ESI != 0

    def test_brs_esi_together(self):
        f = GsUsbFrame(can_id=0x1, data=[], is_fd=True, bitrate_switch=True, error_state_indicator=True)
        assert f.is_bitrate_switch is True
        assert f.is_error_state_indicator is True

    def test_fd_data_padded_to_64(self):
        f = GsUsbFrame(can_id=0x1, data=[0xAB] * 12, is_fd=True)
        assert len(f.data) == 64
        assert f.data[:12] == [0xAB] * 12
        assert f.data[12:] == [0] * 52

    @pytest.mark.parametrize("data_len,expected_dlc,expected_payload", [
        (0,  0,  0),
        (1,  1,  1),
        (8,  8,  8),
        (9,  9,  12),
        (12, 9,  12),
        (13, 10, 16),
        (16, 10, 16),
        (20, 11, 20),
        (24, 12, 24),
        (32, 13, 32),
        (33, 14, 48),
        (48, 14, 48),
        (49, 15, 64),
        (64, 15, 64),
    ])
    def test_dlc_encoding(self, data_len, expected_dlc, expected_payload):
        f = GsUsbFrame(can_id=0x1, data=[0xCC] * data_len, is_fd=True)
        assert f.can_dlc == expected_dlc
        assert f.data_length == expected_payload

    def test_data_length_property(self):
        f = GsUsbFrame(can_id=0x1, data=b"\xFF" * 32, is_fd=True)
        assert f.data_length == 32
        assert f.can_dlc == 13


# ---------------------------------------------------------------------------
# Pack — classic
# ---------------------------------------------------------------------------

class TestClassicPack:
    def test_pack_size_no_ts(self):
        f = GsUsbFrame(can_id=0x7FF, data=[1, 2, 3, 4, 5, 6, 7, 8])
        assert len(f.pack(hw_timestamp=False)) == GS_USB_FRAME_SIZE

    def test_pack_size_with_ts(self):
        f = GsUsbFrame(can_id=0x7FF, data=[1, 2, 3, 4, 5, 6, 7, 8])
        assert len(f.pack(hw_timestamp=True)) == GS_USB_FRAME_SIZE_HW_TIMESTAMP

    def test_pack_fields(self):
        f = GsUsbFrame(can_id=0x123, data=[0xAA, 0xBB])
        raw = f.pack(hw_timestamp=False)
        echo_id, can_id, dlc, ch, flags, res, *data = unpack("<2I12B", raw)
        assert echo_id == GS_USB_ECHO_ID
        assert can_id == 0x123
        assert dlc == 2
        assert data[:2] == [0xAA, 0xBB]


# ---------------------------------------------------------------------------
# Pack — FD
# ---------------------------------------------------------------------------

class TestFdPack:
    def test_pack_size_no_ts(self):
        f = GsUsbFrame(can_id=0x1, data=[0xFF] * 64, is_fd=True)
        assert len(f.pack(hw_timestamp=False)) == GS_USB_FRAME_SIZE_FD

    def test_pack_size_with_ts(self):
        f = GsUsbFrame(can_id=0x1, data=[0xFF] * 64, is_fd=True)
        assert len(f.pack(hw_timestamp=True)) == GS_USB_FRAME_SIZE_FD_HW_TIMESTAMP

    def test_pack_fd_flag_in_frame_flags(self):
        f = GsUsbFrame(can_id=0x1, data=[0xAB] * 12, is_fd=True, bitrate_switch=True)
        raw = f.pack(hw_timestamp=False)
        _echo_id, _can_id, _dlc, _ch, frame_flags, _res, *data = unpack("<2I4B64B", raw)
        assert frame_flags & GS_CAN_FLAG_FD != 0
        assert frame_flags & GS_CAN_FLAG_BRS != 0

    def test_pack_data_fields(self):
        payload = list(range(64))
        f = GsUsbFrame(can_id=0x7FF, data=payload, is_fd=True)
        raw = f.pack(hw_timestamp=False)
        _echo_id, _can_id, _dlc, _ch, _flags, _res, *data = unpack("<2I4B64B", raw)
        assert data == payload


# ---------------------------------------------------------------------------
# Unpack — classic
# ---------------------------------------------------------------------------

class TestClassicUnpack:
    def _make_raw(self, can_id, dlc, data_bytes, ts=None):
        data_bytes = (data_bytes + [0] * 8)[:8]
        if ts is not None:
            return pack("<2I12BI", GS_USB_ECHO_ID, can_id, dlc, 0, 0, 0, *data_bytes, ts)
        return pack("<2I12B", GS_USB_ECHO_ID, can_id, dlc, 0, 0, 0, *data_bytes)

    def test_roundtrip_no_ts(self):
        original = GsUsbFrame(can_id=0x456, data=[1, 2, 3, 4])
        raw = original.pack(hw_timestamp=False)
        received = GsUsbFrame()
        GsUsbFrame.unpack_into(received, raw, hw_timestamp=False)
        assert received.can_id == 0x456
        assert received.can_dlc == 4
        assert received.data[:4] == [1, 2, 3, 4]
        assert received.is_fd is False

    def test_roundtrip_with_ts(self):
        original = GsUsbFrame(can_id=0x100, data=[0xDE, 0xAD])
        original.timestamp_us = 123456
        raw = original.pack(hw_timestamp=True)
        received = GsUsbFrame()
        GsUsbFrame.unpack_into(received, raw, hw_timestamp=True)
        assert received.can_id == 0x100
        assert received.timestamp_us == 123456


# ---------------------------------------------------------------------------
# Unpack — FD
# ---------------------------------------------------------------------------

class TestFdUnpack:
    def test_roundtrip_fd_no_ts(self):
        payload = list(range(32))
        original = GsUsbFrame(can_id=0x7FF, data=payload, is_fd=True, bitrate_switch=True)
        raw = original.pack(hw_timestamp=False)
        assert len(raw) == GS_USB_FRAME_SIZE_FD

        received = GsUsbFrame()
        GsUsbFrame.unpack_into(received, raw, hw_timestamp=False)
        assert received.is_fd is True
        assert received.is_bitrate_switch is True
        assert received.can_dlc == 13  # 32 bytes → DLC 13
        assert received.data_length == 32
        assert list(received.data[:32]) == payload

    def test_roundtrip_fd_with_ts(self):
        payload = [0xAB] * 64
        original = GsUsbFrame(can_id=0x1, data=payload, is_fd=True)
        original.timestamp_us = 999
        raw = original.pack(hw_timestamp=True)
        assert len(raw) == GS_USB_FRAME_SIZE_FD_HW_TIMESTAMP

        received = GsUsbFrame()
        GsUsbFrame.unpack_into(received, raw, hw_timestamp=True)
        assert received.is_fd is True
        assert received.data_length == 64
        assert list(received.data) == payload
        assert received.timestamp_us == 999

    def test_unpack_detects_fd_by_length(self):
        # A raw FD packet (76 bytes) should be detected as FD
        payload = [0x11] * 64
        flags = GS_CAN_FLAG_FD | GS_CAN_FLAG_BRS
        raw = pack("<2I4B64B", GS_USB_ECHO_ID, 0x7FF, 15, 0, flags, 0, *payload)
        assert len(raw) == GS_USB_FRAME_SIZE_FD

        f = GsUsbFrame()
        GsUsbFrame.unpack_into(f, raw, hw_timestamp=False)
        assert f.is_fd is True
        assert f.can_dlc == 15
        assert f.data_length == 64

    def test_unpack_classic_still_works_in_fd_context(self):
        # Classic 20-byte frame should still unpack correctly even when hw_timestamp=False
        payload = [0xCC] * 8
        raw = pack("<2I12B", GS_USB_ECHO_ID, 0x123, 8, 0, 0, 0, *payload)
        assert len(raw) == GS_USB_FRAME_SIZE

        f = GsUsbFrame()
        GsUsbFrame.unpack_into(f, raw, hw_timestamp=False)
        assert f.is_fd is False
        assert f.can_dlc == 8
        assert list(f.data) == payload


# ---------------------------------------------------------------------------
# __sizeof__
# ---------------------------------------------------------------------------

class TestSizeof:
    def test_classic_sizeof(self):
        f = GsUsbFrame()
        assert f.__sizeof__(hw_timestamp=False) == GS_USB_FRAME_SIZE
        assert f.__sizeof__(hw_timestamp=True) == GS_USB_FRAME_SIZE_HW_TIMESTAMP

    def test_fd_sizeof(self):
        f = GsUsbFrame(is_fd=True)
        assert f.__sizeof__(hw_timestamp=False) == GS_USB_FRAME_SIZE_FD
        assert f.__sizeof__(hw_timestamp=True) == GS_USB_FRAME_SIZE_FD_HW_TIMESTAMP


# ---------------------------------------------------------------------------
# __str__
# ---------------------------------------------------------------------------

class TestStr:
    def test_classic_str(self):
        f = GsUsbFrame(can_id=0x7FF, data=[0xAA, 0xBB])
        s = str(f)
        assert "AA BB" in s
        assert "FD" not in s

    def test_fd_str_shows_fd(self):
        f = GsUsbFrame(can_id=0x7FF, data=[0x01] * 12, is_fd=True)
        s = str(f)
        assert "FD" in s
        assert "BRS" not in s

    def test_fd_str_shows_brs(self):
        f = GsUsbFrame(can_id=0x7FF, data=[0x01], is_fd=True, bitrate_switch=True)
        s = str(f)
        assert "FD" in s
        assert "BRS" in s

    def test_fd_str_shows_esi(self):
        f = GsUsbFrame(can_id=0x7FF, data=[], is_fd=True, error_state_indicator=True)
        s = str(f)
        assert "ESI" in s

    def test_fd_str_data_length(self):
        f = GsUsbFrame(can_id=0x7FF, data=[0xAB] * 32, is_fd=True)
        s = str(f)
        assert "[32]" in s


# ---------------------------------------------------------------------------
# DeviceBtConstExtended
# ---------------------------------------------------------------------------

class TestDeviceBtConstExtended:
    def _make_raw(self):
        # 18 x uint32 LE
        return pack("<18I",
            0x5FF,      # feature
            80000000,   # fclk_can
            1, 16,      # tseg1 min/max
            1, 8,       # tseg2 min/max
            4,          # sjw_max
            1, 512, 1,  # brp min/max/inc
            1, 16,      # dtseg1 min/max
            1, 8,       # dtseg2 min/max
            4,          # dsjw_max
            1, 32, 1,   # dbrp min/max/inc
        )

    def test_unpack_size(self):
        from struct import calcsize
        assert calcsize("<18I") == 72

    def test_unpack_fields(self):
        raw = self._make_raw()
        cap = DeviceBtConstExtended.unpack(raw)
        assert cap.feature == 0x5FF
        assert cap.fclk_can == 80000000
        assert cap.tseg1_min == 1
        assert cap.tseg1_max == 16
        assert cap.dtseg1_min == 1
        assert cap.dtseg1_max == 16
        assert cap.dbrp_max == 32

    def test_str(self):
        raw = self._make_raw()
        cap = DeviceBtConstExtended.unpack(raw)
        s = str(cap)
        assert "80000000" in s
        assert "Data" in s
