#!/usr/bin/env bash
# Purpose of this script is to run a quick dry-run to verify everything is set to run the actual test
set -e
set -o pipefail

log_file="dr-$(date -u +%Y%m%d-%H%M%S).log"

time ./sno-deploy-load/sno-deploy-load.py --dry-run --start-delay 1 --end-delay 1 -w -i 10 -t dry-run interval -b 100 -i 1 ztp 2>&1 | tee ${log_file}
