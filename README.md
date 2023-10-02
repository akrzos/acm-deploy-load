# acm-deploy-load

Tools and scripts to load and analyze ACM with cluster deployments and upgrades. Clusters are deployed via manifests or
GitOps using Zero Touch Provisioning (ZTP).

## Workload Script

### acm-deploy-load.py

Tool to load ACM with cluster deployments via manifests or GitOps ZTP

Load/Rate Option

* interval - Deploys X number of clusters (manifests or GitOps ZTP) per Y interval time period

Phases of the Workload

1. Deploy Phase - Apply Manifests or GitOps ZTP to deploy clusters
2. Wait for Cluster Install Completion
3. Wait for DU Profile Completion
4. Report Card / Graphing

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
