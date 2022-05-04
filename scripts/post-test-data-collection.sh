#!/usr/bin/env bash
#set -e
set -o pipefail

results_dir=$(ls -td results/*/ | head -1)
output_dir=${results_dir}/data
mkdir -p ${output_dir}

if [ "$1" == "-k" ]; then
  echo "$(date -u) :: Getting SNO kubeconfigs"
  ls /root/hv-sno/manifests/ | xargs -I % sh -c "oc get secret %-admin-kubeconfig -n % -o json | jq -r '.data.kubeconfig' | base64 -d > /root/hv-sno/manifests/%/kubeconfig"
fi

echo "$(date -u) :: Collecting namespaces and pod data"

oc get ns > ${output_dir}/namespaces
oc get ns -o yaml > ${output_dir}/namespaces.yaml
oc get pods -A > ${output_dir}/pods
oc get pods -A -o yaml > ${output_dir}/pods.yaml

echo "$(date -u) :: Collecting agentclusterinstall data"

oc get agentclusterinstall -A --no-headers -o custom-columns=NAME:'.metadata.name',COMPLETED:'.status.conditions[?(@.type=="Completed")].reason' > ${output_dir}/aci.status
oc describe agentclusterinstall -A > ${output_dir}/aci.describe
oc get agentclusterinstall -A -o yaml > ${output_dir}/aci.yaml

cat ${output_dir}/aci.status | awk '{print $2}' | sort | uniq -c > ${output_dir}/aci.status_count
cat ${output_dir}/aci.status | grep "InstallationFailed" | awk '{print $1}'  > ${output_dir}/aci.InstallationFailed
cat ${output_dir}/aci.status | grep "InstallationNotStarted" | awk '{print $1}' > ${output_dir}/aci.InstallationNotStarted

echo "$(date -u) :: Collecting managedcluster data"

oc get managedcluster -A > ${output_dir}/managedcluster.get_default
oc describe managedcluster -A > ${output_dir}/managedcluster.describe
oc get managedcluster -A --no-headers -o custom-columns=NAME:'.metadata.name',AVAILABLE:'.status.conditions[?(@.type=="ManagedClusterConditionAvailable")].status' > ${output_dir}/managedcluster.available

cat ${output_dir}/managedcluster.available | grep "Unknown" > ${output_dir}/mc.Unknown

echo "$(date -u) :: Collecting clustergroupupgrades data"

oc get clustergroupupgrades -n ztp-install --no-headers -o custom-columns=NAME:'.metadata.name',READY:'.status.conditions[?(@.type=="Ready")].reason' > ${output_dir}/cgu.status
oc describe clustergroupupgrades -n ztp-install > ${output_dir}/cgu.describe
oc get clustergroupupgrades -n ztp-install -o yaml > ${output_dir}/cgu.yaml

cat ${output_dir}/cgu.status | awk '{print $2}' | sort | uniq -c > ${output_dir}/cgu.status_count
cat ${output_dir}/cgu.status | grep "UpgradeTimedOut" > ${output_dir}/cgu.UpgradeTimedOut

echo "$(date -u) :: Inspecting failed SNO installs"
truncate -s 0 ${output_dir}/sno-install-failures

for cluster in $(cat ${output_dir}/aci.InstallationFailed); do
  echo "$(date -u) :: Checking cluster ${cluster}"
  export KUBECONFIG=/root/hv-sno/manifests/${cluster}/kubeconfig
  if ! oc get pods 2>/dev/null >/dev/null; then
    if ssh core@$cluster sudo crictl logs $(ssh core@$cluster sudo crictl ps -a --name '^kube-apiserver$' -q 2>/dev/null | head -1) 2>&1 | grep "ca-bundle.crt: no such file or directory" -q; then
      echo "Bz2017860 $cluster" >> ${output_dir}/sno-install-failures
      continue
    fi
    echo "Offline $cluster" >> ${output_dir}/sno-install-failures
    continue
  fi
  if oc get pods -A | grep -E '(openshift-apiserver|openshift-authentication|openshift-oauth-apiserver)' | grep -q Crash; then
      echo "BadOVN $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
  if oc get pods -A | grep openshift-authentication | grep -q Crash; then
      echo "BadOVN $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
  if oc get pods -n openshift-authentication 2>/dev/null | grep -q ContainerCreating; then
      echo "BadOVN $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
  if oc get co monitoring -ojson  | jq '.status.conditions[] | select(.type == "Degraded").message' -r | grep 'Grafna Deployment failed' -q; then
      echo "BadOVN $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
if oc get co machine-config  -ojson | jq '.status.conditions[] | select(.type=="Degraded").message' | grep -q "waitForControllerConfigToBeCompleted"; then
      echo "WeirdMCO $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
if oc get co machine-config  -ojson | jq '.status.conditions[] | select(.type=="Degraded").message' | grep -q "waitForDeploymentRollout"; then
      echo "WeirdMCO2 $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
  if [[ $(oc get co -ojson | jq -r '[.items[] | select((.status.conditions[]? | select(.type == "Available").status) == "False").metadata.name] | length') == "1" && $(oc get co -ojson | jq -r '.items[] | select((.status.conditions[]? | select(.type == "Available").status) == "False").metadata.name') == "console" ]]; then
      echo "BadConsole $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
  if ! oc logs -n openshift-kube-controller-manager kube-controller-manager-$cluster kube-controller-manager 2>/dev/null 1>/dev/null; then
      echo "DeadKubeControllerManager $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
  if [[ $(oc get pods -A -ojson | jq '[.items[] | select(.status.phase == "Pending").metadata.name] | length') > 10 ]]; then
      echo "BadOVNMaybe-LotsOfPending $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
  if [[ $(oc get co -ojson | jq -r '[.items[] | select((.status.conditions[]? | select(.type == "Available").status) == "False").metadata.name] | length') == "0" ]]; then
      echo "EventuallyOkay $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
  echo "Else $cluster" >> ${output_dir}/sno-install-failures
done

cat ${output_dir}/sno-install-failures | awk '{print $1}' | sort | uniq -c > ${output_dir}/sno-install-failures.failure_count

echo "$(date -u) :: Done collecting data"
