#!/usr/bin/env bash
set -e
set -o pipefail

iteration=1
interval_period=3600
batch=500

ts="$(date -u +%Y%m%d-%H%M%S)"
log_file="iz-1000-${ts}.log"
acm_ver=$(cat /root/rhacm-deploy/deploy/snapshot.ver)
test_ver="ZTP Scale Run ${iteration}"
hub_ocp=$(oc version -o json | jq -r '.openshiftVersion')
sno_ocp=$(grep "imageSetRef:" /root/hv-vm/sno/manifests/sno00001/manifest.yml -A 1 | grep "name" | awk '{print $NF}' | sed 's/openshift-//')
wan_em="(50ms/0.02)"

time ./sno-deploy-load/sno-deploy-load.py --acm-version "${acm_ver}" --test-version "${test_ver}" --hub-version "${hub_ocp}" --sno-version "${sno_ocp}" --wan-emulation "${wan_em}" -e 1000 -w -i 60 -t int-ztp-100-${batch}b-${interval_period}i-${iteration} interval -b ${batch} -i ${interval_period} ztp 2>&1 | tee ${log_file}

results_dir=$(grep "Results data captured in:" $log_file | awk '{print $NF}')

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./sno-deploy-load/sno-deploy-graph.py --acm-version "${acm_ver}" --test-version "${test_ver}" --hub-version "${hub_ocp}" --sno-version "${sno_ocp}" --wan-emulation "${wan_em}" ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./sno-deploy-load/sno-deploy-time.py ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./scripts/post-ztp-install-data-collection.sh -k 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./sno-deploy-load/analyze-agentclusterinstalls.py ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

time ./sno-deploy-load/analyze-clustergroupupgrades.py ${results_dir} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

oc adm must-gather --dest-dir="${results_dir}/must-gather-${ts}" 2>&1 | tee -a ${log_file}
tar caf ${results_dir}/must-gather-${ts}.tar.gz --remove-files ${results_dir}/must-gather-${ts} 2>&1 | tee -a ${log_file}

echo "################################################################################" 2>&1 | tee -a ${log_file}

meta=$(kubectl promdump meta -n openshift-monitoring -p prometheus-k8s-0 -c prometheus -d /prometheus </dev/null 2>&1 | tee -a ${log_file})
kubectl promdump -n openshift-monitoring -p prometheus-k8s-0 -c prometheus -d /prometheus --min-time "$(echo $meta | cut -d \| -f 5 | cut -d \  -f 2,3)" --max-time "$(echo $meta | cut -d \| -f 6 | cut -d \  -f 2,3)" > ${results_dir}/promdump-${ts}.tar.gz

echo "################################################################################" 2>&1 | tee -a ${log_file}

echo "Finished" 2>&1 | tee -a ${log_file}

cat ${log_file} | grep -v WARNING > ${results_dir}/${log_file}.nowarn

mv ${log_file} ${results_dir}

gzip ${results_dir}/${log_file}
