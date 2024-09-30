# acm-deploy-load

Tools and scripts to prepare, load, and analyze a large scale OCP cluster with ACM with cluster
deployments and upgrades. Clusters can be deployed via assisted-installer or via image-based
installer. Either Manifests, SiteConfigs, or clusterinstances can be deployed or pushed via GitOps
to deploy clusters.

## Workload Scripts

### acm-deploy-load.py

Tool to load ACM with cluster deployments via manifests or GitOps ZTP

Methods

* `ai-manifest` - Assisted-installer installed clusters via oc apply yaml manifests
* `ai-clusterinstance` - Assisted-installer installed clusters via oc apply ClusterInstance
* `ai-clusterinstance-gitops` - Assisted-installer installed clusters via ClusterInstances in GitOps
* `ai-siteconfig-gitops` - Default - Assisted-installer installed clusters via SiteConfigs in GitOps
* `ibi-manifest` - Image-based installer installed clusters via oc apply yaml manifests
* `ibi-clusterinstance` - Image-based installer installed clusters via oc apply ClusterInstance
* `ibi-clusterinstance-gitops` - Image-based installer installed clusters via ClusterInstances in GitOps

Load/Rate Option

* interval - Deploys X number of clusters per Y interval time period

Phases of the Workload

1. Deploy Phase - Apply Manifests or GitOps ZTP to deploy clusters
2. Wait for Cluster Install Completion
3. Wait for DU Profile Completion
4. Report Card / Graphing

### acm-mc-workload.py

Tool to load ACM with previously deployed clusters and on interval update a configmap that maps to
policy templates triggering re-enforcing policies.

### mc-workload.py

Tool to load a managed cluster with namespaces, deployments, pods, configmaps, and secrets.

## Analysis Scripts

Analysis scripts can be run after deploying or upgrading clusters to understand success and performance of the system.

* analyze-agentclusterinstalls.py - Summarize and report count, min/avg/max, and 50/95/99 percentiles for cluster
installation timing
* analyze-clustergroupupgrades.py - Summarize and report count, min/avg/max, and 50/95/99 percentiles for ztp-install
clustergroupupgrade custom resources
* analyze-acm-deploy-time.py - Determine deployment duration metrics and peak concurrency from acm-deploy-load
monitoring data
* analyze-upgrade.py - Summarize platform and operator upgrade success and timings from CGUs across upgraded Clusters
* analyze-clusterversion.py - Summarizes cluster upgrade success and timing as observed from the cluster's
clusterversion resources and generates csv of upgrades to be consumed by graphing script

## Graphing Scripts

* graph-clusterversion.py - Graph csv data from analyze-clusterversion.py script
* graph-acm-deploy.py - Graph monitor_data.csv from acm-deploy-load.py
* graph-upgrade.py - Graph csv data as time-series from analyze-upgrade script

## Patch Scripts

Located in the [patch directory](patch), and provide memory limits tuning or image patches specific to scale tests for
specific versions.

## Other Scripts

* ocp-health.py - Check if a cluster is healthy/stable
  * Check if clusterversion is available and/or failing
  * Check if all clusteroperators are available and/or degraded
  * Check if all nodes are ready, unknown or under memory/disk/pid pressure
  * Check if all machineconfigpools updated and/or degraded
  * Check for etcd leader elections
* acm-health.py - Check if ACM is healthy/stable
  * Check if multiclusterhub is available
  * Check if multiclusterengine is available
  * Check if multiclusterobservability is available
