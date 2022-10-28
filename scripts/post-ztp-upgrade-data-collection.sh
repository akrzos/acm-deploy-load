#!/usr/bin/env bash
#set -e
set -o pipefail

results_dir=$(ls -td results/*/ | head -1)
output_dir=${results_dir}/upgrade-data
mkdir -p ${output_dir}

echo "$(date -u) :: Collecting platform/operator upgrade cgu data"

if [[ $(oc get cgu -n ztp-platform-upgrade-prep) ]]; then
  echo "$(date -u) :: Collecting ztp-platform-upgrade-prep data"
  oc get cgu -n ztp-platform-upgrade-prep > ${output_dir}/ztp-platform-upgrade-prep.cgus
  oc get cgu -n ztp-platform-upgrade-prep -o yaml > ${output_dir}/ztp-platform-upgrade-prep.cgus.yaml
  oc describe cgu -n ztp-platform-upgrade-prep > ${output_dir}/ztp-platform-upgrade-prep.cgus.describe
  oc get cgu -n ztp-platform-upgrade-prep --no-headers -o custom-columns=NAME:'.metadata.name',READY:'.status.conditions[?(@.type=="Ready")].reason' > ${output_dir}/ztp-platform-upgrade-prep.cgus.status
  cat ${output_dir}/ztp-platform-upgrade-prep.cgus.status | awk '{print $2}' | sort | uniq -c > ${output_dir}/ztp-platform-upgrade-prep.cgus.status_count
  oc get cgu -n ztp-platform-upgrade-prep -o yaml | grep "state" | sed 's/\s*state:\s*//g' | sort | uniq -c > ${output_dir}/ztp-platform-upgrade-prep.cgus.sno_state_count
  oc get cgu -n ztp-platform-upgrade-prep -o yaml | grep "InProgress" -B 2 | grep sno | sed 's/\s*//g' | sed 's/://g' > ${output_dir}/ztp-platform-upgrade-prep.cgus.sno_InProgress
else
  echo "$(date -u) :: No ztp-platform-upgrade-prep data"
fi

if [[ $(oc get cgu -n ztp-platform-upgrade) ]]; then
  echo "$(date -u) :: Collecting ztp-platform-upgrade data"
  oc get cgu -n ztp-platform-upgrade > ${output_dir}/ztp-platform-upgrade.cgus
  oc get cgu -n ztp-platform-upgrade -o yaml > ${output_dir}/ztp-platform-upgrade.cgus.yaml
  oc describe cgu -n ztp-platform-upgrade > ${output_dir}/ztp-platform-upgrade.cgus.describe
  oc get cgu -n ztp-platform-upgrade --no-headers -o custom-columns=NAME:'.metadata.name',READY:'.status.conditions[?(@.type=="Ready")].reason' > ${output_dir}/ztp-platform-upgrade.cgus.status
  cat ${output_dir}/ztp-platform-upgrade.cgus.status | awk '{print $2}' | sort | uniq -c > ${output_dir}/ztp-platform-upgrade.cgus.status_count
  oc get cgu -n ztp-platform-upgrade -o yaml | grep "state" | sed 's/\s*state:\s*//g' | sort | uniq -c > ${output_dir}/ztp-platform-upgrade.cgus.sno_state_count
  oc get cgu -n ztp-platform-upgrade -o yaml | grep "InProgress" -B 2 | grep sno | sed 's/\s*//g' | sed 's/://g' > ${output_dir}/ztp-platform-upgrade.cgus.sno_InProgress
else
  echo "$(date -u) :: No ztp-platform-upgrade data"
fi

if [[ $(oc get cgu -n ztp-operator-upgrade-prep) ]]; then
  echo "$(date -u) :: Collecting ztp-operator-upgrade-prep data"
  oc get cgu -n ztp-operator-upgrade-prep > ${output_dir}/ztp-operator-upgrade-prep.cgus
  oc get cgu -n ztp-operator-upgrade-prep -o yaml > ${output_dir}/ztp-operator-upgrade-prep.cgus.yaml
  oc describe cgu -n ztp-operator-upgrade-prep > ${output_dir}/ztp-operator-upgrade-prep.cgus.describe
  oc get cgu -n ztp-operator-upgrade-prep --no-headers -o custom-columns=NAME:'.metadata.name',READY:'.status.conditions[?(@.type=="Ready")].reason' > ${output_dir}/ztp-operator-upgrade-prep.cgus.status
  cat ${output_dir}/ztp-operator-upgrade-prep.cgus.status | awk '{print $2}' | sort | uniq -c > ${output_dir}/ztp-operator-upgrade-prep.cgus.status_count
  oc get cgu -n ztp-operator-upgrade-prep -o yaml | grep "state" | sed 's/\s*state:\s*//g' | sort | uniq -c > ${output_dir}/ztp-operator-upgrade-prep.cgus.sno_state_count
  oc get cgu -n ztp-operator-upgrade-prep -o yaml | grep "InProgress" -B 2 | grep sno | sed 's/\s*//g' | sed 's/://g' > ${output_dir}/ztp-operator-upgrade-prep.cgus.sno_InProgress
else
  echo "$(date -u) :: No ztp-operator-upgrade-prep data"
fi

if [[ $(oc get cgu -n ztp-operator-upgrade) ]]; then
  echo "$(date -u) :: Collecting ztp-operator-upgrade data"
  oc get cgu -n ztp-operator-upgrade > ${output_dir}/ztp-operator-upgrade.cgus
  oc get cgu -n ztp-operator-upgrade -o yaml > ${output_dir}/ztp-operator-upgrade.cgus.yaml
  oc describe cgu -n ztp-operator-upgrade > ${output_dir}/ztp-operator-upgrade.cgus.describe
  oc get cgu -n ztp-operator-upgrade --no-headers -o custom-columns=NAME:'.metadata.name',READY:'.status.conditions[?(@.type=="Ready")].reason' > ${output_dir}/ztp-operator-upgrade.cgus.status
  cat ${output_dir}/ztp-operator-upgrade.cgus.status | awk '{print $2}' | sort | uniq -c > ${output_dir}/ztp-operator-upgrade.cgus.status_count
  oc get cgu -n ztp-operator-upgrade -o yaml | grep "state" | sed 's/\s*state:\s*//g' | sort | uniq -c > ${output_dir}/ztp-operator-upgrade.cgus.sno_state_count
  oc get cgu -n ztp-operator-upgrade -o yaml | grep "InProgress" -B 2 | grep sno | sed 's/\s*//g' | sed 's/://g' > ${output_dir}/ztp-operator-upgrade.cgus.sno_InProgress
else
  echo "$(date -u) :: No ztp-operator-upgrade data"
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

echo "$(date -u) :: Done collecting data"
