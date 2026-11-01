"""server/kernel_clock.py: ICMP packet bytes and the checksum."""
import struct
import unittest

from server.kernel_clock import ICMP_ECHO_REQUEST, PAYLOAD_LEN, build_echo_request, icmp_checksum


class PacketTest(unittest.TestCase):
    def test_layout(self):
        pkt = build_echo_request(0x1234, 7)
        self.assertEqual(len(pkt), 8 + PAYLOAD_LEN)
        typ, code, _csum, ident, seq = struct.unpack("!BBHHH", pkt[:8])
        self.assertEqual((typ, code, ident, seq), (ICMP_ECHO_REQUEST, 0, 0x1234, 7))
        self.assertEqual(pkt[8:16], b"EPHEMRES")
        self.assertEqual(struct.unpack("!HH", pkt[16:20]), (0x1234, 7))
        self.assertTrue(all(b == 0xA5 for b in pkt[20:]))

    def test_checksum_verifies(self):
        # A receiver sums the whole packet INCLUDING the checksum field; a valid packet gives 0.
        for ident, seq in ((0, 0), (0x1000, 1), (0xFFFF, 0xFFFF)):
            self.assertEqual(icmp_checksum(build_echo_request(ident, seq)), 0)

    def test_checksum_known_value_and_odd_length(self):
        # RFC 1071 section 3 example: words 0001 f203 f4f5 f6f7 sum to ddf2, checksum 220d.
        self.assertEqual(icmp_checksum(bytes.fromhex("0001f203f4f5f6f7")), 0x220D)
        self.assertEqual(icmp_checksum(b"\x01"), icmp_checksum(b"\x01\x00"))   # odd length is zero-padded


if __name__ == "__main__":
    unittest.main()
