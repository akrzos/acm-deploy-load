#!/usr/bin/env bash
# Purpose of this script is to run a quick dry-run to verify everything is set to run the actual test
set -e
set -o pipefail

iteration=1
interval_period=7200

log_file="dr-$(date -u +%Y%m%d-%H%M%S).log"
# acm_ver=$(cat /root/rhacm-deploy/deploy/snapshot.ver)
# test_ver="ZTP Scale Run ${iteration}"
# hub_ocp=$(oc version -o json | jq -r '.openshiftVersion')
# sno_ocp=$(grep "imageSetRef:" /root/hv-sno/manifests/sno00001/manifest.yml -A 1 | grep "name" | awk '{print $NF}' | sed 's/openshift-//')

# Dry run "overrides"
acm_ver="ACM Version Dry Run"
test_ver="ZTP Scale Run ${iteration}"
hub_ocp="Hub Dry Run"
sno_ocp="SNO Dry Run"
interval_period=1

time ./sno-deploy-load/sno-deploy-load.py --dry-run --start-delay 1 --end-delay 1 --acm-version "${acm_ver}" --test-version "${test_ver}" --hub-version "${hub_ocp}" --sno-version "${sno_ocp}" -w -i 10 -t dry-run interval -b 100 -i ${interval_period} ztp 2>&1 | tee ${log_file}

results_dir=$(grep "Results data captured in:" $log_file | awk '{print $NF}')

time ./sno-deploy-load/sno-deploy-graph.py --acm-version "${acm_ver}" --test-version "${test_ver}" --hub-version "${hub_ocp}" --sno-version "${sno_ocp}" ${results_dir}

time ./scripts/post-test-data-collection.sh

mv ${log_file} ${results_dir}
