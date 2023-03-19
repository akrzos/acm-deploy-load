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
* analyze-sno-upgrade.py - Summarize platform and operator upgrade success and timings from CGUs across upgraded SNOs
* analyze-sno-clusterversion.py - Summarizes cluster upgrade success and timing as observed from the SNO's
clusterversion resource and generates Time-series csv of upgrades to be consumed by graphing script

## Graphing Scripts

* graph-sno-clusterversion.py - Graph time-series csv from analyze-sno-clusterversion script
* graph-acm-deploy.py - Graph monitor_data.csv from acm-deploy-load.py
* graph-sno-upgrade.py - Graph time series csv from analyze-sno-upgrade script

## Patch Scripts

Located in the [acm directory](acm), and provide memory limits tuning or image patches specific to scale tests for specific
versions

## Other Scripts

* cluster-health.py - Check if a cluster is healthy/stable
  * Check if clusterversion is available
  * Check if all clusteroperators available
  * Check if all nodes are ready
  * Check if all machineconfigpools updated
  * Check for etcd leader elections in the last hour
