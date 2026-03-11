#!/usr/bin/env python3
"""Direct hidraw-based MSI per-key RGB setter.

Bypasses the HIDAPI ctypes wrapper and sends HID feature reports
directly via ioctl on /dev/hidraw*, which is more reliable.
"""

import argparse
import fcntl
import glob
import os
import struct
import sys
import time

# Import protocol/keymap data from msi_perkeyrgb
sys.path.insert(0, '/usr/lib/python3.13/site-packages')
from msi_perkeyrgb.config import load_steady
from msi_perkeyrgb.msi_keyboard import MSI_Keyboard
from msi_perkeyrgb.msiprotocol import make_key_colors_packet, make_refresh_packet
from msi_perkeyrgb.protocol_data.keycodes import REGION_KEYCODES

VENDOR_ID = 0x1038
PRODUCT_ID = 0x113a
INTER_COMMAND_DELAY = 0.05  # 50ms between HID commands (vs 10ms in original)


def _ioc(direction, type_char, nr, size):
    """Compute ioctl number (Linux _IOC macro)."""
    return (direction << 30) | (size << 16) | (ord(type_char) << 8) | nr


def hidiocsfeature(length):
    """HIDIOCSFEATURE(len) - send a feature report to a HID device."""
    return _ioc(3, 'H', 0x06, length)  # 3 = _IOC_WRITE|_IOC_READ


def find_hidraw_device():
    """Find the hidraw device for the SteelSeries KLC keyboard (interface 0)."""
    for path in sorted(glob.glob('/sys/class/hidraw/hidraw*/device/uevent')):
        try:
            with open(path) as f:
                uevent = f.read()
        except OSError:
            continue

        # Match vendor:product
        if f'{VENDOR_ID:04X}:{PRODUCT_ID:04X}' not in uevent.upper():
            continue

        # We want interface 0 (the HID control interface, not the keyboard input)
        # Check the parent device path for interface number
        device_path = os.path.dirname(path)
        hidraw_name = path.split('/')[4]  # e.g., hidraw1

        # Read the interface number from the HID device path
        # The path contains something like ...0003:1038:113A.0002 for interface 0
        # and ...0003:1038:113A.0003 for interface 1
        # Interface 0 has lower instance number
        dev_path = f'/dev/{hidraw_name}'
        print(f'Found SteelSeries KLC at {dev_path}')
        return dev_path

    return None


def send_feature_report(fd, data):
    """Send a HID feature report via ioctl."""
    buf = bytearray(data)  # mutable buffer required for _IOWR ioctl
    ioctl_num = hidiocsfeature(len(buf))
    try:
        ret = fcntl.ioctl(fd, ioctl_num, buf)
    except OSError as e:
        raise RuntimeError(f'Failed to send feature report ({len(buf)} bytes): {e}')
    if ret < 0:
        raise RuntimeError(f'Feature report ioctl returned {ret}')


def send_output_report(fd, data):
    """Send a HID output report via write()."""
    buf = bytes(data)
    written = os.write(fd, buf)
    if written != len(buf):
        raise RuntimeError(f'Output report: wrote {written}/{len(buf)} bytes')


def set_steady_color(color_hex, model='GS75'):
    """Set all keys to a steady color."""
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

    # Find the hidraw device
    dev_path = find_hidraw_device()
    if dev_path is None:
        print('SteelSeries KLC keyboard not found', file=sys.stderr)
        return False

    # Open the device
    try:
        fd = os.open(dev_path, os.O_RDWR)
    except OSError as e:
        print(f'Cannot open {dev_path}: {e}', file=sys.stderr)
        return False

    try:
        # Send color packets per region
        for region, region_colors in regions.items():
            packet = make_key_colors_packet(region, region_colors)
            send_feature_report(fd, packet)
            print(f'  Set {region} ({len(region_colors)} keys)')
            time.sleep(INTER_COMMAND_DELAY)

        # Send refresh
        refresh = make_refresh_packet()
        send_output_report(fd, refresh)
        print('  Refresh sent')

    except RuntimeError as e:
        print(f'Error: {e}', file=sys.stderr)
        return False
    finally:
        os.close(fd)

    return True


def main():
    parser = argparse.ArgumentParser(description='Set MSI keyboard RGB via direct hidraw access')
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
