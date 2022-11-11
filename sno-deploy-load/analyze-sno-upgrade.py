#!/usr/bin/env python3
#  Copyright 2022 Red Hat
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import argparse
from collections import OrderedDict
from datetime import datetime
import json
from utils.command import command
import logging
import numpy as np
import sys
import time


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("analyze-sno-upgrade")
logging.Formatter.converter = time.gmtime

default_operator_csvs = [
  "local-storage-operator.4.11.0-202210251429",
  "cluster-logging.5.5.3",
  "ptp-operator.4.11.0-202210250857",
  "sriov-network-operator.4.11.0-202210250857"
]


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Analyze SNO clusters after ZTP upgrade",
      prog="analyze-sno-upgrade.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("-m", "--sno-manifests", type=str, default="/root/hv-vm/sno/manifests",
                      help="The location of the SNO manifests, where kubeconfig is nested under each SNO directory")

  parser.add_argument("-p", "--platform-upgrade", type=str, default="4.11.5",
                      help="The version clusters are expected to have upgraded to")

  parser.add_argument("-o", "--operator-csvs", nargs="*", default=default_operator_csvs,
                      help="The expected operator CSVs to be installed/upgraded to")

  parser.add_argument("results_directory", type=str, help="The location to place analyzed data")
  parser.add_argument("-d", "--debug", action="store_true", default=False, help="Set log level debug")
  cliargs = parser.parse_args()

  if cliargs.debug:
    logger.setLevel(logging.DEBUG)

  logger.info("Analyze sno-upgrade")
  logger.info("Checking if clusters upgraded to {}".format(cliargs.platform_upgrade))
  logger.info("Checking if clusters have operator csvs {}".format(", ".join(cliargs.operator_csvs)))
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")
  # cv_csv_file = "{}/sno-clusterversion-{}.csv".format(cliargs.results_directory, ts)
  # cv_stats_file = "{}/sno-clusterversion-{}.stats".format(cliargs.results_directory, ts)

  cgus = OrderedDict()

  oc_cmd = ["oc", "get", "clustergroupupgrade", "-n", "ztp-platform-upgrade", "-o", "json"]
  rc, output = command(oc_cmd, False, retries=3, no_log=True)
  if rc != 0:
    logger.error("analyze-sno-upgrade, oc get clustergroupupgrade rc: {}".format(rc))
    sys.exit(1)
  cgu_data = json.loads(output)

  # REMOVE after logic finished
  escape = False
  # END REMOVE after logic finished

  for item in cgu_data["items"]:
    cgu_name = item["metadata"]["name"]
    cgu_creation_ts = item["metadata"]["creationTimestamp"]
    cgu_started_at = item["status"]["status"]["startedAt"]
    cgu_cluster_batches = item["status"]["remediationPlan"]

    cgus[cgu_name] = {}
    # cgus[cgu_name]["creationTimestamp"] = cgu_creation_ts
    # cgus[cgu_name]["startedAt"] = cgu_started_at
    cgus[cgu_name]["creationTimestamp"] = datetime.strptime(cgu_creation_ts, "%Y-%m-%dT%H:%M:%SZ")
    cgus[cgu_name]["startedAt"] = datetime.strptime(cgu_started_at, "%Y-%m-%dT%H:%M:%SZ")

    cgus[cgu_name]["batches"] = []
    for idx, batch in enumerate(cgu_cluster_batches):
      logger.info("Batch Index: {}".format(idx))
      cgus[cgu_name]["batches"].append({})
      cgus[cgu_name]["batches"][idx]["clusters"] = batch
      cgus[cgu_name]["batches"][idx]["partial"] = []
      cgus[cgu_name]["batches"][idx]["nonattempt"] = []
      cgus[cgu_name]["batches"][idx]["unreachable"] = []
      cgus[cgu_name]["batches"][idx]["completed"] = []
      cgus[cgu_name]["batches"][idx]["startTS"] = ""
      cgus[cgu_name]["batches"][idx]["platformEndTS"] = ""
      cgus[cgu_name]["batches"][idx]["operatorEndTS"] = ""
      cgus[cgu_name]["batches"][idx]["operator_completed"] = []
      cgus[cgu_name]["batches"][idx]["operator_incomplete"] = []

      # Gather per cluster data in a specific batch
      for cluster in batch:
        logger.info("Cluster: {}".format(cluster))
        kubeconfig = "{}/{}/kubeconfig".format(cliargs.sno_manifests, cluster)

        # REMOVE after logic finished
        # if cluster == "sno00002" or cluster == "sno01011" or cluster == "sno02029":
        # if cluster == "sno00010" or cluster == "sno01020" or cluster == "sno02040":
        # if cluster == "sno00005" or cluster == "sno01015":
        #   escape = True
        #   logger.warn("Escaping because we made it to cluster (sno00010, sno01020, sno02040)")
        #   break
        # END REMOVE after logic finished

        oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "clusterversion", "version", "-o", "json"]
        rc, output = command(oc_cmd, False, retries=2, no_log=True)
        if rc != 0:
          logger.error("analyze-sno-upgrade, oc get clusterversion rc: {}".format(rc))
          logger.info("Recording {} as an unreachable cluster".format(cluster))
          cgus[cgu_name]["batches"][idx]["unreachable"].append(cluster)
        cv_data = json.loads(output)

        found_correct_platform_upgrade = False

        for ver_hist_entry in cv_data["status"]["history"]:
          cv_version = ver_hist_entry["version"]
          cv_state = ver_hist_entry["state"]
          cv_startedtime = datetime.strptime(ver_hist_entry["startedTime"], "%Y-%m-%dT%H:%M:%SZ")
          cv_completiontime = ""
          if cv_version == cliargs.platform_upgrade:
            logger.debug("Cluster attempted upgrade to correct platform")
            if found_correct_platform_upgrade:
              logger.error("Found duplicate clusterversion entry")
              sys.exit(1)
            found_correct_platform_upgrade = True

            logger.debug("Comparing batch startTS: '{}' Cluster: '{}'".format(cgus[cgu_name]["batches"][idx]["startTS"], cv_startedtime))
            if cgus[cgu_name]["batches"][idx]["startTS"] == "":
              logger.debug("Recording intial batch startTS: '{}'".format(cv_startedtime))
              cgus[cgu_name]["batches"][idx]["startTS"] = cv_startedtime
            else:
              if cgus[cgu_name]["batches"][idx]["startTS"] > cv_startedtime:
                logger.debug("Identified earlier batch startTS: '{}'".format(cv_startedtime))
                cgus[cgu_name]["batches"][idx]["startTS"] = cv_startedtime

            if cv_state == "Partial":
              logger.info("Cluster with Partial Upgrade Found")
              cgus[cgu_name]["batches"][idx]["partial"].append(cluster)
            if cv_state == "Completed":
              logger.info("Cluster with Completed Upgrade Found")
              cgus[cgu_name]["batches"][idx]["completed"].append(cluster)
              cv_completiontime = datetime.strptime(ver_hist_entry["completionTime"], "%Y-%m-%dT%H:%M:%SZ")

              logger.debug("Comparing batch platformEndTS: '{}' Cluster: '{}'".format(cgus[cgu_name]["batches"][idx]["platformEndTS"], cv_completiontime))
              if cgus[cgu_name]["batches"][idx]["platformEndTS"] == "":
                logger.debug("Recording intial batch platformEndTS: '{}'".format(cv_completiontime))
                cgus[cgu_name]["batches"][idx]["platformEndTS"] = cv_completiontime
              else:
                if cgus[cgu_name]["batches"][idx]["platformEndTS"] < cv_completiontime:
                  logger.debug("Identified later batch platformEndTS: '{}'".format(cv_completiontime))
                  cgus[cgu_name]["batches"][idx]["platformEndTS"] = cv_completiontime

        if not found_correct_platform_upgrade:
          logger.info("Recording {} as an nonattempt cluster".format(cluster))
          cgus[cgu_name]["batches"][idx]["nonattempt"].append(cluster)
          # On nonattempt clusters, do not check operator csvs since the platform never upgraded anyhow
        else:

          oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "clusterserviceversions", "-A", "-o", "json"]
          rc, output = command(oc_cmd, False, retries=2, no_log=True)
          if rc != 0:
            logger.error("analyze-sno-upgrade, oc get clusterserviceversions rc: {}".format(rc))
          else:
            csv_data = json.loads(output)
            operator_found = False
            for operator in cliargs.operator_csvs:
              operator_found = False
              logger.info("Checking if operator {} is installed".format(operator))
              for item in csv_data["items"]:
                if item["metadata"]["name"] == operator and item["status"]["phase"] == "Succeeded":
                  operator_found = True
                  operator_installed_ts = datetime.strptime(item["status"]["lastUpdateTime"], "%Y-%m-%dT%H:%M:%SZ")
                  logger.info("Operator was installed by: '{}'".format(operator_installed_ts))

                  logger.debug("Comparing batch operatorEndTS: '{}' Operator: '{}'".format(cgus[cgu_name]["batches"][idx]["operatorEndTS"], operator_installed_ts))
                  if cgus[cgu_name]["batches"][idx]["operatorEndTS"] == "":
                    logger.debug("Recording intial batch operatorEndTS: '{}'".format(operator_installed_ts))
                    cgus[cgu_name]["batches"][idx]["operatorEndTS"] = operator_installed_ts
                  else:
                    if cgus[cgu_name]["batches"][idx]["operatorEndTS"] < operator_installed_ts:
                      logger.debug("Identified later batch operatorEndTS: '{}'".format(operator_installed_ts))
                      cgus[cgu_name]["batches"][idx]["operatorEndTS"] = operator_installed_ts

                  break;
              if not operator_found:
                logger.error("Cluster: {} failed to have Operator CSV: {} installed with phase Succeeded".format(cluster, operator))
                # Don't bother checking the rest of the operators, the cluster already failed on an operator
                break;
            if operator_found:
              cgus[cgu_name]["batches"][idx]["operator_completed"].append(cluster)
            else:
              cgus[cgu_name]["batches"][idx]["operator_incomplete"].append(cluster)


  # Display captured data:
  for cgu_name in cgus:
    logger.info("##########################################################################################")
    logger.info("Collected Data for CGU: {}".format(cgu_name))
    logger.info("CGU creationTimestamp: {}".format(cgus[cgu_name]["creationTimestamp"]))
    logger.info("CGU startedAt: {}".format(cgus[cgu_name]["startedAt"]))
    logger.info("Cluster Upgrade Batches: {}".format(len(cgus[cgu_name]["batches"])))
    for idx, batch in enumerate(cgus[cgu_name]["batches"]):
      logger.info("#############################################")
      logger.info("Data from Batch {}".format(idx))
      logger.info("Total Clusters: {}".format(len(cgus[cgu_name]["batches"][idx]["clusters"])))
      logger.info("Platform completed: {}".format(len(cgus[cgu_name]["batches"][idx]["completed"])))
      logger.info("Platform partial: {}".format(len(cgus[cgu_name]["batches"][idx]["partial"])))
      logger.info("Platform nonattempt: {}".format(len(cgus[cgu_name]["batches"][idx]["nonattempt"])))
      logger.info("Platform unreachable: {}".format(len(cgus[cgu_name]["batches"][idx]["unreachable"])))
      logger.info("Operator completed: {}".format(len(cgus[cgu_name]["batches"][idx]["operator_completed"])))
      logger.info("Operator incomplete: {}".format(len(cgus[cgu_name]["batches"][idx]["operator_incomplete"])))
      logger.info("Earliest platform start timestamp: {}".format(cgus[cgu_name]["batches"][idx]["startTS"]))
      logger.info("Latest platform end timestamp: {}".format(cgus[cgu_name]["batches"][idx]["platformEndTS"]))
      logger.info("Latest operator end timestamp: {}".format(cgus[cgu_name]["batches"][idx]["operatorEndTS"]))
      # Show Durations: platform time, platform to oETS, cgu to pETS, cgu to oETS

  # Determine time to complete ztp-upgrade of a cluster (Stats)
  # Determine time to complete an upgrade on a batch of SNOs
  # Determine time to complete an upgrade for the whole CGU

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))


if __name__ == "__main__":
  sys.exit(main())
