#!/usr/bin/env bash
# 3500 MC support

export KUBECONFIG=/root/bm/kubeconfig

echo "Applying ACM search-v2-operator collector resources bump"
oc patch search -n open-cluster-management search-v2-operator --type json -p '[{"op": "add", "path": "/spec/deployments/collector/resources", "value": {"limits": {"memory": "8Gi"}, "requests": {"memory": "64Mi", "cpu": "25m"}}}]'
echo "Sleep 10"
sleep 10
echo "Applying ACM search-v2-operator database resources bump"
oc patch search -n open-cluster-management search-v2-operator --type json -p '[{"op": "add", "path": "/spec/deployments/database/resources", "value": {"limits": {"memory": "16Gi"}, "requests": {"memory": "32Mi", "cpu": "25m"}}}]'
echo "Sleep 10"
sleep 10
echo "Applying ACM search-v2-operator indexer resources bump"
oc patch search -n open-cluster-management search-v2-operator --type json -p '[{"op": "add", "path": "/spec/deployments/indexer/resources", "value": {"limits": {"memory": "4Gi"}, "requests": {"memory": "128Mi", "cpu": "25m"}}}]'
echo "Sleep 10"
sleep 10

echo "Done Patching"
