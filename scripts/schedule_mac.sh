#!/bin/bash
# Run the daily screener + email automatically on weekdays (macOS launchd).
#   bash scripts/schedule_mac.sh install [HH:MM]    default 16:10 (after the 15:30 close and NSE's bhavcopy)
#   bash scripts/schedule_mac.sh uninstall
#   bash scripts/schedule_mac.sh status
# The Mac must be awake at that time. To wake it automatically (asks for your password):
#   sudo pmset repeat wakeorpoweron MTWRF 16:05:00
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.ictswingengine.daily"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PY="$REPO/.venv/bin/python"
case "${1:-status}" in
  install)
    T="${2:-16:10}"; H="${T%%:*}"; M="${T##*:}"
    [ -x "$PY" ] || { echo "No $PY: create the venv first (python3 -m venv .venv && .venv/bin/pip install -r requirements.txt)"; exit 1; }
    mkdir -p "$HOME/Library/LaunchAgents" "$REPO/reports/daily"
    {
      echo '<?xml version="1.0" encoding="UTF-8"?>'
      echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
      echo '<plist version="1.0"><dict>'
      echo "  <key>Label</key><string>$LABEL</string>"
      echo "  <key>WorkingDirectory</key><string>$REPO</string>"
      echo '  <key>ProgramArguments</key><array>'
      echo "    <string>$PY</string><string>-m</string><string>scripts.daily</string><string>--fetch</string><string>--email</string>"
      echo '  </array>'
      echo '  <key>StartCalendarInterval</key><array>'
      for d in 1 2 3 4 5; do
        echo "    <dict><key>Weekday</key><integer>$d</integer><key>Hour</key><integer>$((10#$H))</integer><key>Minute</key><integer>$((10#$M))</integer></dict>"
      done
      echo '  </array>'
      echo "  <key>StandardOutPath</key><string>$REPO/reports/daily/schedule.log</string>"
      echo "  <key>StandardErrorPath</key><string>$REPO/reports/daily/schedule.log</string>"
      echo '</dict></plist>'
    } > "$PLIST"
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST"
    echo "Installed: weekdays at $T (Mac time). Log: reports/daily/schedule.log"
    echo "Run it now to test:  launchctl start $LABEL" ;;
  uninstall)
    launchctl unload "$PLIST" 2>/dev/null || true; rm -f "$PLIST"; echo "Removed." ;;
  status)
    if [ -f "$PLIST" ]; then echo "Installed: $PLIST"; launchctl list | grep "$LABEL" || echo "(not loaded)"; else echo "Not installed."; fi ;;
  *) echo "usage: $0 install [HH:MM] | uninstall | status"; exit 1 ;;
esac
