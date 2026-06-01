#!/bin/bash
# Set the MSI SteelSeries KLC (USB 1038:113a) per-key RGB to a steady color.
#
# ONE consolidated path, triggered by:
#   - udev, when the *hidraw* node appears (device is ready — see 99-msi-rgb.rules)
#   - the system-sleep resume hook (reinit-msi-steelseries-keyboard.sh)
#
# It uses the stock `msi-perkeyrgb` tool, which sends set_colors() + refresh()
# and activates the lights on its own (no unbind/rebind needed).
#
# HARD RULE (see ~/Projects/gentoo-config/GOTCHAS.md, "Repeated failed HID
# writes crash the USB controller"): the controller wedges after repeated failed
# feature-report writes and only a full power-off + AC-unplug recovers it. So:
#   * the attempt ceiling is 3 and MUST NOT be raised;
#   * an atomic per-boot claim caps total writes at 3 no matter how many udev
#     triggers arrive (the keyboard exposes several hidraw interfaces);
#   * on the first sign the controller is unhealthy we ABORT — never hammer;
#   * on failure we leave the keyboard DARK (safe, recoverable), never bricked.
set -u

idVendor="1038"
idProduct="113a"
model="GS75"                                # GS76 Stealth uses the GS75 keymap
conf="/etc/msi-kbd-rgb.conf"
claim="/run/msi-kbd-rgb.claimed"            # tmpfs: auto-clears each boot
settle="${MSI_KBD_SETTLE:-3}"               # seconds for the controller to become write-ready
maxAttempts=3                               # GOTCHAS ceiling — DO NOT RAISE

# Desired color: 6 hex digits from the conf file, else default lavender.
color="cba6f7"
if [ -r "$conf" ]; then
    c="$(grep -oiE '[0-9a-f]{6}' "$conf" | head -n1)"
    [ -n "$c" ] && color="$c"
fi

# Atomic single-claim per boot. mkdir is atomic, so exactly one invocation wins
# even when the device's several hidraw interfaces fire the rule near-together.
# This is also the brick guard: total HID writes per boot <= $maxAttempts.
mkdir "$claim" 2>/dev/null || exit 0

# Locate the USB port (e.g. 3-12) for the keyboard.
port=""
for d in /sys/bus/usb/devices/*/; do
    [ -r "${d}idVendor" ] && [ -r "${d}idProduct" ] || continue
    if [ "$(cat "${d}idVendor")" = "$idVendor" ] && [ "$(cat "${d}idProduct")" = "$idProduct" ]; then
        port="$(basename "$d")"
        break
    fi
done
if [ -z "$port" ]; then
    echo "msi-kbd-rgb: $idVendor:$idProduct not present, nothing to do" >&2
    exit 0
fi

# Settle (NOT write-retries) is what wins the enumeration race: the device can
# be enumerated but not yet ready for feature reports right after `add`.
sleep "$settle"

healthy() {
    [ -d "/sys/bus/usb/devices/$port" ] &&
    [ "$(cat "/sys/bus/usb/devices/$port/idProduct" 2>/dev/null)" = "$idProduct" ]
}

ok=0
for attempt in $(seq 1 "$maxAttempts"); do
    if /usr/bin/msi-perkeyrgb --model "$model" --id "${idVendor}:${idProduct}" -s "$color"; then
        ok=1
        break
    fi
    # Bail the instant the controller looks unhealthy — never hammer a wedged one.
    if ! healthy; then
        echo "msi-kbd-rgb: controller unhealthy after attempt $attempt; aborting (brick guard)" >&2
        break
    fi
    sleep 1
done

if [ "$ok" = 0 ]; then
    echo "msi-kbd-rgb: HID write failed; leaving keyboard dark (safe, recoverable)" >&2
    exit 1
fi

echo "msi-kbd-rgb: set #$color via msi-perkeyrgb ($attempt attempt(s))"
