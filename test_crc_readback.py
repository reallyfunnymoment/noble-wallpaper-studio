"""Offline proof of four-byte CRC inversion; no connected-device access."""
import random
import struct
import unittest
from unittest.mock import patch
from crc_readback import crc, decode_four_bytes, read_four_bytes


class ReadbackTests(unittest.TestCase):
    def test_all_basis_vectors_and_zero(self):
        for value in [0, 0xffffffff]+[1 << i for i in range(32)]:
            data = struct.pack('<I', value)
            self.assertEqual(decode_four_bytes(crc(data)), data)

    def test_random_independent_values(self):
        rng = random.Random(1031)
        for _ in range(10000):
            data = struct.pack('<I', rng.getrandbits(32))
            self.assertEqual(decode_four_bytes(crc(data)), data)

    def test_readback_uses_only_four_byte_resource_query(self):
        calls = []
        def query(address, length):
            calls.append((address, length))
            return {'returned_crc_word': f'{crc(bytes.fromhex("1234abcd")):08x}'}
        self.assertEqual(read_four_bytes(0x80002, query), bytes.fromhex('1234abcd'))
        self.assertEqual(calls, [(0x80002, 4)])
        for address in (0, 0x7ffff, 0x5ee76d):
            with self.assertRaises(ValueError):
                read_four_bytes(address, query)
        self.assertEqual(len(calls), 1)

    def test_probe_recovers_unknown_wallpaper_without_local_baseline(self):
        import probe_crc_readback as investigation
        stock = bytes(range(32))
        offset = investigation.SLOTS['scenery'][1]
        wallpaper = random.Random(31).randbytes(32)
        calls = []
        def query(address, length):
            start = address-0x80000
            calls.append((address, length))
            data = (stock[start:start+length] if start < 32 else
                    wallpaper[start-offset:start-offset+length])
            self.assertEqual(len(data), length)
            return {'returned_crc_word': f'{crc(data):08x}'}
        with patch.object(investigation, 'probe', return_value=dict(
                application_version_word='0000001f', application_variant_word='00010000')), \
                patch.object(investigation, 'read_stock_resource', return_value=stock), \
                patch.object(investigation, 'probe_resource_crc', side_effect=query), \
                patch('radio_info_probe.probe_resource_crc', side_effect=query):
            result = investigation.investigate()
        self.assertTrue(result['byte_readback_proof'])
        self.assertFalse(result['regions'][1]['matches_stock_reference'])
        self.assertEqual(len(calls), 19)


if __name__ == '__main__':
    unittest.main(verbosity=2)
