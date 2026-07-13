#!/bin/sh
# Re-apply the MSI keyboard RGB after resume from sleep.
# Clears the per-boot claim so the unified script runs once, then runs it.
# The brick guard (atomic claim + one-strike single write) lives in the
# script, so this hook stays a dumb one-shot — never add a retry loop here.
case "$1" in
    post)
        rm -rf /run/msi-kbd-rgb.claimed
        /usr/local/sbin/msi-kbd-rgb.sh
        ;;
esac
