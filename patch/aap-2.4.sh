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

echo "Done Patching"
