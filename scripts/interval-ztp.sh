#!/usr/bin/env bash
set -e
set -o pipefail

log_file="dr-$(date -u +%Y%m%d-%H%M%S).log"
iteration=1

./sno-deploy-load/sno-deploy-load.py -w -i 60 -t int-ztp-100-100b-7200i-${iteration} interval -b 100 -i 7200 ztp 2>&1 | tee ${log_file}
