# MSI GS76 keyboard backlight — consolidated, brick-safe redesign

**Status:** DRAFT — staged, not installed. Do not install or test until the RGB
controller has been recovered with a full power-off + AC-unplug (see GOTCHAS.md
"Repeated failed HID writes crash the USB controller").

## Why

The old setup ran **two** overlapping mechanisms that both poked the keyboard:

| | tool | retries | sets |
|---|---|---|---|
| `msi-steelseries-init.service` → `msi-steelseries-init.sh` | `msi-perkeyrgb` | 3 (bounded, safe) | white, then unbind/rebind |
| `msi-perkeyrgb.service` → `set-rgb.sh` → `set-rgb-direct.py` | custom re-impl | **5 per region × 5 wrapper** | lavender `cba6f7` |

Both use the same `libhidapi-libusb` backend (the GOTCHAS "must use hidraw" note
is stale for msi-perkeyrgb 2.1 — it loads libusb). The danger is **not** the
backend; it's the **retry multiplication** in the custom path: `set-rgb-direct.py`
retries every key-region up to 5×, wrapped in `set-rgb.sh`'s 5 more — dozens of
failed feature-report writes when the device is briefly unready, which is exactly
what wedges the controller and forces an AC-unplug.

Two root problems:
1. **Brick cannon** — the custom-script retry multiplication.
2. **Boot race** — the udev trigger fired on raw USB `add` (too early); the
   controller wasn't write-ready, the bounded retry sometimes lost, keyboard
   booted dark ("off again").

## What this redesign does

- **One** path. `msi-perkeyrgb -s <color>` already does `set_colors()` + `refresh()`
  (main.py:133-134), so it activates the lights itself — no custom libusb script,
  no unbind/rebind.
- **Race fix** — trigger on **hidraw `add`** (node present = device ready) + a
  3s settle, instead of raw USB `add`.
- **Brick-proof retry** — attempt ceiling stays at the GOTCHAS-sanctioned **3**,
  plus: an **atomic per-boot claim** (`mkdir /run/msi-kbd-rgb.claimed`) caps
  *total* writes per boot at 3 regardless of how many hidraw interfaces fire,
  and the loop **aborts** the instant the controller looks unhealthy. On failure
  it leaves the keyboard **dark (recoverable)**, never bricked.
- **Color in one place** — `/etc/msi-kbd-rgb.conf` (default `cba6f7`).

## Files

| staged | installs to |
|---|---|
| `msi-kbd-rgb.sh` | `/usr/local/sbin/msi-kbd-rgb.sh` (0755) |
| `msi-kbd-rgb.service` | `/etc/systemd/system/msi-kbd-rgb.service` |
| `99-msi-rgb.rules` | `/etc/udev/rules.d/99-msi-rgb.rules` (replaces existing) |
| `reinit-msi-steelseries-keyboard.sh` | `/usr/lib/systemd/system-sleep/` (0755) |
| `msi-kbd-rgb.conf` | `/etc/msi-kbd-rgb.conf` |

## Install (ONLY after controller recovery)

```bash
cd ~/Projects/msi-perkeyrgb/redesign
sudo install -m0755 msi-kbd-rgb.sh /usr/local/sbin/msi-kbd-rgb.sh
sudo install -m0644 msi-kbd-rgb.conf /etc/msi-kbd-rgb.conf
sudo install -m0644 msi-kbd-rgb.service /etc/systemd/system/msi-kbd-rgb.service
sudo install -m0644 99-msi-rgb.rules /etc/udev/rules.d/99-msi-rgb.rules
sudo install -m0755 reinit-msi-steelseries-keyboard.sh \
     /usr/lib/systemd/system-sleep/reinit-msi-steelseries-keyboard.sh

# Retire the old two-mechanism setup
sudo systemctl disable --now msi-perkeyrgb.service msi-steelseries-init.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/msi-perkeyrgb.service \
           /etc/systemd/system/msi-steelseries-init.service \
           /usr/local/sbin/msi-steelseries-init.sh

sudo systemctl daemon-reload
sudo udevadm control --reload
```

## Validate

1. One manual run (single write, safe):
   ```bash
   sudo rm -rf /run/msi-kbd-rgb.claimed
   sudo systemctl start msi-kbd-rgb.service
   journalctl -u msi-kbd-rgb.service -n 20 --no-pager
   ```
   Expect: `set #cba6f7 via msi-perkeyrgb (1 attempt(s))` and the keyboard lights.
2. Suspend/resume — confirm it re-applies.
3. Real test: reboot. Keyboard should come up lit without intervention.

If lights get *set* but don't *activate* on cold boot (unlikely — refresh works
on the warm path today), re-introduce a single guarded unbind/rebind after the
successful write. Documented as the fallback; not expected to be needed.

## Rollback

Old files are untouched in their original locations until the `rm`/`disable`
step above. To revert, restore `msi-steelseries-init.service`,
`msi-perkeyrgb.service`, `msi-steelseries-init.sh`, and the old
`99-msi-rgb.rules`, then `daemon-reload` + `udevadm control --reload`.
The retired `set-rgb.sh` / `set-rgb-direct.py` remain in `~/Projects/msi-perkeyrgb/`.
