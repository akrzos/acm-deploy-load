#!/usr/bin/env bash
# IBIO Image Patch

export KUBECONFIG=/root/bm/kubeconfig

echo "Patching MCE IBIO container image"
# oc image mirror -a /opt/registry/pull-secret-disconnected.txt quay.io/itsoiref/image-based-install-operator:cabundle e38-h01-000-r650.rdu2.scalelab.redhat.com:5000/ibio/image-based-install-operator:cabundle --keep-manifest-list --continue-on-error=true
# oc image mirror -a /opt/registry/pull-secret-disconnected.txt quay.io/itsoiref/image-based-install-operator:fixes e38-h01-000-r650.rdu2.scalelab.redhat.com:5000/ibio/image-based-install-operator:fixes-03 --keep-manifest-list --continue-on-error=true
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="manager").image'
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="manager").command[]'
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="server").image'
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="server").command[]'
oc annotate multiclusterengine multiclusterengine pause=true
oc get deploy -n multicluster-engine image-based-install-operator -o json |  jq '.spec.template.spec.containers[] |= (select(.name=="manager").image = "e38-h01-000-r650.rdu2.scalelab.redhat.com:5000/ibio/image-based-install-operator:fixes-03")' | oc replace -f -
oc get deploy -n multicluster-engine image-based-install-operator -o json |  jq '.spec.template.spec.containers[] |= (select(.name=="server").image = "e38-h01-000-r650.rdu2.scalelab.redhat.com:5000/ibio/image-based-install-operator:fixes-03")' | oc replace -f -
oc get deploy -n multicluster-engine image-based-install-operator -o json |  jq '.spec.template.spec.containers[] |= (select(.name=="manager").command = ["/usr/local/bin/manager"])' | oc replace -f -
oc get deploy -n multicluster-engine image-based-install-operator -o json |  jq '.spec.template.spec.containers[] |= (select(.name=="server").command = ["/usr/local/bin/server"])' | oc replace -f -
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="manager").image'
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="manager").command[]'
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="server").image'
oc get deploy -n multicluster-engine image-based-install-operator -o json | jq '.spec.template.spec.containers[] | select(.name=="server").command[]'
echo "Sleep 45"
sleep 45
