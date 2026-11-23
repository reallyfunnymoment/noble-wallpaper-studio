"""Read-only information and bounded resource-checksum requests to FlySky HID.

Command 1 matches the original updater's discovery request and the supplied
firmware's metadata reply branch at 0x080864EA. There is deliberately no
arbitrary opcode, erase, update-mode, or firmware-write option. Resource CRC
requests are limited to the known resource range and at most 64 KiB each.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
from pathlib import Path
import secrets
import struct
import time
from inspect_connected_radio import inspect

REPORT_BYTES = 281
RESOURCE_START = 0x80000
RESOURCE_BYTES = 5695344


def info_request(sequence):
    report = bytearray(REPORT_BYTES)
    struct.pack_into('<II', report, 1, sequence, 1)
    return bytes(report)


def parse_info(report, sequence):
    if len(report) != REPORT_BYTES or report[0] != 0:
        raise ValueError('Unexpected HID report length or report ID')
    returned_sequence, command = struct.unpack_from('<II', report, 1)
    if returned_sequence != sequence or command != 1:
        raise ValueError('Reply does not match the information request')
    metadata = report[25:73]
    return dict(metadata_hex=metadata.hex(), metadata_words=[f'{v:08x}' for v in struct.unpack('<12I', metadata)],
                application_version_word=f'{struct.unpack_from("<I", metadata, 40)[0]:08x}',
                application_variant_word=f'{struct.unpack_from("<I", metadata, 44)[0]:08x}',
                capacity_measured=False)


class OVERLAPPED(C.Structure):
    _fields_ = [('Internal', C.c_size_t), ('InternalHigh', C.c_size_t),
                ('Offset', W.DWORD), ('OffsetHigh', W.DWORD), ('hEvent', W.HANDLE)]


def resource_crc_request(sequence, address, length):
    resource_end = RESOURCE_START+RESOURCE_BYTES
    final_sector = resource_end//4096*4096
    within_resource = (RESOURCE_START <= address < resource_end
                       and 1 <= length <= 65536 and address+length <= resource_end)
    # One explicitly bounded adjacent-sector check permits verifying padding
    # before an update; no arbitrary read addresses or larger range is exposed.
    final_sector_check = address == final_sector and length == 4096
    if not (within_resource or final_sector_check):
        raise ValueError('Checksum request is outside the known resource range.')
    report = bytearray(REPORT_BYTES)
    struct.pack_into('<IIIII', report, 1, sequence, 6, address, length, 0xffffffff)
    return bytes(report)


def exchange_readonly(request):
    if len(request) != REPORT_BYTES or request[0] != 0:
        raise ValueError('Invalid read-only request framing.')
    sequence, command = struct.unpack_from('<II', request, 1)
    if command == 1:
        expected = info_request(sequence)
    elif command == 6:
        expected = resource_crc_request(sequence, struct.unpack_from('<I', request, 9)[0],
                                        struct.unpack_from('<I', request, 13)[0])
    else:
        raise ValueError('Only information and bounded resource-checksum requests are permitted.')
    if request != expected:
        raise ValueError('Unexpected parameters in read-only request.')
    return _exchange_validated(request)


def _exchange_validated(request):
    """Transport only. Callers must enforce their command and address policy."""
    sequence, command = struct.unpack_from('<II', request, 1)
    candidates = [entry for entry in inspect()['interfaces']
                  if entry.get('vid') in ('284e', '9243') and entry.get('pid') == '8d09'
                  and entry.get('usage_page') == 'ff00' and entry.get('usage') == '0001'
                  and entry.get('input_report_bytes') == REPORT_BYTES
                  and entry.get('output_report_bytes') == REPORT_BYTES]
    if len(candidates) != 1:
        raise RuntimeError(f'Expected exactly one matching FlySky vendor interface; found {len(candidates)}.')
    kernel = C.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.CreateEventW.argtypes = [C.c_void_p, W.BOOL, W.BOOL, W.LPCWSTR]
    kernel.CreateEventW.restype = W.HANDLE
    for name in ('ReadFile', 'WriteFile'):
        fn = getattr(kernel, name)
        fn.argtypes = [W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.POINTER(OVERLAPPED)]
        fn.restype = W.BOOL
    kernel.GetOverlappedResultEx.argtypes = [W.HANDLE, C.POINTER(OVERLAPPED), C.POINTER(W.DWORD), W.DWORD, W.BOOL]
    kernel.GetOverlappedResult.argtypes = [W.HANDLE, C.POINTER(OVERLAPPED), C.POINTER(W.DWORD), W.BOOL]
    kernel.CancelIoEx.argtypes = [W.HANDLE, C.POINTER(OVERLAPPED)]
    handle = kernel.CreateFileW(candidates[0]['interface_path'], 0xc0000000, 3, None, 3, 0x40000000, None)
    if handle == C.c_void_p(-1).value:
        raise C.WinError(C.get_last_error())

    def transfer(name, buffer, timeout_ms):
        operation = OVERLAPPED()
        operation.hEvent = kernel.CreateEventW(None, True, False, None)
        if not operation.hEvent:
            raise C.WinError(C.get_last_error())
        transferred = W.DWORD()
        try:
            if not getattr(kernel, name)(handle, buffer, REPORT_BYTES, C.byref(transferred), C.byref(operation)):
                error = C.get_last_error()
                if error != 997:  # ERROR_IO_PENDING
                    raise C.WinError(error)
                if not kernel.GetOverlappedResultEx(handle, C.byref(operation), C.byref(transferred), timeout_ms, False):
                    error = C.get_last_error()
                    kernel.CancelIoEx(handle, C.byref(operation))
                    # Complete cancellation before releasing the operation or its buffer.
                    kernel.GetOverlappedResult(handle, C.byref(operation), C.byref(transferred), True)
                    if error == 258:
                        raise TimeoutError(f'{name} timed out; operation canceled.')
                    raise C.WinError(error)
            return transferred.value
        finally:
            kernel.CloseHandle(operation.hEvent)
    try:
        outgoing = C.create_string_buffer(request, REPORT_BYTES)
        if transfer('WriteFile', outgoing, 2000) != REPORT_BYTES:
            raise RuntimeError('USB request was not fully transferred.')
        deadline = time.monotonic() + 3
        for _ in range(16):
            incoming = C.create_string_buffer(REPORT_BYTES)
            count = transfer('ReadFile', incoming, max(1, round((deadline-time.monotonic())*1000)))
            reply = incoming.raw[:count]
            if len(reply) == REPORT_BYTES and struct.unpack_from('<I', reply, 1)[0] == sequence:
                if reply[0] != 0 or struct.unpack_from('<I', reply, 5)[0] != command:
                    raise ValueError('Unexpected USB reply framing or command.')
                return reply, candidates[0]['vid']
            if time.monotonic() >= deadline:
                break
        raise TimeoutError('No matching information reply within the bounded receive window.')
    finally:
        kernel.CloseHandle(handle)


def probe():
    sequence = secrets.randbelow(0xfffffffe) + 1
    request = info_request(sequence)
    reply, vid = exchange_readonly(request)
    result = parse_info(reply, sequence)
    result.update(vid=vid, pid='8d09', command=1, requests_sent=1,
                  request_hex=request.hex(), reply_hex=reply.hex(),
                  reply_sha256=hashlib.sha256(reply).hexdigest(),
                  operation='Fixed metadata query only; no flash or settings writes requested.')
    return result


def probe_resource_crc(address=RESOURCE_START, length=4096):
    sequence = secrets.randbelow(0xfffffffe) + 1
    request = resource_crc_request(sequence, address, length)
    reply, vid = exchange_readonly(request)
    return dict(vid=vid, pid='8d09', command=6, requests_sent=1, address=address, length=length,
                returned_crc_word=f'{struct.unpack_from("<I", reply, 17)[0]:08x}',
                request_hex=request.hex(), reply_hex=reply.hex(),
                operation='Bounded resource-checksum request only; no erase/program request.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('radio_info_reply.json'))
    args = parser.parse_args()
    result = probe()
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
