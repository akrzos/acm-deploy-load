#!/usr/bin/env bash
set -e
set -o pipefail

log_file="iz-$(date -u +%Y%m%d-%H%M%S).log"
iteration=1

time ./sno-deploy-load/sno-deploy-load.py -e 1000 -w -i 60 -t int-ztp-100-100b-7200i-${iteration} interval -b 100 -i 7200 ztp 2>&1 | tee ${log_file}

results_dir=$(grep "Results data captured in:" $log_file | awk '{print $NF}')

time ./sno-deploy-load/sno-deploy-graph.py --acm-version "$(cat /root/rhacm-deploy/deploy/snapshot.ver)" --test-version "ZTP Scale Run ${iteration}" ${results_dir}
