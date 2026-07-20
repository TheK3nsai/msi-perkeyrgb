# MSI GS76 keyboard backlight — consolidated, brick-safe redesign

**Status:** INSTALLED 2026-07-12; **revised to ONE-STRIKE 2026-07-13** — the
first reboot check failed (controller was already half-wedged; it hard-wedged
under the bounded 3-attempt retry). The script now makes exactly one programming
attempt per boot with a 5s settle and aborts dark on any `HIDSendError`. One
attempt contains several ordered feature reports plus the final refresh; it is
the transaction that is never retried. Full incident
analysis + policy rationale: gentoo-config `GOTCHAS.md` ("Repeated failed HID
writes"). **Canonical copies live in `~/Projects/gentoo-config`** — this dir
is staging/reference; sync from gentoo-config, not the other way.

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
  5s settle, instead of raw USB `add`. The settle, not retries, wins the race.
- **One-strike brick guard** (2026-07-13, supersedes the original 3-attempt
  retry) — exactly **one programming attempt** per boot: an **atomic per-boot claim**
  (`mkdir /run/msi-kbd-rgb.claimed`) dedupes the multiple hidraw-interface udev
  triggers, and any `HIDSendError` aborts immediately. Rationale: every hard
  wedge on record was preceded by fail→retry sequences, and `msi-perkeyrgb`
  exit 0 after a prior failure was observed with the lights still dark (EC
  ACKs without applying). On failure it leaves the keyboard **dark
  (recoverable)**, never bricked.
- **Color in one place** — `/etc/msi-kbd-rgb.conf` (default `cba6f7`).
- **Deterministic HID cleanup** (2026-07-19) — the client explicitly closes its
  libusb HID handle on success and failure, so interface 0 is reattached instead
  of remaining detached after the process exits.

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

1. One manual programming attempt (no retry):
   ```bash
   sudo rm -rf /run/msi-kbd-rgb.claimed
   sudo systemctl start msi-kbd-rgb.service
   journalctl -u msi-kbd-rgb.service -n 20 --no-pager
   ```
   Expect: `set #cba6f7 via msi-perkeyrgb (single programming attempt)` and the keyboard
   lights. If it throws `HIDSendError` instead, STOP — do not re-run; the
   controller is unhealthy (EC reset via the Battery Reset Hole, see
   gentoo-config GOTCHAS).
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
