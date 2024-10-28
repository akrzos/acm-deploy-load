#!/usr/bin/env bash
# 3500 MC support

export KUBECONFIG=/root/mno/kubeconfig

# Addresses both:
# https://issues.redhat.com/browse/ACM-5791
# https://issues.redhat.com/browse/ACM-6288
# Fixed in 2.8.1-DOWNSTREAM-2023-07-14-22-34-17 and newer
# echo "Patching MCE ocm-controller and ocm-proxyserver image"
# oc get deploy -n multicluster-engine ocm-controller -o json |  jq '.spec.template.spec.containers[] | select(.name=="ocm-controller").image'
# oc get deploy -n multicluster-engine ocm-proxyserver -o json |  jq '.spec.template.spec.containers[] | select(.name=="ocm-proxyserver").image'
# oc annotate multiclusterengine multiclusterengine pause=true
# # oc image mirror -a /opt/registry/sync/pull-secret-bastion.acm_d.txt quay.io/zhiweiyin/multicloud-manager:2.3.1 e27-h01-000-r650.rdu2.scalelab.redhat.com:5000/zhiweiyin/multicloud-manager:2.3.1 --keep-manifest-list --continue-on-error=true
# oc get deploy -n multicluster-engine ocm-controller -o json |  jq '.spec.template.spec.containers[] |= (select(.name=="ocm-controller").image = "e27-h01-000-r650.rdu2.scalelab.redhat.com:5000/zhiweiyin/multicloud-manager:2.3.1")' | oc replace -f -
# oc get deploy -n multicluster-engine ocm-proxyserver -o json |  jq '.spec.template.spec.containers[] |= (select(.name=="ocm-proxyserver").image = "e27-h01-000-r650.rdu2.scalelab.redhat.com:5000/zhiweiyin/multicloud-manager:2.3.1")' | oc replace -f -
# oc get deploy -n multicluster-engine ocm-controller -o json |  jq '.spec.template.spec.containers[] | select(.name=="ocm-controller").image'
# oc get deploy -n multicluster-engine ocm-proxyserver -o json |  jq '.spec.template.spec.containers[] | select(.name=="ocm-proxyserver").image'
# echo "Sleep 15"
# sleep 15

# https://issues.redhat.com/browse/ACM-6288
# echo "Patching MCE ocm-proxyserver memory limits to 16Gi"
# oc get deploy -n multicluster-engine ocm-proxyserver -o json | jq '.spec.template.spec.containers[0].resources.limits.memory'
# oc annotate multiclusterengine multiclusterengine pause=true
# oc get deploy -n multicluster-engine ocm-proxyserver -o json |  jq '.spec.template.spec.containers[0].resources.limits.memory = "16Gi"' | oc replace -f -
# oc get deploy -n multicluster-engine ocm-proxyserver -o json | jq '.spec.template.spec.containers[0].resources.limits.memory'
# echo "Sleep 45"
# sleep 45

echo "Applying ACM search-v2-operator collector resources bump"
oc patch search -n open-cluster-management search-v2-operator --type json -p '[{"op": "add", "path": "/spec/deployments/collector/resources", "value": {"limits": {"memory": "8Gi"}, "requests": {"memory": "64Mi", "cpu": "25m"}}}]'
echo "Sleep 10"
sleep 10
echo "Applying ACM search-v2-operator database resources bump"
oc patch search -n open-cluster-management search-v2-operator --type json -p '[{"op": "add", "path": "/spec/deployments/database/resources", "value": {"limits": {"memory": "16Gi"}, "requests": {"memory": "32Mi", "cpu": "25m"}}}]'
echo "Sleep 10"
sleep 10
echo "Applying ACM search-v2-operator database envvars"
oc patch search -n open-cluster-management search-v2-operator --type json -p '[{"op": "add", "path": "/spec/deployments/database/envVar", "value": [{"name": "POSTGRESQL_EFFECTIVE_CACHE_SIZE", "value": "1024MB"}, {"name": "POSTGRESQL_SHARED_BUFFERS", "value": "512MB"}, {"name": "WORK_MEM", "value": "128MB"}]}]'
echo "Sleep 10"
sleep 10
echo "Applying ACM search-v2-operator indexer resources bump"
oc patch search -n open-cluster-management search-v2-operator --type json -p '[{"op": "add", "path": "/spec/deployments/indexer/resources", "value": {"limits": {"memory": "4Gi"}, "requests": {"memory": "128Mi", "cpu": "25m"}}}]'
echo "Sleep 10"
sleep 10
echo "Applying ACM search-v2-operator queryapi resources bump"
oc patch search -n open-cluster-management search-v2-operator --type json -p '[{"op": "add", "path": "/spec/deployments/queryapi/resources", "value": {"limits": {"memory": "4Gi"}, "requests": {"memory": "1Gi", "cpu": "25m"}}}]'
echo "Sleep 10"
sleep 10

echo "Applying ACM observability tuning"
echo "Applying ACM observability memcache tuning"
oc patch mco -n open-cluster-management-observability observability --type json -p '[{"op": "add", "path": "/spec/advanced", "value": {"queryFrontendMemcached": {"connectionLimit": 10240, "maxItemSize": "10m", "memoryLimitMb": 10240}, "storeMemcached": {"connectionLimit": 10240, "maxItemSize": "10m", "memoryLimitMb": 10240}}}]'
echo "Sleep 10"
sleep 10
# echo "Applying ACM observability store replicas 6 tuning"
# oc patch mco -n open-cluster-management-observability observability --type json -p '[{"op": "add", "path": "/spec/advanced/store", "value": {"replicas": "6"}}]'
# echo "Sleep 10"
# sleep 10
echo "Applying ACM observability route timeout tuning"
oc annotate route -n open-cluster-management-observability rbac-query-proxy --overwrite haproxy.router.openshift.io/timeout=300s
oc annotate route -n open-cluster-management-observability observatorium-api --overwrite haproxy.router.openshift.io/timeout=300s
echo "Sleep 10"
sleep 10

echo "Done Patching"
