#!/usr/bin/env bash
# Imaged Based Install Scale Patches

export KUBECONFIG=/root/mno/kubeconfig

bastion=$(hostname)

echo "Pausing MCE"
oc annotate multiclusterengine multiclusterengine pause=true

# echo "Pausing MCH"
# oc annotate mch -n open-cluster-management multiclusterhub mch-pause=True

# Patch MCE IBIO container image (Requires MCE pause)
echo "Patching MCE IBIO container image"
# Fixed in ACM 2.12 FC5
# oc image mirror -a /opt/registry/pull-secret-bastion.txt quay.io/eranco74/image-based-install-operator:MGMT-19033 ${bastion}:5000/ibio/image-based-install-operator:MGMT-19033 --keep-manifest-list
# Not fixed yet
oc image mirror -a /opt/registry/pull-secret-bastion.txt quay.io/eranco74/image-based-install-operator:OCPBUGS-43330 ${bastion}:5000/ibio/image-based-install-operator:OCPBUGS-43330 --keep-manifest-list

oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="manager").image'
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="server").image'
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] |= (select(.name=="manager").image = "'"${bastion}"':5000/ibio/image-based-install-operator:OCPBUGS-43330")' | oc replace -f -
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] |= (select(.name=="server").image = "'"${bastion}"':5000/ibio/image-based-install-operator:OCPBUGS-43330")' | oc replace -f -
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="manager").image'
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="server").image'
echo "Sleep 15"
sleep 15

# # Patch MCE managedcluster-import-controller-v2 Memory Limits (Requires MCE pause)
# # Work on fix for https://issues.redhat.com/browse/ACM-15246 (Does not work)
# echo "Patching MCE managedcluster-import-controller-v2  container image memory limits"
# oc get deploy -n multicluster-engine managedcluster-import-controller-v2 -o json | jq '.spec.template.spec.containers[0].resources.limits.memory'
# oc get deploy -n multicluster-engine managedcluster-import-controller-v2 -o json | jq '.spec.template.spec.containers[0].resources.limits.memory = "7Gi"' | oc replace -f -
# oc get deploy -n multicluster-engine managedcluster-import-controller-v2 -o json | jq '.spec.template.spec.containers[0].resources.limits.memory'
# echo "Sleep 15"
# sleep 15
# # Patch MCE managedcluster-import-controller-v2 GOMEMLIMIT env var (Requires MCE pause)
# echo "Patching MCE managedcluster-import-controller-v2 GOMEMLIMIT env var"
# oc get deploy -n multicluster-engine managedcluster-import-controller-v2 -o json | jq '.spec.template.spec.containers[0].env[] | select(.name=="GOMEMLIMIT").value'
# oc get deploy -n multicluster-engine managedcluster-import-controller-v2 -o json | jq '.spec.template.spec.containers[0].env[] |= (select(.name=="GOMEMLIMIT").value = "6GiB")' | oc replace -f -
# oc get deploy -n multicluster-engine managedcluster-import-controller-v2 -o json | jq '.spec.template.spec.containers[0].env[] | select(.name=="GOMEMLIMIT").value'
# echo "Sleep 15"
# sleep 15

# # Patch MCE IBIO Memory Limits (Requires MCE pause)
# # Fixed in ACM 2.12 FC5
# echo "Patching MCE IBIO container image memory limits"
# oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[0].resources.limits.memory'
# oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[0].resources.limits.memory = "16Gi"' | oc replace -f -
# oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[0].resources.limits.memory'
# echo "Sleep 15"
# sleep 15

# # Patch MCE ocm-controller container image (Requires MCE pause)
# # Fixed in ACM 2.12 FC5
# echo "Patching MCE ocm-controller container image"
# oc image mirror -a /opt/registry/pull-secret-bastion.txt quay.io/stolostron/multicloud-manager:2.12.0-PR781-e04efaf8338b31f21f76bfdfcb95df6c291a4ead ${bastion}:5000/stolostron/multicloud-manager:deletefix-01 --keep-manifest-list
#
# oc get deploy -n multicluster-engine ocm-controller -o json | jq '.spec.template.spec.containers[] | select(.name=="ocm-controller").image'
# oc get deploy -n multicluster-engine ocm-controller -o json | jq '.spec.template.spec.containers[] |= (select(.name=="ocm-controller").image = "'"${bastion}"':5000/stolostron/multicloud-manager:deletefix-01")' | oc replace -f -
# oc get deploy -n multicluster-engine ocm-controller -o json | jq '.spec.template.spec.containers[] | select(.name=="ocm-controller").image'
# echo "Sleep 15"
# sleep 15

# # Patch SiteConfig Operator container image (Requires MCH pause)
# # Fixed in ACM 2.12 FC5
# echo "Patching ACM SiteConfig Operator container image"
# oc image mirror -a /opt/registry/pull-secret-bastion.txt quay.io/acm-d/siteconfig:latest ${bastion}:5000/acm-d/siteconfig:failed-fix-01 --keep-manifest-list
#
# oc get deploy -n open-cluster-management siteconfig-controller-manager -o json | jq '.spec.template.spec.containers[] | select(.name=="manager").image'
# oc get deploy -n open-cluster-management siteconfig-controller-manager -o json | jq '.spec.template.spec.containers[] |= (select(.name=="manager").image = "'"${bastion}"':5000/acm-d/siteconfig:failed-fix-01")' | oc replace -f -
# oc get deploy -n open-cluster-management siteconfig-controller-manager -o json | jq '.spec.template.spec.containers[] | select(.name=="manager").image'
