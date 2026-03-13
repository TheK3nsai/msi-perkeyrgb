#!/usr/bin/env python3
"""
Diagnostic: try reading feature reports and test report ID framing.

Tests:
1. GET_FEATURE_REPORT to verify two-way communication
2. Send with 0x00 report ID prefix (correct per HID spec for no-report-ID devices)
3. Try both hidraw interfaces
"""

import os, struct, fcntl, sys
from time import sleep

# IOCTL numbers for hidraw
def _IOC(direction, type_num, nr, size):
    return (direction << 30) | (size << 16) | (type_num << 8) | nr

_IOC_WRITE = 1
_IOC_READ = 2

def HIDIOCGFEATURE(size):
    return _IOC(_IOC_WRITE | _IOC_READ, 0x48, 0x07, size)

def HIDIOCSFEATURE(size):
    return _IOC(_IOC_WRITE | _IOC_READ, 0x48, 0x06, size)

# Output report is just a regular write() on hidraw
# But we need the right framing

def find_steelseries_hidraw():
    """Find hidraw devices for SteelSeries KLC."""
    devs = []
    for entry in os.listdir('/sys/class/hidraw'):
        uevent_path = f'/sys/class/hidraw/{entry}/device/uevent'
        try:
            with open(uevent_path) as f:
                content = f.read()
            if '1038' in content and '113A' in content.upper():
                devs.append(entry)
        except:
            pass
    return sorted(devs)

devs = find_steelseries_hidraw()
print(f"SteelSeries KLC hidraw devices: {devs}")

for dev_name in devs:
    dev_path = f'/dev/{dev_name}'
    print(f"\n{'='*60}")
    print(f"Testing {dev_path}")
    print(f"{'='*60}")

    try:
        fd = os.open(dev_path, os.O_RDWR)
    except PermissionError:
        print(f"  Permission denied")
        continue

    # --- Test 1: GET_FEATURE_REPORT ---
    print(f"\n  [Test 1] GET_FEATURE_REPORT (524 bytes, report ID 0x0E)")
    try:
        buf = bytearray(524)
        buf[0] = 0x0E  # request report "ID" 0x0E
        ret = fcntl.ioctl(fd, HIDIOCGFEATURE(524), buf)
        print(f"    Returned {len(buf)} bytes")
        print(f"    First 32 bytes: {' '.join(f'{b:02x}' for b in buf[:32])}")
        print(f"    Non-zero bytes: {sum(1 for b in buf if b != 0)}")
    except Exception as e:
        print(f"    Error: {e}")

    print(f"\n  [Test 2] GET_FEATURE_REPORT (524 bytes, report ID 0x00)")
    try:
        buf = bytearray(524)
        buf[0] = 0x00  # request report ID 0 (no report IDs)
        ret = fcntl.ioctl(fd, HIDIOCGFEATURE(524), buf)
        print(f"    Returned {len(buf)} bytes")
        print(f"    First 32 bytes: {' '.join(f'{b:02x}' for b in buf[:32])}")
        print(f"    Non-zero bytes: {sum(1 for b in buf if b != 0)}")
    except Exception as e:
        print(f"    Error: {e}")

    # --- Test 3: GET_FEATURE_REPORT (64 bytes) ---
    print(f"\n  [Test 3] GET_FEATURE_REPORT (64 bytes, report ID 0x00)")
    try:
        buf = bytearray(64)
        buf[0] = 0x00
        ret = fcntl.ioctl(fd, HIDIOCGFEATURE(64), buf)
        print(f"    Returned {len(buf)} bytes")
        print(f"    First 32 bytes: {' '.join(f'{b:02x}' for b in buf[:32])}")
    except Exception as e:
        print(f"    Error: {e}")

    # --- Test 4: Send minimal color packet with report ID 0x00 prefix ---
    # Only on the first hidraw (interface 0)
    if dev_name == devs[0]:
        print(f"\n  [Test 4] SEND feature report with 0x00 prefix (525 bytes)")
        print(f"    Building: [0x00] + [0x0E, 0x00, 0x2A, 0x00, ...keycodes..., footer]")

        # Build the inner 524-byte packet
        R, G, B = 0xFF, 0xFF, 0xFF
        keycodes = [4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,
                    24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,58,59,60,61,62,63]
        inner = [0x0E, 0x00, 0x2A, 0x00]  # header
        for kc in keycodes:
            inner += [R, G, B, 0,0,0,0,0,0, 0x01, 0x00, kc]
        while len(inner) < 508:
            inner += [0x00] * 12
        inner += [0x00] * 14 + [0x08, 0x39]  # footer
        assert len(inner) == 524

        # Prepend report ID 0x00
        buf = bytes([0x00]) + bytes(inner)  # 525 bytes total

        try:
            ret = fcntl.ioctl(fd, HIDIOCSFEATURE(len(buf)), buf)
            print(f"    ioctl returned, buf size after: {len(buf)}")
            print(f"    Success!")
        except Exception as e:
            print(f"    Error: {e}")

        sleep(0.05)

        # Send refresh with 0x00 prefix
        print(f"\n  [Test 5] SEND output report (write) with 0x00 prefix (65 bytes)")
        refresh = bytes([0x00, 0x09] + [0x00] * 62)  # 65 bytes: reportID(0) + data(64)
        try:
            ret = os.write(fd, refresh)
            print(f"    write() returned {ret}")
        except Exception as e:
            print(f"    Error: {e}")

        # Also try WITHOUT prefix (original way)
        sleep(0.1)
        print(f"\n  [Test 6] SEND feature report WITHOUT prefix (524 bytes, original)")
        try:
            ret = fcntl.ioctl(fd, HIDIOCSFEATURE(len(inner)), bytes(inner))
            print(f"    ioctl returned, success!")
        except Exception as e:
            print(f"    Error: {e}")

        sleep(0.05)
        print(f"\n  [Test 7] SEND output report (write) WITHOUT prefix (64 bytes)")
        refresh_orig = bytes([0x09] + [0x00] * 63)
        try:
            ret = os.write(fd, refresh_orig)
            print(f"    write() returned {ret}")
        except Exception as e:
            print(f"    Error: {e}")

    os.close(fd)

print("\n\nDone. Check keyboard for any lights.")
