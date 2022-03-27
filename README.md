# sno-deploy-load

Tool to load ACM with SNO deployments either via manifests or via Zero Touch Provisioning (ZTP)

## Load/Rate Options

* interval - Deploys X number of SNOs per interval time period
* (Not implemented yet) status - Deploys X number of SNOs until all complete or fail, then repeats until all SNOs completed/failed or end of index
* (Not implemented yet) concurrent - Attempts to keep X number of SNOs deploying until no more available SNOs to keep concurrency rate

## Phases of the Workload

1. Deploy Phase - Apply Manifests or gitops to deploy SNOs
2. Wait for SNO Install Completion
3. Wait for DU Profile Completion
4. Report Card / Graphing
