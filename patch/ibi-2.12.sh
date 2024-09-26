#!/usr/bin/env bash
# IBIO Image Patch

export KUBECONFIG=/root/bm/kubeconfig

# echo "Patching MCE IBIO container image"
# oc image mirror -a /opt/registry/pull-secret-disconnected.txt quay.io/itsoiref/image-based-install-operator:cabundle e38-h01-000-r650.rdu2.scalelab.redhat.com:5000/ibio/image-based-install-operator:cabundle --keep-manifest-list
# oc image mirror -a /opt/registry/pull-secret-disconnected.txt quay.io/itsoiref/image-based-install-operator:fixes e38-h01-000-r650.rdu2.scalelab.redhat.com:5000/ibio/image-based-install-operator:fixes-03 --keep-manifest-list
# oc image mirror -a /opt/registry/pull-secret-disconnected.txt quay.io/itsoiref/image-based-install-operator:fixes2 e38-h01-000-r650.rdu2.scalelab.redhat.com:5000/ibio/image-based-install-operator:fixes2-01 --keep-manifest-list
# oc image mirror -a /opt/registry/pull-secret-disconnected.txt quay.io/itsoiref/image-based-install-operator:dataimage e38-h01-000-r650.rdu2.scalelab.redhat.com:5000/ibio/image-based-install-operator:dataimage --keep-manifest-list

# echo "Pausing MCE"
# oc annotate multiclusterengine multiclusterengine pause=true
# oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="manager").image'
# oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="server").image'
# oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] |= (select(.name=="manager").image = "e38-h01-000-r650.rdu2.scalelab.redhat.com:5000/ibio/image-based-install-operator:dataimage")' | oc replace -f -
# oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] |= (select(.name=="server").image = "e38-h01-000-r650.rdu2.scalelab.redhat.com:5000/ibio/image-based-install-operator:dataimage")' | oc replace -f -
# oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="manager").image'
# oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="server").image'
# echo "Sleep 15"
# sleep 15

# # DataImage IBIO needs an additional patch to the clusterrole
# echo "Patching IBIO clusterrole"
# oc patch clusterrole open-cluster-management:image-based-install-operator:controller-manager --type json -p '[{"op": "add", "path": "/rules/-", "value": {"apiGroups": ["metal3.io"], "resources": ["baremetalhosts/finalizers"], "verbs": ["update"]}}, {"op": "add", "path": "/rules/-", "value": {"apiGroups": ["metal3.io"], "resources": ["dataimages"], "verbs": ["create", "delete", "get", "list", "patch", "update", "watch"]}}]'

# Patch hive-controller
echo "Pausing MCE"
oc annotate multiclusterengine multiclusterengine pause=true
echo "Scaling Hive Operator to 0"
oc scale -n multicluster-engine deploy/hive-operator --replicas=0
echo "Sleep 15"
sleep 15
echo "Patching Hive Controller container image"
oc get deploy -n hive hive-controllers -o json | jq '.spec.template.spec.containers[] | select(.name=="manager").image'
oc get deploy -n hive hive-controllers -o json | jq '.spec.template.spec.containers[] |= (select(.name=="manager").image = "e38-h01-000-r650.rdu2.scalelab.redhat.com:5000/hive/hive:clusterinstall-update-order-03")' | oc replace -f -
oc get deploy -n hive hive-controllers -o json | jq '.spec.template.spec.containers[] | select(.name=="manager").image'
echo "Sleep 15"
sleep 15
