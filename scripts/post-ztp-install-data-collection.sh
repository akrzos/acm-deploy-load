#!/usr/bin/env bash
#set -e
set -o pipefail

results_dir=$(ls -td results/*/ | head -1)
output_dir=${results_dir}/install-data
mkdir -p ${output_dir}

if [ "$1" == "-k" ]; then
  echo "$(date -u) :: Getting SNO kubeconfigs"
  ls /root/hv-vm/sno/manifests/ | xargs -I % sh -c "oc get secret %-admin-kubeconfig -n % -o json | jq -r '.data.kubeconfig' | base64 -d > /root/hv-vm/sno/manifests/%/kubeconfig"
  echo "$(date -u) :: Getting compact cluster kubeconfigs"
  ls /root/hv-vm/compact/manifests/ | xargs -I % sh -c "oc get secret %-admin-kubeconfig -n % -o json | jq -r '.data.kubeconfig' | base64 -d > /root/hv-vm/compact/manifests/%/kubeconfig"
  echo "$(date -u) :: Getting standard cluster kubeconfigs"
  ls /root/hv-vm/standard/manifests/ | xargs -I % sh -c "oc get secret %-admin-kubeconfig -n % -o json | jq -r '.data.kubeconfig' | base64 -d > /root/hv-vm/standard/manifests/%/kubeconfig"
fi

echo "$(date -u) :: Collecting namespaces, nodes and pod data"

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
oc describe policy -A > ${output_dir}/policy.describe

echo "$(date -u) :: Collecting clustergroupupgrades data"

oc get clustergroupupgrades -n ztp-install --no-headers -o custom-columns=NAME:'.metadata.name',READY:'.status.conditions[?(@.type=="Succeeded")].reason' > ${output_dir}/cgu.status
oc describe clustergroupupgrades -n ztp-install > ${output_dir}/cgu.describe
oc get clustergroupupgrades -n ztp-install -o yaml > ${output_dir}/cgu.yaml

cat ${output_dir}/cgu.status | awk '{print $2}' | sort | uniq -c > ${output_dir}/cgu.status_count
cat ${output_dir}/cgu.status | grep "TimedOut"  | awk '{print $1}' > ${output_dir}/cgu.TimedOut

echo "$(date -u) :: Inspecting failed SNO installs"
truncate -s 0 ${output_dir}/sno-install-failures

for cluster in $(cat ${output_dir}/aci.InstallationFailed); do
  echo "$(date -u) :: Checking cluster ${cluster}"
  export KUBECONFIG=/root/hv-vm/sno/manifests/${cluster}/kubeconfig
  if ! oc get pods 2>/dev/null >/dev/null; then
    if ssh core@${cluster} sudo crictl logs $(ssh core@$cluster sudo crictl ps -a --name '^kube-apiserver$' -q 2>/dev/null | head -1) 2>&1 | grep "ca-bundle.crt: no such file or directory" -q; then
        echo "CaBundleCrt-Bz2017860 $cluster" >> ${output_dir}/sno-install-failures
        continue
    fi
    if ssh core@${cluster} sudo journalctl -u kubelet 2>&1 | grep "unable to destroy cgroup paths"  -q; then
        echo "SystemdTimeout-Bz2094952 $cluster" >> ${output_dir}/sno-install-failures
        continue
    fi
    echo "Offline $cluster" >> ${output_dir}/sno-install-failures
    continue
  fi
  if oc get pods -n openshift-apiserver -oyaml | grep -q ContainerStatusUnknown; then
      echo "ContainerStatusUnknown-bz2092940 $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
  if oc get pods -n openshift-oauth-apiserver -oyaml | grep -q ContainerStatusUnknown; then
      echo "ContainerStatusUnknown-bz2092940 $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
  if oc get pods -A | grep -E '(openshift-apiserver|openshift-authentication|openshift-oauth-apiserver|package-server-manager|cluster-storage-operator-)' | grep -q Crash; then
      echo "BadOVN-Bz2092907 $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
  if oc get pods -A | grep openshift-authentication | grep -q Crash; then
      echo "BadOVN-Bz2092907 $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
  if oc get pods -n openshift-authentication 2>/dev/null | grep -q ContainerCreating; then
      echo "AuthContainerCreating-BZ2016115 $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
  if oc get co monitoring -ojson  | jq '.status.conditions[] | select(.type == "Degraded").message' -r | grep 'Grafana Deployment failed' -q; then
      echo "BadOVN $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
  if oc get co machine-config  -ojson | jq '.status.conditions[]? | select(.type=="Degraded").message' | grep -q "waitForControllerConfigToBeCompleted"; then
      echo "WeirdMCO $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
  if oc get co machine-config  -ojson | jq '.status.conditions[]? | select(.type=="Degraded").message' | grep -q "waitForDeploymentRollout"; then
      echo "WeirdMCO2 $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
  if [[ $(oc get co -ojson | jq -r '[.items[] | select((.status.conditions[]? | select(.type == "Available").status) == "False").metadata.name] | length') == "1" && $(oc get co -ojson | jq -r '.items[] | select((.status.conditions[]? | select(.type == "Available").status) == "False").metadata.name') == "console" ]]; then
      echo "BadConsole $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
  if ! oc logs -n openshift-kube-controller-manager kube-controller-manager-$cluster kube-controller-manager 2>/dev/null 1>/dev/null; then
      echo "DeadKubeControllerManager-Bz2082628 $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
  if [[ $(oc get pods -A -ojson | jq '[.items[] | select(.status.phase == "Pending").metadata.name] | length') > 10 ]]; then
      echo "LotsOfPending-bz2093013 $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
  if [[ $(oc get co -ojson | jq -r '[.items[] | select((.status.conditions[]? | select(.type == "Available").status) == "False").metadata.name] | length') == "0" ]]; then
      echo "EventuallyOkay $cluster" >> ${output_dir}/sno-install-failures
      continue
  fi
  echo "Else $cluster" >> ${output_dir}/sno-install-failures
done

cat ${output_dir}/sno-install-failures | awk '{print $1}' | sort | uniq -c > ${output_dir}/sno-install-failures.failure_count

echo "$(date -u) :: Inspecting TimedOut CGUs"
mkdir -p ${output_dir}/cgu-failures

for cluster in $(cat ${output_dir}/cgu.TimedOut); do
  echo "$(date -u) :: Checking cluster ${cluster}"
  export KUBECONFIG=/root/hv-vm/sno/manifests/${cluster}/kubeconfig
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

done

echo "$(date -u) :: Done collecting data"
