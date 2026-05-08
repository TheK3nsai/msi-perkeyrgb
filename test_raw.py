#!/usr/bin/env python3
"""Absolute minimum test: send raw HID bytes to the keyboard.
No libraries, no dependencies - just open hidraw and ioctl."""

import fcntl
import os
import struct
import sys
import time

# HIDIOCSFEATURE = 0xC0094806 on x86_64 Linux
# But the size is encoded in the ioctl number. For a 520-byte buffer:
# _IOC(_IOC_WRITE|_IOC_READ, 'H', 0x06, size)
# We'll compute it properly.

def HIDIOCSFEATURE(size):
    """Compute HIDIOCSFEATURE ioctl number for given buffer size."""
    # _IOC(dir, type, nr, size)
    # dir = _IOC_WRITE|_IOC_READ = 3
    # type = 'H' = 0x48
    # nr = 0x06
    _IOC_WRITE = 1
    _IOC_READ = 2
    _IOC_NRBITS = 8
    _IOC_TYPEBITS = 8
    _IOC_SIZEBITS = 14
    _IOC_NRSHIFT = 0
    _IOC_TYPESHIFT = _IOC_NRSHIFT + _IOC_NRBITS      # 8
    _IOC_SIZESHIFT = _IOC_TYPESHIFT + _IOC_TYPEBITS   # 16
    _IOC_DIRSHIFT = _IOC_SIZESHIFT + _IOC_SIZEBITS    # 30
    direction = (_IOC_WRITE | _IOC_READ) << _IOC_DIRSHIFT
    return direction | (size << _IOC_SIZESHIFT) | (0x48 << _IOC_TYPESHIFT) | (0x06 << _IOC_NRSHIFT)


# Protocol constants from msiprotocol.py
NB_KEYS = 42
REGIONS = {
    "alphanum": 0x2a,
    "enter":    0x0b,
    "modifiers": 0x18,
    "numpad":   0x24,
}

# Key codes per region (from keycodes.py)
REGION_KEYS = {
    "alphanum":  [4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,58,59,60,61,62,63],
    "enter":     [40,49,50,100,135,136,137,138,139,144,145,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    "modifiers": [41,42,43,44,45,46,47,48,51,52,53,54,55,56,57,101,224,225,226,227,228,229,230,240,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    "numpad":    [64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,0,0,0,0,0,0],
}


def make_color_packet(region_name, r, g, b):
    """Build a feature report packet for a region with all keys set to one color."""
    packet = bytearray()
    region_id = REGIONS[region_name]
    keys = REGION_KEYS[region_name]

    # Header: 4 bytes
    packet += bytes([0x0e, 0x00, region_id, 0x00])

    # 42 key slots, 12 bytes each
    for i in range(NB_KEYS):
        keycode = keys[i]
        # [R, G, B, 0, 0, 0, 0, 0, 0, 1, 0, keycode]
        packet += bytes([r, g, b, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, keycode])

    # Footer: 16 bytes
    packet += bytes([0x00]*14 + [0x08, 0x39])

    return bytes(packet)


def make_refresh_packet():
    """Build the refresh output report."""
    return bytes([0x09] + [0x00] * 63)


def try_device(hidraw_path, r, g, b):
    """Try sending color data to a hidraw device."""
    print(f"\n{'='*60}")
    print(f"Trying {hidraw_path} with color #{r:02x}{g:02x}{b:02x}")
    print(f"{'='*60}")

    try:
        fd = os.open(hidraw_path, os.O_RDWR)
    except OSError as e:
        print(f"  FAIL: Cannot open {hidraw_path}: {e}")
        return False

    try:
        for region_name in ["alphanum", "enter", "modifiers", "numpad"]:
            packet = make_color_packet(region_name, r, g, b)
            print(f"  Region '{region_name}': {len(packet)} bytes, header={packet[:4].hex()}")

            ioctl_num = HIDIOCSFEATURE(len(packet))
            try:
                ret = fcntl.ioctl(fd, ioctl_num, packet)
                print(f"    -> ioctl returned: {ret} (type: {type(ret).__name__})")
                if isinstance(ret, bytes):
                    print(f"    -> response first 8 bytes: {ret[:8].hex()}")
            except OSError as e:
                print(f"    -> ioctl FAILED: {e}")
                # Don't give up - try next region
                continue

            time.sleep(0.1)

        # Send refresh
        refresh = make_refresh_packet()
        print(f"  Refresh packet: {len(refresh)} bytes")
        try:
            written = os.write(fd, refresh)
            print(f"    -> write returned: {written}")
        except OSError as e:
            print(f"    -> write FAILED: {e}")

    finally:
        os.close(fd)

    return True


def main():
    # Bright white - if anything works, we'll see it
    r, g, b = 0xFF, 0xFF, 0xFF

    if len(sys.argv) > 1:
        # Allow specifying color
        color = sys.argv[1].lstrip('#')
        r = int(color[0:2], 16)
        g = int(color[2:4], 16)
        b = int(color[4:6], 16)

    # Try both SteelSeries hidraw devices
    for dev in ["/dev/hidraw1", "/dev/hidraw2"]:
        try_device(dev, r, g, b)
        print()


if __name__ == "__main__":
    main()
