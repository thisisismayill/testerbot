#!/usr/bin/env bash
# TesterBot install (macOS / Linux)
set -e
cd "$(dirname "$0")"
echo "→ Installing the Python packages…"
python3 -m pip install -r requirements.txt
echo "→ Downloading the Chromium browser (once only, ~150 MB)…"
python3 -m playwright install chromium
echo ""
chmod +x TesterBot.command 2>/dev/null
xattr -d com.apple.quarantine TesterBot.command 2>/dev/null
echo "✓ Ready."
echo ""
echo "  Easiest way:  double-click TesterBot.command"
echo "  From a shell: python3 tester_bot.py https://your-site.com"
