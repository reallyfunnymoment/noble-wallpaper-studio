"""Read Windows' cached FlySky HID interface descriptions. No HID reports sent.

Opens matching device handles with desired access 0, asks Windows for attributes
and parsed capabilities, then closes them. Never calls ReadFile, WriteFile,
HidD_SetFeature, HidD_GetFeature, or any firmware command.
"""
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import sys


class GUID(C.Structure):
    _fields_ = [('Data1', W.DWORD), ('Data2', W.WORD), ('Data3', W.WORD), ('Data4', C.c_ubyte*8)]


class INTERFACE(C.Structure):
    _fields_ = [('cbSize', W.DWORD), ('InterfaceClassGuid', GUID),
                ('Flags', W.DWORD), ('Reserved', C.c_size_t)]


class ATTRIBUTES(C.Structure):
    _fields_ = [('Size', W.ULONG), ('VendorID', W.USHORT),
                ('ProductID', W.USHORT), ('VersionNumber', W.USHORT)]


class CAPS(C.Structure):
    _fields_ = [('Usage', W.USHORT), ('UsagePage', W.USHORT),
                ('InputReportByteLength', W.USHORT), ('OutputReportByteLength', W.USHORT),
                ('FeatureReportByteLength', W.USHORT), ('Reserved', W.USHORT*17),
                ('NumberLinkCollectionNodes', W.USHORT), ('NumberInputButtonCaps', W.USHORT),
                ('NumberInputValueCaps', W.USHORT), ('NumberInputDataIndices', W.USHORT),
                ('NumberOutputButtonCaps', W.USHORT), ('NumberOutputValueCaps', W.USHORT),
                ('NumberOutputDataIndices', W.USHORT), ('NumberFeatureButtonCaps', W.USHORT),
                ('NumberFeatureValueCaps', W.USHORT), ('NumberFeatureDataIndices', W.USHORT)]


def inspect():
    if sys.platform != 'win32':
        raise RuntimeError('This descriptor inspection requires Windows Python.')
    setup = C.WinDLL('setupapi', use_last_error=True)
    hid = C.WinDLL('hid', use_last_error=True)
    kernel = C.WinDLL('kernel32', use_last_error=True)
    hid.HidD_GetHidGuid.argtypes = [C.POINTER(GUID)]
    setup.SetupDiGetClassDevsW.argtypes = [C.POINTER(GUID), W.LPCWSTR, W.HWND, W.DWORD]
    setup.SetupDiGetClassDevsW.restype = W.HANDLE
    setup.SetupDiEnumDeviceInterfaces.argtypes = [W.HANDLE, C.c_void_p, C.POINTER(GUID), W.DWORD, C.POINTER(INTERFACE)]
    setup.SetupDiGetDeviceInterfaceDetailW.argtypes = [W.HANDLE, C.POINTER(INTERFACE), C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p]
    setup.SetupDiDestroyDeviceInfoList.argtypes = [W.HANDLE]
    kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    hid.HidD_GetAttributes.argtypes = [W.HANDLE, C.POINTER(ATTRIBUTES)]
    hid.HidD_GetPreparsedData.argtypes = [W.HANDLE, C.POINTER(C.c_void_p)]
    hid.HidP_GetCaps.argtypes = [C.c_void_p, C.POINTER(CAPS)]
    hid.HidP_GetCaps.restype = C.c_long
    hid.HidD_FreePreparsedData.argtypes = [C.c_void_p]
    invalid = C.c_void_p(-1).value
    guid = GUID()
    hid.HidD_GetHidGuid(C.byref(guid))
    devices = setup.SetupDiGetClassDevsW(C.byref(guid), None, None, 0x12)
    if devices == invalid:
        raise C.WinError(C.get_last_error())
    found = []
    try:
        index = 0
        while True:
            interface = INTERFACE()
            interface.cbSize = C.sizeof(interface)
            if not setup.SetupDiEnumDeviceInterfaces(devices, None, C.byref(guid), index, C.byref(interface)):
                error = C.get_last_error()
                if error == 259:
                    break
                raise C.WinError(error)
            index += 1
            required = W.DWORD()
            setup.SetupDiGetDeviceInterfaceDetailW(devices, C.byref(interface), None, 0, C.byref(required), None)
            detail = C.create_string_buffer(required.value)
            C.cast(detail, C.POINTER(W.DWORD))[0] = 8 if C.sizeof(C.c_void_p) == 8 else 6
            if not setup.SetupDiGetDeviceInterfaceDetailW(devices, C.byref(interface), detail, required, None, None):
                raise C.WinError(C.get_last_error())
            path = C.wstring_at(C.addressof(detail) + 4)
            if not any(v in path.lower() for v in ('vid_284e', 'vid_9243')):
                continue
            record = dict(interface_path=path)
            found.append(record)
            # Zero desired access, both sharing flags, OPEN_EXISTING. Metadata only.
            handle = kernel.CreateFileW(path, 0, 3, None, 3, 0, None)
            if handle == invalid:
                record['metadata_error'] = str(C.WinError(C.get_last_error()))
                continue
            try:
                attributes = ATTRIBUTES()
                attributes.Size = C.sizeof(attributes)
                if hid.HidD_GetAttributes(handle, C.byref(attributes)):
                    record.update(vid=f'{attributes.VendorID:04x}', pid=f'{attributes.ProductID:04x}',
                                  version=f'{attributes.VersionNumber:04x}')
                preparsed = C.c_void_p()
                if not hid.HidD_GetPreparsedData(handle, C.byref(preparsed)):
                    raise C.WinError(C.get_last_error())
                try:
                    caps = CAPS()
                    status = hid.HidP_GetCaps(preparsed, C.byref(caps))
                    if status != 0x00110000:
                        raise RuntimeError(f'HidP_GetCaps failed: {status:#x}')
                    record.update(usage_page=f'{caps.UsagePage:04x}', usage=f'{caps.Usage:04x}',
                                  input_report_bytes=caps.InputReportByteLength,
                                  output_report_bytes=caps.OutputReportByteLength,
                                  feature_report_bytes=caps.FeatureReportByteLength)
                finally:
                    hid.HidD_FreePreparsedData(preparsed)
            finally:
                kernel.CloseHandle(handle)
    finally:
        setup.SetupDiDestroyDeviceInfoList(devices)
    return dict(mode='Metadata inspection only; zero desired access; no HID reports sent.', interfaces=found)


if __name__ == '__main__':
    report = inspect()
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
