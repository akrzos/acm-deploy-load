#!/usr/bin/env bash
#set -e
set -o pipefail

results_dir=$(ls -td results/*/ | head -1)
output_dir=${results_dir}/install-data
mkdir -p ${output_dir}

if [ "$1" == "-k" ]; then
  echo "$(date -u) :: Getting sno cluster kubeconfigs"
  ls /root/hv-vm/sno/manifests/ | xargs -I % sh -c "mkdir -p /root/hv-vm/kc/% ;oc get secret %-admin-kubeconfig -n % -o json | jq -r '.data.kubeconfig' | base64 -d > /root/hv-vm/kc/%/kubeconfig"
  echo "$(date -u) :: Getting compact cluster kubeconfigs"
  ls /root/hv-vm/compact/manifests/ | xargs -I % sh -c "mkdir -p /root/hv-vm/kc/%; oc get secret %-admin-kubeconfig -n % -o json | jq -r '.data.kubeconfig' | base64 -d > /root/hv-vm/kc/%/kubeconfig"
  echo "$(date -u) :: Getting standard cluster kubeconfigs"
  ls /root/hv-vm/standard/manifests/ | xargs -I % sh -c "mkdir -p /root/hv-vm/kc/%; oc get secret %-admin-kubeconfig -n % -o json | jq -r '.data.kubeconfig' | base64 -d > /root/hv-vm/kc/%/kubeconfig"
fi

echo "$(date -u) :: Collecting clusterversion, csv, nodes, namespaces and pod/event data"

oc get clusterversion > ${output_dir}/clusterversion
oc get clusterversion -o yaml > ${output_dir}/clusterversion.yaml
oc describe clusterversion > ${output_dir}/clusterversion.describe

# Get hub cluster install config
oc get cm -n kube-system cluster-config-v1 -o yaml > ${output_dir}/cluster-config-v1

oc get csv -A > ${output_dir}/csv
# Takes too much space:
# oc get csv -A -o yaml > ${output_dir}/csv.yaml
# oc describe csv -A > ${output_dir}/csv.describe

oc get no > ${output_dir}/nodes
oc get no -o yaml > ${output_dir}/nodes.yaml
oc describe no > ${output_dir}/nodes.describe
oc get ns > ${output_dir}/namespaces
oc get ns -o yaml > ${output_dir}/namespaces.yaml
oc get pods -A > ${output_dir}/pods
oc get pods -A -o yaml > ${output_dir}/pods.yaml
oc describe pods -A > ${output_dir}/pods.describe
oc get ev -A > ${output_dir}/events
oc get ev -A -o yaml > ${output_dir}/events.yaml

echo "$(date -u) :: Collecting agentclusterinstall data"

oc get agentclusterinstall -A --no-headers -o custom-columns=NAME:'.metadata.name',COMPLETED:'.status.conditions[?(@.type=="Completed")].reason' > ${output_dir}/aci.status
oc describe agentclusterinstall -A > ${output_dir}/aci.describe
oc get agentclusterinstall -A -o yaml > ${output_dir}/aci.yaml

cat ${output_dir}/aci.status | awk '{print $2}' | sort | uniq -c > ${output_dir}/aci.status_count
cat ${output_dir}/aci.status | grep "InstallationFailed" | awk '{print $1}' > ${output_dir}/aci.InstallationFailed
cat ${output_dir}/aci.status | grep "InstallationNotStarted" | awk '{print $1}' > ${output_dir}/aci.InstallationNotStarted
cat ${output_dir}/aci.status | grep "InstallationInProgress" | awk '{print $1}' > ${output_dir}/aci.InstallationInProgress

# Get 2 Deployed cluster's install-configs
cat ${output_dir}/aci.status | grep InstallationCompleted | head -n 2 | awk '{print $1}' | xargs -I % sh -c "oc --kubeconfig /root/hv-vm/kc/%/kubeconfig get cm -n kube-system cluster-config-v1 -o yaml > ${output_dir}/%.cluster-config-v1"

echo "$(date -u) :: Collecting managedcluster data"

oc get managedcluster -A > ${output_dir}/managedcluster.get_default
oc describe managedcluster -A > ${output_dir}/managedcluster.describe
oc get managedcluster -A --no-headers -o custom-columns=NAME:'.metadata.name',AVAILABLE:'.status.conditions[?(@.type=="ManagedClusterConditionAvailable")].status' > ${output_dir}/managedcluster.available

cat ${output_dir}/managedcluster.available | grep "Unknown" > ${output_dir}/mc.Unknown

echo "$(date -u) :: Collecting mch/mce data"

oc get mch -A > ${output_dir}/mch
oc get mch -A -o yaml > ${output_dir}/mch.yaml
oc describe mch -A > ${output_dir}/mch.describe

oc get mce > ${output_dir}/mce
oc get mce -o yaml > ${output_dir}/mce.yaml
oc describe mce > ${output_dir}/mce.describe

echo "$(date -u) :: Collecting policy data"

oc get policy -A > ${output_dir}/policy
oc get policy -A -o yaml > ${output_dir}/policy.yaml
# Also takes too much space
# oc describe policy -A > ${output_dir}/policy.describe

echo "$(date -u) :: Collecting clustergroupupgrades data"

oc get clustergroupupgrades -n ztp-install --no-headers -o custom-columns=NAME:'.metadata.name',READY:'.status.conditions[?(@.type=="Succeeded")].reason' > ${output_dir}/cgu.status
oc describe clustergroupupgrades -n ztp-install > ${output_dir}/cgu.describe
oc get clustergroupupgrades -n ztp-install -o yaml > ${output_dir}/cgu.yaml

cat ${output_dir}/cgu.status | awk '{print $2}' | sort | uniq -c > ${output_dir}/cgu.status_count
cat ${output_dir}/cgu.status | grep "TimedOut"  | awk '{print $1}' > ${output_dir}/cgu.TimedOut

echo "$(date -u) :: Inspecting failed cluster installs"
truncate -s 0 ${output_dir}/cluster-install-failures
for cluster in $(cat ${output_dir}/aci.InstallationFailed); do
  echo "$(date -u) :: Checking cluster ${cluster}"
  export KUBECONFIG=/root/hv-vm/kc/${cluster}/kubeconfig
  if ! oc get pods 2>/dev/null >/dev/null; then
    # needs adjustment for compact/standard
    if ssh core@${cluster} uptime 2>/dev/null >/dev/null; then
        echo "$cluster APIDown" | tee -a ${output_dir}/cluster-install-failures
        continue
    fi
    echo "$cluster Offline" | tee -a ${output_dir}/cluster-install-failures
    continue
  fi
  if oc get clusterversion -o json version | jq '.status.conditions[] | select(.status=="True") | select(.type=="Progressing").message ' | egrep "Working towards|some cluster operators are not available|MultipleErrors" -q; then
    # https://issues.redhat.com/browse/OCPBUGS-12881
    echo "$cluster ManyOperatorsIncomplete" | tee -a ${output_dir}/cluster-install-failures
    continue
  fi
  failure_found=false
  echo -n "$cluster " | tee -a ${output_dir}/cluster-install-failures
  autoscaler_degraded=$(oc get co cluster-autoscaler -o json | jq -r '.status.conditions==null')
  ceo_available=$(oc get co etcd -o json | jq -r '.status.conditions[] | select(.type=="Available").status')
  ceo_degraded=$(oc get co etcd -o json | jq -r '.status.conditions[] | select(.type=="Degraded").status')
  image_registry_degraded=$(oc get co image-registry -o json | jq -r '.status.conditions[] | select(.type=="Degraded").status')
  mco_degraded=$(oc get co machine-config -o json | jq -r '.status.conditions[] | select(.type=="Degraded").status')
  ks_degraded=$(oc get co kube-scheduler -o json | jq -r '.status.conditions[] | select(.type=="Degraded").status')
  olm_degraded=$(oc get co operator-lifecycle-manager -o json | jq -r '.status.conditions[] | select(.type=="Degraded").status')
  if [ $autoscaler_degraded == "true" ]; then
    # https://issues.redhat.com/browse/OCPBUGS-18954
    echo -n "ClusterAutoScalerDegraded " | tee -a ${output_dir}/cluster-install-failures
    failure_found=true
  fi
  if [ $ceo_available == "False" ]; then
    # https://issues.redhat.com/browse/OCPBUGS-12475
    echo -n "EtcdOperatorUnavailable " | tee -a ${output_dir}/cluster-install-failures
    failure_found=true
  fi
  if [ $ceo_degraded == "True" ]; then
    # https://issues.redhat.com/browse/OCPBUGS-12853
    echo -n "EtcdOperatorDegraded " | tee -a ${output_dir}/cluster-install-failures
    failure_found=true
  fi
  if [ $image_registry_degraded == "True" ]; then
    # https://issues.redhat.com/browse/OCPBUGS-18969
    echo -n "ImageRegistryDegraded " | tee -a ${output_dir}/cluster-install-failures
    failure_found=true
  fi
  if [ $mco_degraded == "True" ]; then
    # https://issues.redhat.com/browse/OCPBUGS-12741
    # https://issues.redhat.com/browse/OCPBUGS-18964 (Also detected as this)
    echo -n "MCODegraded " | tee -a ${output_dir}/cluster-install-failures
    failure_found=true
  fi
  if [ $olm_degraded == "True" ]; then
    echo -n "OLMDegraded " | tee -a ${output_dir}/cluster-install-failures
    failure_found=true
  fi
  if [ $ks_degraded == "True" ]; then
    echo -n "KubeSchedulerDegraded " | tee -a ${output_dir}/cluster-install-failures
    failure_found=true
  fi
  if $failure_found ; then
    echo "" | tee -a ${output_dir}/cluster-install-failures
  else
    # Sometimes a cluster is actually installed or seems installed by the time this script has completed
    # Alternatively this could be a new install failure type
    echo "Else" | tee -a ${output_dir}/cluster-install-failures
  fi
done
cat ${output_dir}/cluster-install-failures | awk '{$1=""; print $0}' | sort | uniq -c > ${output_dir}/cluster-install-failures.failure_count


echo "$(date -u) :: Inspecting 40 TimedOut CGUs"
mkdir -p ${output_dir}/cgu-failures
examined_cgu_failures=0

for cluster in $(cat ${output_dir}/cgu.TimedOut); do
  examined_cgu_failures=$((examined_cgu_failures+1))
  echo "$(date -u) :: Checking cluster ($examined_cgu_failures) - ${cluster}"
  export KUBECONFIG=/root/hv-vm/kc/${cluster}/kubeconfig
  mkdir -p ${output_dir}/cgu-failures/${cluster}

  oc get pods -A > ${output_dir}/cgu-failures/${cluster}/pods
  oc get pods -A -o yaml > ${output_dir}/cgu-failures/${cluster}/pods.yaml
  oc describe pods -A > ${output_dir}/cgu-failures/${cluster}/pods.describe

  oc get clusteroperators -A > ${output_dir}/cgu-failures/${cluster}/clusteroperators
  oc get clusteroperators -A -o yaml > ${output_dir}/cgu-failures/${cluster}/clusteroperators.yaml
  oc describe clusteroperators -A > ${output_dir}/cgu-failures/${cluster}/clusteroperators.describe

  oc get clusterversion -o yaml > ${output_dir}/cgu-failures/${cluster}/clusterversion.yaml

  oc get configurationpolicies -A > ${output_dir}/cgu-failures/${cluster}/configurationpolicies
  oc get configurationpolicies -A -o yaml > ${output_dir}/cgu-failures/${cluster}/configurationpolicies.yaml
  oc describe configurationpolicies -A > ${output_dir}/cgu-failures/${cluster}/configurationpolicies.describe

  oc get policies -A > ${output_dir}/cgu-failures/${cluster}/policies
  oc get policies -A -o yaml > ${output_dir}/cgu-failures/${cluster}/policies.yaml
  oc describe policies -A > ${output_dir}/cgu-failures/${cluster}/policies.describe

  oc get subs -A > ${output_dir}/cgu-failures/${cluster}/subs
  oc get subs -A -o yaml > ${output_dir}/cgu-failures/${cluster}/subs.yaml
  oc describe subs -A > ${output_dir}/cgu-failures/${cluster}/subs.describe

  oc get csvs -A > ${output_dir}/cgu-failures/${cluster}/csvs
  oc get csvs -A -o yaml > ${output_dir}/cgu-failures/${cluster}/csvs.yaml
  oc describe csvs -A > ${output_dir}/cgu-failures/${cluster}/csvs.describe

  oc get installplans -A > ${output_dir}/cgu-failures/${cluster}/installplans
  oc get installplans -A -o yaml > ${output_dir}/cgu-failures/${cluster}/installplans.yaml
  oc describe installplans -A > ${output_dir}/cgu-failures/${cluster}/installplans.describe

  oc get catalogsources -A > ${output_dir}/cgu-failures/${cluster}/catalogsources
  oc get catalogsources -A -o yaml > ${output_dir}/cgu-failures/${cluster}/catalogsources.yaml
  oc describe catalogsources -A > ${output_dir}/cgu-failures/${cluster}/catalogsources.describe

  if [ "$examined_cgu_failures" -ge "40" ]; then
    break
  fi
done

echo "$(date -u) :: Done collecting data"
