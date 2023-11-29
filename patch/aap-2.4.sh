#!/usr/bin/env bash
# Ansible Automation Platform ZTP day2 tuning

aap_csv=$(oc get csv -n ansible-automation-platform -l operators.coreos.com/ansible-automation-platform-operator.ansible-automation-platfor= -o json | jq '.items[0].metadata.name' -r)

echo "Using AAP csv: ${aap_csv}"
echo "Patching AAP resource-operator-controller-manager's platform-resource-manager memory limit to 32Gi"
oc get csv -n ansible-automation-platform ${aap_csv} -o json | jq '.spec.install.spec.deployments[] | select(.name=="resource-operator-controller-manager").spec.template.spec.containers[] | select(.name=="platform-resource-manager").resources.limits.memory'
oc get deploy -n ansible-automation-platform resource-operator-controller-manager -o json | jq '.spec.template.spec.containers[] | select(.name=="platform-resource-manager").resources.limits.memory'
oc get csv -n ansible-automation-platform ${aap_csv} -o json | jq '.spec.install.spec.deployments[] |= (select(.name=="resource-operator-controller-manager").spec.template.spec.containers[] |= (select(.name=="platform-resource-manager").resources.limits.memory = "32Gi"))' | oc replace -f -
oc get csv -n ansible-automation-platform ${aap_csv} -o json | jq '.spec.install.spec.deployments[] | select(.name=="resource-operator-controller-manager").spec.template.spec.containers[] | select(.name=="platform-resource-manager").resources.limits.memory'
oc get deploy -n ansible-automation-platform resource-operator-controller-manager -o json | jq '.spec.template.spec.containers[] | select(.name=="platform-resource-manager").resources.limits.memory'
# echo "Sleep 15"
# sleep 15

# Possibly this belongs in ACM tuning instead of AAP, but is needed when AAP is enabled
# Tune multicluster-operators-hub-subscription for large scale interaction with AAP
# https://issues.redhat.com/browse/ACM-8636
echo "Applying ACM multicluster-operators-hub-subscription memory limit bump to 32Gi"
oc annotate mch -n open-cluster-management multiclusterhub mch-pause=True
oc get deploy -n open-cluster-management multicluster-operators-hub-subscription -o json | jq '.spec.template.spec.containers[] | select(.name=="multicluster-operators-hub-subscription") | .resources.limits.memory'
oc get deploy -n open-cluster-management multicluster-operators-hub-subscription -o json | jq '.spec.template.spec.containers[] |= (select(.name=="multicluster-operators-hub-subscription").resources.limits.memory = "32Gi")' | oc replace -f -
oc get deploy -n open-cluster-management multicluster-operators-hub-subscription -o json | jq '.spec.template.spec.containers[] | select(.name=="multicluster-operators-hub-subscription") | .resources.limits.memory'
echo "Sleep 10"
sleep 10

echo "Done Patching"
