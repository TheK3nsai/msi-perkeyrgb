#!/bin/bash
# Wrapper for msi-perkeyrgb with retry logic for systemd
COLOR="${1:-cba6f7}"
MAX_RETRIES=5
DELAY=3

for ((i=1; i<=MAX_RETRIES; i++)); do
    echo "Attempt $i/$MAX_RETRIES: setting keyboard RGB to #$COLOR"
    if /usr/bin/msi-perkeyrgb --model GS75 --id 1038:113a -s "$COLOR" 2>&1; then
        echo "Success on attempt $i"
        exit 0
    fi
    echo "Failed attempt $i, waiting ${DELAY}s..."
    sleep "$DELAY"
done

echo "All $MAX_RETRIES attempts failed"
exit 1
