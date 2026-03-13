#!/usr/bin/env python3
"""
Minimal test: set all keyboard keys to white using libhidapi-hidraw.

First-principles approach:
- Uses hidraw backend (NOT libusb) — sends full buffer to kernel
- Sends 4 region packets (524 bytes each) + 1 refresh (64 bytes)
- Single attempt, no retries
- Prints return values for diagnosis
"""

import ctypes
import ctypes.util
from time import sleep

# --- Load hidraw backend specifically ---
lib = ctypes.cdll.LoadLibrary("libhidapi-hidraw.so")

# Set up function signatures (64-bit safe)
lib.hid_init.argtypes = []
lib.hid_init.restype = ctypes.c_int

lib.hid_open.argtypes = [ctypes.c_ushort, ctypes.c_ushort, ctypes.c_wchar_p]
lib.hid_open.restype = ctypes.c_void_p

lib.hid_close.argtypes = [ctypes.c_void_p]
lib.hid_close.restype = None

lib.hid_write.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
lib.hid_write.restype = ctypes.c_int

lib.hid_send_feature_report.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
lib.hid_send_feature_report.restype = ctypes.c_int

lib.hid_error.argtypes = [ctypes.c_void_p]
lib.hid_error.restype = ctypes.c_wchar_p

# --- Constants ---
VID = 0x1038
PID = 0x113A
NB_KEYS = 42
KEY_FRAGMENT_SIZE = 12

REGIONS = {
    "alphanum": (0x2A, [4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,58,59,60,61,62,63]),
    "enter":    (0x0B, [40,49,50,100,135,136,137,138,139,144,145]),
    "modifiers":(0x18, [41,42,43,44,45,46,47,48,51,52,53,54,55,56,57,101,224,225,226,227,228,229,230,240]),
    "numpad":   (0x24, [64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99]),
}

# Color to set (white)
R, G, B = 0xFF, 0xFF, 0xFF

def build_color_packet(region_id, keycodes):
    """Build a 524-byte feature report for one region."""
    packet = [0x0E, 0x00, region_id, 0x00]  # header

    keys_written = 0
    for kc in keycodes:
        packet += [R, G, B, 0,0,0,0,0,0, 0x01, 0x00, kc]
        keys_written += 1

    # Pad remaining slots
    while keys_written < NB_KEYS:
        packet += [0x00] * KEY_FRAGMENT_SIZE
        keys_written += 1

    # Footer
    packet += [0x00] * 14 + [0x08, 0x39]

    assert len(packet) == 524, f"Packet size {len(packet)}, expected 524"
    return bytes(packet)

def build_refresh_packet():
    """Build the 64-byte refresh/commit packet."""
    return bytes([0x09] + [0x00] * 63)

# --- Main ---
print(f"Loading libhidapi-hidraw.so")
ret = lib.hid_init()
print(f"hid_init() = {ret}")

print(f"\nOpening device {VID:04x}:{PID:04x}...")
dev = lib.hid_open(VID, PID, None)
if not dev:
    print("ERROR: hid_open returned NULL. Check udev rules / permissions.")
    exit(1)
print(f"hid_open() = {dev:#x}")

try:
    # Send color packets for each region
    for name, (region_id, keycodes) in REGIONS.items():
        packet = build_color_packet(region_id, keycodes)
        ret = lib.hid_send_feature_report(dev, packet, len(packet))
        err = lib.hid_error(dev) if ret < 0 else None
        status = f"OK ({ret} bytes)" if ret >= 0 else f"FAILED ({ret}): {err}"
        print(f"  {name:10s} (0x{region_id:02X}): {status}")
        sleep(0.01)

    # Send refresh
    refresh = build_refresh_packet()
    ret = lib.hid_write(dev, refresh, len(refresh))
    err = lib.hid_error(dev) if ret < 0 else None
    status = f"OK ({ret} bytes)" if ret >= 0 else f"FAILED ({ret}): {err}"
    print(f"  {'refresh':10s} (0x09): {status}")

    print("\nDone. Check if keyboard lights turned on.")
finally:
    lib.hid_close(dev)
    print("Device closed.")
