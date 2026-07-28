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
# writes crash the USB controller"): the controller wedges after failed
# feature-report writes and only the Battery Reset Hole EC reset recovers it.
# ONE-STRIKE POLICY (2026-07-13): a single HIDSendError means the controller is
# unhealthy — every hard wedge on record was preceded by fail→retry sequences,
# and msi-perkeyrgb's exit code after a prior failure is untrustworthy (exit 0
# with the lights still dark). So:
#   * exactly ONE programming attempt per boot — NO retry loop, DO NOT add one back;
#     that one msi-perkeyrgb transaction contains several ordered HID transfers;
#   * an atomic per-boot claim keeps it at one attempt no matter how many udev
#     triggers arrive (the keyboard exposes several hidraw interfaces);
#   * the settle sleep, not retries, is what wins the enumeration race;
#   * on failure we leave the keyboard DARK (safe, recoverable), never bricked.
#     Exit 75 marks this guarded hardware outcome; the systemd unit accepts only
#     that code so optional lighting cannot make the whole host degraded.
#     Manual recovery after a dark boot with a healthy controller:
#       sudo rmdir /run/msi-kbd-rgb.claimed && sudo systemctl start msi-kbd-rgb
set -u

idVendor="1038"
idProduct="113a"
model="GS75"                                # GS76 Stealth uses the GS75 keymap
conf="/etc/msi-kbd-rgb.conf"
claim="/run/msi-kbd-rgb.claimed"            # tmpfs: auto-clears each boot
settle="${MSI_KBD_SETTLE:-5}"               # seconds for the controller to become write-ready

# Desired color: 6 hex digits from the conf file, else default lavender.
color="cba6f7"
if [ -r "$conf" ]; then
    c="$(grep -oiE '[0-9a-f]{6}' "$conf" | head -n1)"
    [ -n "$c" ] && color="$c"
fi

# Atomic single-claim per boot. mkdir is atomic, so exactly one invocation wins
# even when the device's several hidraw interfaces fire the rule near-together.
# This is also the brick guard: exactly one programming transaction per boot.
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

# One strike. A HIDSendError here means the controller is unhealthy — retrying
# risks the hard wedge (Battery Reset Hole recovery), and a post-failure exit 0
# from msi-perkeyrgb has been observed with the lights still dark, so a retry
# can't even be trusted when it claims success.
if ! /usr/bin/msi-perkeyrgb --model "$model" --id "${idVendor}:${idProduct}" -s "$color"; then
    echo "msi-kbd-rgb: HID write failed; leaving keyboard dark — controller suspect (one-strike brick guard)" >&2
    echo "msi-kbd-rgb: if lights stay dark after an EC reset + reboot, see GOTCHAS 'Repeated failed HID writes'" >&2
    exit 75
fi

echo "msi-kbd-rgb: set #$color via msi-perkeyrgb (single programming attempt)"
