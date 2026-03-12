#!/usr/bin/env python3
"""Direct MSI per-key RGB setter using HIDAPI libusb backend.

Uses libhidapi-libusb (not hidraw) to send HID feature reports, which
handles multi-packet USB control transfers more reliably on full-speed
devices like the SteelSeries KLC.
"""

import argparse
import ctypes as ct
import re
import sys
import time
from os import popen
from os.path import exists

# Import protocol/keymap data from msi_perkeyrgb
sys.path.insert(0, '/usr/lib/python3.13/site-packages')
from msi_perkeyrgb.config import load_steady
from msi_perkeyrgb.msi_keyboard import MSI_Keyboard
from msi_perkeyrgb.msiprotocol import make_key_colors_packet, make_refresh_packet
from msi_perkeyrgb.protocol_data.keycodes import REGION_KEYCODES

VENDOR_ID = 0x1038
PRODUCT_ID = 0x113a
INTER_COMMAND_DELAY = 0.35   # 350ms between HID commands
RETRY_DELAY = 1.0            # 1s wait before retrying a failed report
MAX_RETRIES = 5              # per-packet retry count


def load_hidapi():
    """Load the HIDAPI libusb backend."""
    s = popen("ldconfig -p").read()
    path_matches = re.findall(r"/.*libhidapi-libusb\.so(?:\.\d+)*", s)
    if not path_matches:
        print('Cannot locate libhidapi-libusb.so', file=sys.stderr)
        sys.exit(1)

    lib_path = path_matches[0]
    if not exists(lib_path):
        print(f'HIDAPI library not found at {lib_path}', file=sys.stderr)
        sys.exit(1)

    hidapi = ct.cdll.LoadLibrary(lib_path)

    # Set up function signatures
    hidapi.hid_init.argtypes = []
    hidapi.hid_init.restype = ct.c_int
    hidapi.hid_open.argtypes = [ct.c_ushort, ct.c_ushort, ct.c_wchar_p]
    hidapi.hid_open.restype = ct.c_void_p
    hidapi.hid_send_feature_report.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_size_t]
    hidapi.hid_send_feature_report.restype = ct.c_int
    hidapi.hid_write.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_size_t]
    hidapi.hid_write.restype = ct.c_int
    hidapi.hid_close.argtypes = [ct.c_void_p]
    hidapi.hid_close.restype = None
    hidapi.hid_error.argtypes = [ct.c_void_p]
    hidapi.hid_error.restype = ct.c_wchar_p
    hidapi.hid_exit.argtypes = []
    hidapi.hid_exit.restype = ct.c_int

    return hidapi


def set_steady_color(color_hex, model='GS75'):
    """Set all keys to a steady color using HIDAPI libusb backend."""
    msi_keymap = MSI_Keyboard.get_model_keymap(model)
    if msi_keymap is None:
        print(f'Unknown model: {model}', file=sys.stderr)
        return False

    colors_map, warnings = load_steady(color_hex, msi_keymap)
    for w in warnings:
        print(f'Warning: {w}', file=sys.stderr)

    # Translate Linux keycodes to MSI keycodes
    msi_keycodes = [msi_keymap[k] for k in colors_map.keys()]
    msi_colors_map = dict(zip(msi_keycodes, colors_map.values()))

    # Sort by region
    regions = {}
    for keycode, color in msi_colors_map.items():
        for region, region_codes in REGION_KEYCODES.items():
            if keycode in region_codes:
                if region not in regions:
                    regions[region] = {}
                regions[region][keycode] = color

    # Load HIDAPI libusb backend
    hidapi = load_hidapi()
    hidapi.hid_init()

    # Open the device
    device = hidapi.hid_open(VENDOR_ID, PRODUCT_ID, ct.c_wchar_p(0))
    if device is None:
        print('Cannot open SteelSeries KLC keyboard', file=sys.stderr)
        hidapi.hid_exit()
        return False

    print(f'Opened SteelSeries KLC via HIDAPI libusb')

    success = True
    try:
        # Send color packets per region
        for region, region_colors in regions.items():
            packet = make_key_colors_packet(region, region_colors)
            data = bytes(packet)

            sent = False
            for attempt in range(MAX_RETRIES):
                ret = hidapi.hid_send_feature_report(device, data, len(data))
                if ret == len(data):
                    print(f'  Set {region} ({len(region_colors)} keys)')
                    sent = True
                    break
                else:
                    err = hidapi.hid_error(device)
                    err_msg = err if err else 'unknown error'
                    print(f'  {region} attempt {attempt + 1}/{MAX_RETRIES} failed '
                          f'(ret={ret}): {err_msg}')
                    time.sleep(RETRY_DELAY)

            if not sent:
                print(f'  FAILED: {region} after {MAX_RETRIES} attempts', file=sys.stderr)
                success = False
                break

            time.sleep(INTER_COMMAND_DELAY)

        if success:
            # Send refresh as output report
            refresh = bytes(make_refresh_packet())
            ret = hidapi.hid_write(device, refresh, len(refresh))
            if ret == len(refresh):
                print('  Refresh sent')
            else:
                err = hidapi.hid_error(device)
                print(f'  Refresh failed (ret={ret}): {err}', file=sys.stderr)
                success = False

    finally:
        hidapi.hid_close(device)
        hidapi.hid_exit()

    return success


def main():
    parser = argparse.ArgumentParser(description='Set MSI keyboard RGB via HIDAPI libusb')
    parser.add_argument('color', help='Hex color (e.g., cba6f7)')
    parser.add_argument('--model', default='GS75', help='MSI laptop model (default: GS75)')
    args = parser.parse_args()

    color = args.color.lstrip('#')
    if len(color) != 6:
        print(f'Invalid color: {args.color}', file=sys.stderr)
        sys.exit(1)

    print(f'Setting keyboard RGB to #{color}')
    if set_steady_color(color, args.model):
        print('Done')
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
