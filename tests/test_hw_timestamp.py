"""server/hw_timestamp.py: the NIC setting is read first, changed only when safe, and restored.

A fake driver replaces fcntl.ioctl.  Like the kernel, it follows the pointer packed into
struct ifreq and reads/writes the caller's real hwtstamp_config memory.
"""
import errno
import struct
import unittest
from unittest import mock

from server import hw_timestamp as hw
from server.kernel_clock import KernelClockSocket, RouteInfo


class FakeDriver:
    def __init__(self, cur=(0, 0, 0), get_errno=None, set_errno=None, grant=None):
        self.cur, self.get_errno, self.set_errno, self.grant = list(cur), get_errno, set_errno, grant
        self.calls = []

    def ioctl(self, _fd, request, ifreq):
        _name, ptr = struct.unpack_from("@16sP", ifreq)
        cfg = hw.HwtstampConfig.from_address(ptr)
        if request == hw.SIOCGHWTSTAMP:
            self.calls.append("GET")
            if self.get_errno:
                raise OSError(self.get_errno, "fake")
            cfg.flags, cfg.tx_type, cfg.rx_filter = self.cur
        else:
            self.calls.append(("SET", cfg.tx_type, cfg.rx_filter))
            if self.set_errno:
                raise OSError(self.set_errno, "fake")
            self.cur = [cfg.flags, cfg.tx_type, cfg.rx_filter if self.grant is None else self.grant]
            cfg.rx_filter = self.cur[2]
        return ifreq


class HwTimestampTest(unittest.TestCase):
    def drive(self, driver):
        patcher = mock.patch.object(hw.fcntl, "ioctl", driver.ioctl)
        patcher.start()
        self.addCleanup(patcher.stop)
        return hw.configure_hw_timestamping("eth0")

    def test_enable_then_restore_keeps_tx_setting(self):
        drv = FakeDriver(cur=(0, 1, 0))                     # TX stamping on (e.g. ptp4l), RX off
        st = self.drive(drv)
        self.assertTrue(st.hardware)
        self.assertEqual(drv.cur, [0, 1, hw.HWTSTAMP_FILTER_ALL])
        self.assertIsNone(hw.restore_hw_timestamping(st))
        self.assertEqual(drv.cur, [0, 1, 0])
        self.assertIsNone(hw.restore_hw_timestamping(st))  # second restore is a no-op
        self.assertEqual(drv.calls.count("GET"), 1)

    def test_unreadable_setting_is_left_alone(self):
        drv = FakeDriver(get_errno=errno.EOPNOTSUPP)        # lo, veth, Wi-Fi, GNS3 taps
        st = self.drive(drv)
        self.assertFalse(st.hardware)
        self.assertEqual(drv.calls, ["GET"])

    def test_someone_elses_setting_is_left_alone(self):
        drv = FakeDriver(cur=(0, 1, 12))                    # a PTP filter is already active
        st = self.drive(drv)
        self.assertEqual(drv.calls, ["GET"])
        self.assertFalse(st.hardware)                       # PTP-only filters never stamp ICMP
        self.assertIsNone(st.previous)

    def test_already_all_is_used_but_not_owned(self):
        st = self.drive(FakeDriver(cur=(0, 0, hw.HWTSTAMP_FILTER_ALL)))
        self.assertTrue(st.hardware)
        self.assertIsNone(st.previous)

    def test_driver_granting_nothing_reports_software_only(self):
        drv = FakeDriver(grant=0)
        st = self.drive(drv)
        self.assertFalse(st.hardware)
        self.assertIsNotNone(st.previous)                   # we still issued a SET, so restore it

    def test_permission_errors_never_raise(self):
        self.assertIn("CAP_NET_ADMIN", self.drive(FakeDriver(get_errno=errno.EPERM)).reason)
        self.assertIn("CAP_NET_ADMIN", self.drive(FakeDriver(set_errno=errno.EPERM)).reason)

    def test_socket_close_restores_even_without_an_open_socket(self):
        drv = FakeDriver()
        k = KernelClockSocket([RouteInfo("10.0.0.1", "eth0", "10.0.0.2")])
        k._hw.append(self.drive(drv))
        self.assertEqual(drv.cur[2], hw.HWTSTAMP_FILTER_ALL)
        k.close()
        self.assertEqual(drv.cur, [0, 0, 0])
        k.close()                                           # idempotent


if __name__ == "__main__":
    unittest.main()
