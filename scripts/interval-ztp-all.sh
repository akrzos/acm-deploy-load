#!/usr/bin/env bash
set -e
set -o pipefail

iteration=1
interval_period=1800

log_file="iz-all-$(date -u +%Y%m%d-%H%M%S).log"
acm_ver=$(cat /root/rhacm-deploy/deploy/snapshot.ver)
test_ver="ZTP Scale Run ${iteration}"
hub_ocp=$(oc version -o json | jq -r '.openshiftVersion')
sno_ocp=$(grep "imageSetRef:" /root/hv-sno/manifests/sno00001/manifest.yml -A 1 | grep "name" | awk '{print $NF}' | sed 's/openshift-//')

time ./sno-deploy-load/sno-deploy-load.py --acm-version "${acm_ver}" --test-version "${test_ver}" --hub-version "${hub_ocp}" --sno-version "${sno_ocp}" -w -i 60 -t int-ztp-100-100b-${interval_period}i-${iteration} interval -b 100 -i ${interval_period} ztp 2>&1 | tee ${log_file}

results_dir=$(grep "Results data captured in:" $log_file | awk '{print $NF}')

time ./sno-deploy-load/sno-deploy-graph.py --acm-version "${acm_ver}" --test-version "${test_ver}" --hub-version "${hub_ocp}" --sno-version "${sno_ocp}" ${results_dir}

time ./scripts/post-test-data-collection.sh -k

time ./sno-deploy-load/analyze-agentclusterinstalls.py ${results_dir}

time ./sno-deploy-load/analyze-clustergroupupgrades.py ${results_dir}

mv ${log_file} ${results_dir}
