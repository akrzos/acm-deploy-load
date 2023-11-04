#!/usr/bin/env bash
# Ansible Automation Platform ZTP day2 tuning

echo "Patching AAP resource-operator-controller-manager's platform-resource-manager memory limit to 32Gi"
oc get csv -n ansible-automation-platform aap-operator.v2.4.0-0.1697506179 -o json | jq '.spec.install.spec.deployments[] | select(.name=="resource-operator-controller-manager").spec.template.spec.containers[] | select(.name=="platform-resource-manager").resources.limits.memory'
oc get deploy -n ansible-automation-platform resource-operator-controller-manager -o json | jq '.spec.template.spec.containers[] | select(.name=="platform-resource-manager").resources'
oc get csv -n ansible-automation-platform aap-operator.v2.4.0-0.1697506179 -o json | jq '.spec.install.spec.deployments[] |= (select(.name=="resource-operator-controller-manager").spec.template.spec.containers[] |= (select(.name=="platform-resource-manager").resources.limits.memory = "32Gi"))' | oc replace -f -
oc get csv -n ansible-automation-platform aap-operator.v2.4.0-0.1697506179 -o json | jq '.spec.install.spec.deployments[] | select(.name=="resource-operator-controller-manager").spec.template.spec.containers[] | select(.name=="platform-resource-manager").resources.limits.memory'
oc get deploy -n ansible-automation-platform resource-operator-controller-manager -o json | jq '.spec.template.spec.containers[] | select(.name=="platform-resource-manager").resources'
# echo "Sleep 15"
# sleep 15

echo "Done Patching"
