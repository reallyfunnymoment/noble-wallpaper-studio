"""Offline checks only. Never calls the probe or opens device handles."""
import struct
import unittest
from radio_info_probe import info_request, parse_info


class ProtocolTests(unittest.TestCase):
    def test_only_information_opcode_and_zero_parameters(self):
        request = info_request(0x12345678)
        self.assertEqual(len(request), 281)
        self.assertEqual(request[0], 0)
        self.assertEqual(struct.unpack_from('<II', request, 1), (0x12345678, 1))
        self.assertEqual(request[9:], bytes(272))

    def test_reply_is_bound_to_the_expected_request(self):
        reply = bytearray(info_request(17))
        struct.pack_into('<12I', reply, 25, *range(12))
        result = parse_info(reply, 17)
        self.assertEqual(result['application_version_word'], '0000000a')
        self.assertFalse(result['capacity_measured'])
        for invalid in (reply[:-1], bytes([1])+reply[1:], info_request(18)):
            with self.assertRaises(ValueError):
                parse_info(invalid, 17)
        struct.pack_into('<I', reply, 5, 5)
        with self.assertRaises(ValueError):
            parse_info(reply, 17)


if __name__ == '__main__':
    unittest.main(verbosity=2)
