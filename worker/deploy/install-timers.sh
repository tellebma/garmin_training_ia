#!/usr/bin/env bash
#
# install-timers.sh — copy systemd units onto the host and enable them.
#
# Designed for the UNRAID / Linux host that runs the garmin-sync container.
# You don't need to clone the repo; just extract the files from the running
# container and execute this script:
#
#     docker cp garmin-sync:/app/deploy/. /tmp/garmin-deploy/
#     sudo bash /tmp/garmin-deploy/install-timers.sh
#
# The script is idempotent: re-running it overwrites the units in place and
# re-enables the timers. The legacy garmin-sync-cron.timer (daily 05:00 UTC)
# is disabled in favor of the new targeted schedule.

set -euo pipefail

if [ "$(id -u)" != "0" ]; then
  echo "This script must run as root (use sudo)." >&2
  exit 1
fi

# Locate the deploy/ directory we were called from.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

UNITS=(
  garmin-sync-sleep.service
  garmin-sync-sleep.timer
  garmin-sync-activities-midday.service
  garmin-sync-activities-midday.timer
  garmin-sync-activities-evening.service
  garmin-sync-activities-evening.timer
  garmin-sync-profile.service
  garmin-sync-profile.timer
)

TIMERS=(
  garmin-sync-sleep.timer
  garmin-sync-activities-midday.timer
  garmin-sync-activities-evening.timer
  garmin-sync-profile.timer
)

echo "==> Copying systemd units to /etc/systemd/system/"
for unit in "${UNITS[@]}"; do
  src="${HERE}/${unit}"
  if [ ! -f "${src}" ]; then
    echo "  missing: ${src}" >&2
    exit 1
  fi
  cp -f "${src}" "/etc/systemd/system/${unit}"
  echo "  installed: ${unit}"
done

echo "==> Reloading systemd"
systemctl daemon-reload

echo "==> Enabling and starting new timers"
for t in "${TIMERS[@]}"; do
  systemctl enable --now "${t}"
  echo "  enabled: ${t}"
done

# Disable the legacy daily cron if it exists, to avoid double sync at 05:00 UTC.
if systemctl list-unit-files | grep -q "^garmin-sync-cron.timer"; then
  echo "==> Disabling legacy garmin-sync-cron.timer"
  systemctl disable --now garmin-sync-cron.timer || true
fi

echo ""
echo "Done. Active timers:"
systemctl list-timers --no-pager | grep "garmin-sync" || true
echo ""
echo "Next scheduled runs:"
systemctl list-timers garmin-sync-sleep.timer garmin-sync-activities-midday.timer \
  garmin-sync-activities-evening.timer garmin-sync-profile.timer --no-pager 2>/dev/null | tail -6
