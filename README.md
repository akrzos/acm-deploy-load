# sno-deploy-load

Tool to load ACM with SNO deployments either via manifests or via Zero Touch Provisioning (ZTP)

## Load/Rate Options

* interval - Deploys X number of SNOs per interval time period
* status - Deploys X number of SNOs until all complete or fail, then repeats until all SNOs completed/failed or end of index
* concurrent - Attempts to keep X number of SNOs deploying until no more available SNOs to keep concurrency rate
