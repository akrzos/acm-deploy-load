# sno-deploy-load

Tools and scripts to load and analyze ACM with SNO deployments and upgrades. SNOs are deployed via manifests or GitOps
using Zero Touch Provisioning (ZTP).

## Workload Script

### sno-deploy-load.py

Tool to load ACM with SNO deployments via manifests or GitOps ZTP

Load/Rate Option

* interval - Deploys X number of SNOs (manifests or GitOps ZTP) per Y interval time period

Phases of the Workload

1. Deploy Phase - Apply Manifests or GitOps ZTP to deploy SNOs
2. Wait for SNO Install Completion
3. Wait for DU Profile Completion
4. Report Card / Graphing

## Analysis Scripts

Analysis scripts can be run after deploying or upgrading SNOs to understand success and performance of the system.

* analyze-agentclusterinstalls.py - Summarize and report count, min/avg/max, and 50/95/99 percentiles for SNO
installation timing
* analyze-clustergroupupgrades.py - Summarize and report count, min/avg/max, and 50/95/99 percentiles for ztp-install
clustergroupupgrade custom resources
* analyze-sno-deploy-time.py - Determine deployment duration metrics and peak concurrencies from sno-deploy-load
monitoring data
* analyze-sno-upgrade.py - Summarize platform and operator upgrade success and timings from CGUs across upgraded SNOs
* analyze-sno-clusterversion.py - Summarizes cluster upgrade success and timing as observed from the SNO's
clusterversion resource and generates Time-series csv of upgrades to be consumed by graphing script

## Graphing Scripts

* graph-sno-clusterversion.py - Graph time-series csv from analyze-sno-clusterversion script
* graph-sno-deploy.py - Graph monitor_data.csv from sno-deploy-load.py
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
