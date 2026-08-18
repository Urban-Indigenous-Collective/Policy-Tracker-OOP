#!/bin/bash
set -euo pipefail
cd /opt/policy-tracker
grep -v '^NY_OPEN_LEGISLATION_KEY=' .env > .env.tmp 2>/dev/null || cp .env .env.tmp 2>/dev/null || touch .env.tmp
cat /tmp/ny_key_line.txt >> .env.tmp
mv .env.tmp .env
rm -f /tmp/ny_key_line.txt
grep -q '^NY_OPEN_LEGISLATION_KEY=.' .env && echo "NY key installed"
