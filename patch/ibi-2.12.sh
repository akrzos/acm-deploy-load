#!/usr/bin/env bash
# IBIO Image Patch

export KUBECONFIG=/root/bm/kubeconfig

bastion=$(hostname)

echo "Pausing MCE"
oc annotate multiclusterengine multiclusterengine pause=true

# Patch MCE IBIO container image (Requires MCE pause)
echo "Patching MCE IBIO container image"
oc image mirror -a /opt/registry/pull-secret-bastion.txt quay.io/eranco74/image-based-install-operator:MGMT-19033 ${bastion}:5000/ibio/image-based-install-operator:MGMT-19033 --keep-manifest-list

oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="manager").image'
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="server").image'
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] |= (select(.name=="manager").image = "'"${bastion}"':5000/ibio/image-based-install-operator:MGMT-19033")' | oc replace -f -
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] |= (select(.name=="server").image = "'"${bastion}"':5000/ibio/image-based-install-operator:MGMT-19033")' | oc replace -f -
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="manager").image'
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="server").image'
echo "Sleep 15"
sleep 15

# Patch MCE IBIO Memory Limits(Requires MCE pause)
echo "Patching MCE IBIO container image memory limits"
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[0].resources.limits.memory'
oc get deploy -n multicluster-engine image-based-install-operator -o json |  jq '.spec.template.spec.containers[0].resources.limits.memory = "16Gi"' | oc replace -f -
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[0].resources.limits.memory'
echo "Sleep 15"
sleep 15

# Patch MCE ocm-controller container image (Requires MCE pause)
echo "Patching MCE ocm-controller container image"
oc image mirror -a /opt/registry/pull-secret-bastion.txt quay.io/stolostron/multicloud-manager:2.12.0-PR781-e04efaf8338b31f21f76bfdfcb95df6c291a4ead ${bastion}:5000/stolostron/multicloud-manager:deletefix-01 --keep-manifest-list

oc get deploy -n multicluster-engine ocm-controller -o json | jq '.spec.template.spec.containers[] | select(.name=="ocm-controller").image'
oc get deploy -n multicluster-engine ocm-controller -o json | jq '.spec.template.spec.containers[] |= (select(.name=="ocm-controller").image = "'"${bastion}"':5000/stolostron/multicloud-manager:deletefix-01")' | oc replace -f -
oc get deploy -n multicluster-engine ocm-controller -o json | jq '.spec.template.spec.containers[] | select(.name=="ocm-controller").image'
echo "Sleep 15"
sleep 15
