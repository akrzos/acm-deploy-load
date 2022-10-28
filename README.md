# sno-deploy-load

Tool to load ACM with SNO deployments either via manifests or via Zero Touch Provisioning (ZTP) and scripts to help analyze data afterwards.

## Load/Rate Option

* interval - Deploys X number of SNOs (manifests or GitOps ZTP) per Y interval time period

## Phases of the Workload

1. Deploy Phase - Apply Manifests or GitOps ZTP to deploy SNOs
2. Wait for SNO Install Completion
3. Wait for DU Profile Completion
4. Report Card / Graphing
