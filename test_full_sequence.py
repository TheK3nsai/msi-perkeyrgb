#!/usr/bin/env python3
"""
Full sequence test with readback verification and longer delays.
Uses raw hidraw ioctl for maximum control.
"""

import os, fcntl, sys
from time import sleep

def _IOC(d, t, nr, sz):
    return (d << 30) | (sz << 16) | (t << 8) | nr

def HIDIOCGFEATURE(sz):
    return _IOC(3, 0x48, 0x07, sz)

def HIDIOCSFEATURE(sz):
    return _IOC(3, 0x48, 0x06, sz)

NB_KEYS = 42
R, G, B = 0xFF, 0xFF, 0xFF  # white

REGIONS = {
    "alphanum":  (0x2A, [4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,58,59,60,61,62,63]),
    "enter":     (0x0B, [40,49,50,100,135,136,137,138,139,144,145]),
    "modifiers": (0x18, [41,42,43,44,45,46,47,48,51,52,53,54,55,56,57,101,224,225,226,227,228,229,230,240]),
    "numpad":    (0x24, [64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99]),
}

def build_color_packet(region_id, keycodes):
    packet = [0x0E, 0x00, region_id, 0x00]
    k = 0
    for kc in keycodes:
        packet += [R, G, B, 0,0,0,0,0,0, 0x01, 0x00, kc]
        k += 1
    while k < NB_KEYS:
        packet += [0x00] * 12
        k += 1
    packet += [0x00] * 14 + [0x08, 0x39]
    assert len(packet) == 524
    return bytes(packet)

# Find the right hidraw
for entry in sorted(os.listdir('/sys/class/hidraw')):
    uevent = f'/sys/class/hidraw/{entry}/device/uevent'
    try:
        with open(uevent) as f:
            if '1038' in f.read() and entry.endswith('1'):  # first interface
                break
    except:
        continue
else:
    # Fallback
    entry = 'hidraw1'

dev_path = f'/dev/{entry}'
print(f"Using {dev_path}")

fd = os.open(dev_path, os.O_RDWR)

# --- Phase 1: Send all 4 regions with 100ms delays ---
print("\n--- Phase 1: Sending color packets (100ms delay) ---")
for name, (region_id, keycodes) in REGIONS.items():
    packet = build_color_packet(region_id, keycodes)
    try:
        fcntl.ioctl(fd, HIDIOCSFEATURE(len(packet)), packet)
        print(f"  {name:12s} (0x{region_id:02X}): OK")
    except Exception as e:
        print(f"  {name:12s} (0x{region_id:02X}): FAILED - {e}")
        # Try once more after longer delay
        sleep(0.5)
        try:
            fcntl.ioctl(fd, HIDIOCSFEATURE(len(packet)), packet)
            print(f"  {name:12s} (0x{region_id:02X}): OK (retry)")
        except Exception as e2:
            print(f"  {name:12s} (0x{region_id:02X}): FAILED again - {e2}")
    sleep(0.1)  # 100ms between regions

# --- Phase 2: Send refresh ---
print("\n--- Phase 2: Sending refresh packet ---")
refresh = bytes([0x09] + [0x00] * 63)
try:
    ret = os.write(fd, refresh)
    print(f"  refresh: OK ({ret} bytes)")
except Exception as e:
    print(f"  refresh: FAILED - {e}")

sleep(0.2)

# --- Phase 3: Read back to verify data was stored ---
print("\n--- Phase 3: Reading back feature report ---")
buf = bytearray(524)
buf[0] = 0x0E
try:
    fcntl.ioctl(fd, HIDIOCGFEATURE(524), buf)
    nz = sum(1 for b in buf if b != 0)
    print(f"  GET_FEATURE (ID=0x0E): {nz} non-zero bytes")
    if nz > 0:
        print(f"  First 48 bytes: {' '.join(f'{b:02x}' for b in buf[:48])}")
    else:
        print(f"  All zeros — device did not store our data")
except Exception as e:
    print(f"  GET_FEATURE: {e}")

# --- Phase 4: Try reading with different "report IDs" to discover what the device responds to ---
print("\n--- Phase 4: Probing different report IDs ---")
for rid in [0x00, 0x01, 0x02, 0x03, 0x09, 0x0B, 0x0E, 0x18, 0x24, 0x2A, 0xFF]:
    buf = bytearray(524)
    buf[0] = rid
    try:
        fcntl.ioctl(fd, HIDIOCGFEATURE(524), buf)
        nz = sum(1 for b in buf if b != 0)
        print(f"  Report ID 0x{rid:02X}: {nz} non-zero bytes", end="")
        if nz > 0:
            print(f"  data: {' '.join(f'{b:02x}' for b in buf[:16])}")
        else:
            print()
    except Exception as e:
        print(f"  Report ID 0x{rid:02X}: {e}")

os.close(fd)
print("\nDone. Check keyboard.")
