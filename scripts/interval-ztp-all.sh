#!/usr/bin/env bash
set -e
set -o pipefail

log_file="iz-all-$(date -u +%Y%m%d-%H%M%S).log"
acm_ver=$(cat /root/rhacm-deploy/deploy/snapshot.ver)
hub_ocp=$(oc version -o json | jq -r '.openshiftVersion')
# Usually the sno ocp is the same as the hub, adjust otherwise
sno_ocp=${hub_ocp}
iteration=1

time ./sno-deploy-load/sno-deploy-load.py --acm-version "${acm_ver}" --hub-version "${hub_ocp}" --sno-version "${sno_ocp}" -w -i 60 -t int-ztp-100-100b-7200i-${iteration} interval -b 100 -i 7200 ztp 2>&1 | tee ${log_file}

results_dir=$(grep "Results data captured in:" $log_file | awk '{print $NF}')

time ./sno-deploy-load/sno-deploy-graph.py --acm-version "${acm_ver}" --hub-version "${hub_ocp}" --sno-version "${sno_ocp}" --test-version "ZTP Scale Run ${iteration}" ${results_dir}
