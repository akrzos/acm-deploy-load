#!/usr/bin/env bash
# IBIO Image Patch

export KUBECONFIG=/root/bm/kubeconfig

bastion=$(hostname)

echo "Pausing MCE"
oc annotate multiclusterengine multiclusterengine pause=true

echo "Patching MCE IBIO container image"
# oc image mirror -a /opt/registry/pull-secret-bastion.txt quay.io/itsoiref/image-based-install-operator:cabundle ${bastion}:5000/ibio/image-based-install-operator:cabundle --keep-manifest-list
# oc image mirror -a /opt/registry/pull-secret-bastion.txt quay.io/itsoiref/image-based-install-operator:fixes ${bastion}:5000/ibio/image-based-install-operator:fixes-03 --keep-manifest-list
# oc image mirror -a /opt/registry/pull-secret-bastion.txt quay.io/itsoiref/image-based-install-operator:fixes2 ${bastion}:5000/ibio/image-based-install-operator:fixes2-01 --keep-manifest-list
# oc image mirror -a /opt/registry/pull-secret-bastion.txt quay.io/itsoiref/image-based-install-operator:dataimage ${bastion}:5000/ibio/image-based-install-operator:dataimage --keep-manifest-list
# DataImage IBIO needs an additional patch to the clusterrole
# echo "Patching IBIO clusterrole"
# oc patch clusterrole open-cluster-management:image-based-install-operator:controller-manager --type json -p '[{"op": "add", "path": "/rules/-", "value": {"apiGroups": ["metal3.io"], "resources": ["baremetalhosts/finalizers"], "verbs": ["update"]}}, {"op": "add", "path": "/rules/-", "value": {"apiGroups": ["metal3.io"], "resources": ["dataimages"], "verbs": ["create", "delete", "get", "list", "patch", "update", "watch"]}}]'
# OOM image to address IBIO OOM at scale
oc image mirror -a /opt/registry/pull-secret-bastion.txt quay.io/itsoiref/image-based-install-operator:oom ${bastion}:5000/ibio/image-based-install-operator:oom-03 --keep-manifest-list

oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="manager").image'
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="server").image'
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] |= (select(.name=="manager").image = "'"${bastion}"':5000/ibio/image-based-install-operator:oom-03")' | oc replace -f -
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] |= (select(.name=="server").image = "'"${bastion}"':5000/ibio/image-based-install-operator:oom-03")' | oc replace -f -
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="manager").image'
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="server").image'
echo "Sleep 15"
sleep 15

# Patch MCE IBIO Memory Limits (Needs MCE pause)
echo "Patching MCE IBIO container image memory limits"
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[0].resources.limits.memory'
oc get deploy -n multicluster-engine image-based-install-operator -o json |  jq '.spec.template.spec.containers[0].resources.limits.memory = "16Gi"' | oc replace -f -
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[0].resources.limits.memory'
echo "Sleep 15"
sleep 15

# Patch hive-controller container image (requires mce pause)
# echo "Scaling Hive Operator to 0"
# oc scale -n multicluster-engine deploy/hive-operator --replicas=0
# echo "Sleep 15"
# sleep 15
# echo "Patching Hive Controller container image"
# oc image mirror -a /opt/registry/pull-secret-bastion.txt quay.io/2uasimojo/hive:clusterinstall-update-order ${bastion}:5000/hive/hive:clusterinstall-update-order-03 --keep-manifest-list
# oc get deploy -n hive hive-controllers -o json | jq '.spec.template.spec.containers[] | select(.name=="manager").image'
# oc get deploy -n hive hive-controllers -o json | jq '.spec.template.spec.containers[] |= (select(.name=="manager").image = "'"${bastion}"':5000/hive/hive:clusterinstall-update-order-03")' | oc replace -f -
# oc get deploy -n hive hive-controllers -o json | jq '.spec.template.spec.containers[] | select(.name=="manager").image'
# echo "Sleep 15"
# sleep 15
