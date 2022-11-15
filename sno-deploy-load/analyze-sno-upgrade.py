#!/usr/bin/env python3
#
# Analyze "Upgrade" ClusterGroupUpgrades data on a hub cluster, clusterversion and clusterserviceversion data from the
# SNOs to determine success/failure and timings of platform+operator upgrades of SNOs
#
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
from datetime import timedelta
import json
from utils.command import command
import logging
import numpy as np
from pathlib import Path
import sys
import time


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("analyze-sno-upgrade")
logging.Formatter.converter = time.gmtime

default_operator_csvs = [
  "local-storage-operator.4.11.0-202210251429",
  # For reasons unknown, cluster-logging csv shows a status.lastUpdateTime much beyond the time expected
  # "cluster-logging.5.5.3",
  "ptp-operator.4.11.0-202210250857",
  "sriov-network-operator.4.11.0-202210250857"
]


# TODO:
# * CGU Percentage of success/failure
# * Batch duration time (Success time, not include failure since that would just be the timeout)
# * Report Card File (Stats)
# * Determine Stats timing to complete ztp-upgrade of batch of clusters, cgu of clusters


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
  parser.add_argument("--offline-process", action="store_true", default=False, help="Uses previously stored raw data")
  parser.add_argument("-d", "--debug", action="store_true", default=False, help="Set log level debug")
  cliargs = parser.parse_args()

  if cliargs.debug:
    logger.setLevel(logging.DEBUG)

  logger.info("Analyze sno-upgrade")
  logger.info("Checking if clusters upgraded to {}".format(cliargs.platform_upgrade))
  logger.info("Checking if clusters have operator csvs {}".format(", ".join(cliargs.operator_csvs)))
  raw_data_dir = "{}/sno-upgrade".format(cliargs.results_directory)
  Path(raw_data_dir).mkdir(parents=True, exist_ok=True)
  if cliargs.offline_process:
    logger.info("Reading raw data from: {}".format(raw_data_dir))
  else:
    logger.info("Storing raw data in: {}".format(raw_data_dir))
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")
  upgrade_csv_file = "{}/sno-upgrade-{}.csv".format(cliargs.results_directory, ts)
  upgrade_stats_file = "{}/sno-upgrade-{}.stats".format(cliargs.results_directory, ts)

  logger.info("Writing CSV: {}".format(upgrade_csv_file))
  with open(upgrade_csv_file, "w") as csv_file:
    csv_file.write("cgu,batch,name,state,platform_startedTime,platform_completionTime,platform_duration,operator_lastUpdateTime,upgrade_duration\n")

  csv_cluster_state = ""
  csv_platform_started_time = ""
  csv_platform_completion_time = ""
  csv_platform_duration = ""
  csv_operator_last_update_time = ""
  csv_upgrade_duration = ""

  cgus = OrderedDict()

  if not cliargs.offline_process:
    oc_cmd = ["oc", "get", "clustergroupupgrade", "-n", "ztp-platform-upgrade", "-o", "json"]
    rc, output = command(oc_cmd, False, retries=3, no_log=True)
    if rc != 0:
      logger.error("analyze-sno-upgrade, oc get clustergroupupgrade rc: {}".format(rc))
      sys.exit(1)
    with open("{}/cgus.json".format(raw_data_dir), "w") as cgu_data_file:
      cgu_data_file.write(output)

  with open("{}/cgus.json".format(raw_data_dir), "r") as cgu_data_file:
    cgu_data = json.load(cgu_data_file)

  for item in cgu_data["items"]:
    cgu_name = item["metadata"]["name"]
    cgu_creation_ts = item["metadata"]["creationTimestamp"]
    cgu_started_at = item["status"]["status"]["startedAt"]
    cgu_cluster_batches = item["status"]["remediationPlan"]

    cgus[cgu_name] = {}
    cgus[cgu_name]["creationTimestamp"] = datetime.strptime(cgu_creation_ts, "%Y-%m-%dT%H:%M:%SZ")
    cgus[cgu_name]["startedAt"] = datetime.strptime(cgu_started_at, "%Y-%m-%dT%H:%M:%SZ")

    cgus[cgu_name]["batches"] = []
    for batch_index, batch in enumerate(cgu_cluster_batches):
      logger.info("Batch Index: {}".format(batch_index))
      cgus[cgu_name]["batches"].append({})
      cgus[cgu_name]["batches"][batch_index]["clusters"] = batch
      cgus[cgu_name]["batches"][batch_index]["partial"] = []
      cgus[cgu_name]["batches"][batch_index]["nonattempt"] = []
      cgus[cgu_name]["batches"][batch_index]["unreachable"] = []
      cgus[cgu_name]["batches"][batch_index]["completed"] = []
      cgus[cgu_name]["batches"][batch_index]["startTS"] = ""
      cgus[cgu_name]["batches"][batch_index]["platformEndTS"] = ""
      cgus[cgu_name]["batches"][batch_index]["operatorEndTS"] = ""
      cgus[cgu_name]["batches"][batch_index]["operator_completed"] = []
      cgus[cgu_name]["batches"][batch_index]["operator_incomplete"] = []

      # Gather per cluster data in a specific batch
      for cluster in batch:
        logger.info("Cluster: {}".format(cluster))
        csv_cluster_state = ""
        csv_platform_started_time = ""
        csv_platform_completion_time = ""
        csv_platform_duration = ""
        csv_operator_last_update_time = ""
        csv_upgrade_duration = ""
        kubeconfig = "{}/{}/kubeconfig".format(cliargs.sno_manifests, cluster)

        if not cliargs.offline_process:
          oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "clusterversion", "version", "-o", "json"]
          rc, output = command(oc_cmd, False, retries=2, no_log=True)
          if rc != 0:
            logger.error("analyze-sno-upgrade, oc get clusterversion rc: {}".format(rc))
            output = ""
          with open("{}/{}-cv.json".format(raw_data_dir, cluster), "w") as cv_data_file:
            cv_data_file.write(output)

        with open("{}/{}-cv.json".format(raw_data_dir, cluster), "r") as cv_data_file:
          cv_data = json.load(cv_data_file)

        if cv_data == "":
          logger.info("Recording {} as an unreachable cluster".format(cluster))
          csv_cluster_state = "unreachable"
          cgus[cgu_name]["batches"][batch_index]["unreachable"].append(cluster)

        found_correct_platform_upgrade = False

        for ver_hist_entry in cv_data["status"]["history"]:
          cv_version = ver_hist_entry["version"]
          cv_state = ver_hist_entry["state"]
          cv_startedtime = datetime.strptime(ver_hist_entry["startedTime"], "%Y-%m-%dT%H:%M:%SZ")
          cv_completiontime = ""
          if cv_version == cliargs.platform_upgrade:
            logger.debug("Cluster attempted upgrade to correct platform")
            csv_cluster_state = ver_hist_entry["state"]
            csv_platform_started_time = ver_hist_entry["startedTime"]
            if found_correct_platform_upgrade:
              logger.error("Found duplicate clusterversion entry")
              sys.exit(1)
            found_correct_platform_upgrade = True

            logger.debug("Comparing batch startTS: '{}' Cluster: '{}'".format(cgus[cgu_name]["batches"][batch_index]["startTS"], cv_startedtime))
            if cgus[cgu_name]["batches"][batch_index]["startTS"] == "":
              logger.debug("Recording intial batch startTS: '{}'".format(cv_startedtime))
              cgus[cgu_name]["batches"][batch_index]["startTS"] = cv_startedtime
            else:
              if cgus[cgu_name]["batches"][batch_index]["startTS"] > cv_startedtime:
                logger.debug("Identified earlier batch startTS: '{}'".format(cv_startedtime))
                cgus[cgu_name]["batches"][batch_index]["startTS"] = cv_startedtime

            if cv_state == "Partial":
              logger.info("Cluster with Partial Upgrade Found")
              cgus[cgu_name]["batches"][batch_index]["partial"].append(cluster)
            if cv_state == "Completed":
              logger.info("Cluster with Completed Upgrade Found")
              cgus[cgu_name]["batches"][batch_index]["completed"].append(cluster)
              cv_completiontime = datetime.strptime(ver_hist_entry["completionTime"], "%Y-%m-%dT%H:%M:%SZ")
              csv_platform_completion_time = ver_hist_entry["completionTime"]
              csv_platform_duration = (cv_completiontime - cv_startedtime).total_seconds()

              logger.debug("Comparing batch platformEndTS: '{}' Cluster: '{}'".format(cgus[cgu_name]["batches"][batch_index]["platformEndTS"], cv_completiontime))
              if cgus[cgu_name]["batches"][batch_index]["platformEndTS"] == "":
                logger.debug("Recording intial batch platformEndTS: '{}'".format(cv_completiontime))
                cgus[cgu_name]["batches"][batch_index]["platformEndTS"] = cv_completiontime
              else:
                if cgus[cgu_name]["batches"][batch_index]["platformEndTS"] < cv_completiontime:
                  logger.debug("Identified later batch platformEndTS: '{}'".format(cv_completiontime))
                  cgus[cgu_name]["batches"][batch_index]["platformEndTS"] = cv_completiontime

        if not found_correct_platform_upgrade:
          logger.info("Recording {} as an nonattempt cluster".format(cluster))
          cgus[cgu_name]["batches"][batch_index]["nonattempt"].append(cluster)
          csv_cluster_state = "nonattempt"
          # On nonattempt clusters, do not check operator csvs since the platform never upgraded anyhow
        else:

          if not cliargs.offline_process:
            oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "clusterserviceversions", "-A", "-o", "json"]
            rc, output = command(oc_cmd, False, retries=2, no_log=True)
            if rc != 0:
              logger.error("analyze-sno-upgrade, oc get clusterserviceversions rc: {}".format(rc))
              output = ""
            with open("{}/{}-csv.json".format(raw_data_dir, cluster), "w") as csv_data_file:
              csv_data_file.write(output)

          with open("{}/{}-csv.json".format(raw_data_dir, cluster), "r") as csv_data_file:
            csv_data = json.load(csv_data_file)

          if csv_data == "":
            logger.warn("No csv data found")
          else:
            for operator in cliargs.operator_csvs:
              operator_found = False
              logger.info("Checking if operator {} is installed".format(operator))
              for item in csv_data["items"]:
                if item["metadata"]["name"] == operator and item["status"]["phase"] == "Succeeded":
                  operator_found = True
                  operator_installed_ts = datetime.strptime(item["status"]["lastUpdateTime"], "%Y-%m-%dT%H:%M:%SZ")
                  logger.info("Operator was installed by: '{}'".format(operator_installed_ts))

                  logger.debug("Comparing batch operatorEndTS: '{}' Operator: '{}'".format(cgus[cgu_name]["batches"][batch_index]["operatorEndTS"], operator_installed_ts))
                  if cgus[cgu_name]["batches"][batch_index]["operatorEndTS"] == "":
                    logger.debug("Recording intial batch operatorEndTS: '{}'".format(operator_installed_ts))
                    cgus[cgu_name]["batches"][batch_index]["operatorEndTS"] = operator_installed_ts
                  else:
                    if cgus[cgu_name]["batches"][batch_index]["operatorEndTS"] < operator_installed_ts:
                      logger.debug("Identified later batch operatorEndTS: '{}'".format(operator_installed_ts))
                      cgus[cgu_name]["batches"][batch_index]["operatorEndTS"] = operator_installed_ts

                  if csv_operator_last_update_time == "":
                    csv_operator_last_update_time = item["status"]["lastUpdateTime"]
                  else:
                    if datetime.strptime(csv_operator_last_update_time, "%Y-%m-%dT%H:%M:%SZ") < operator_installed_ts:
                      csv_operator_last_update_time = item["status"]["lastUpdateTime"]

                  break;
              if not operator_found:
                logger.error("Cluster: {} failed to have Operator CSV: {} installed with phase Succeeded".format(cluster, operator))
                # Don't bother checking the rest of the operators, the cluster already failed on an operator
                break;
            if operator_found:
              cgus[cgu_name]["batches"][batch_index]["operator_completed"].append(cluster)
              csv_upgrade_duration = (datetime.strptime(csv_operator_last_update_time, "%Y-%m-%dT%H:%M:%SZ") - datetime.strptime(csv_platform_started_time, "%Y-%m-%dT%H:%M:%SZ")).total_seconds()
            else:
              cgus[cgu_name]["batches"][batch_index]["operator_incomplete"].append(cluster)
              csv_operator_last_update_time = ""

        with open(upgrade_csv_file, "a") as csv_file:
          csv_file.write("{},{},{},{},{},{},{},{},{}\n".format(
            cgu_name, batch_index, cluster, csv_cluster_state, csv_platform_started_time, csv_platform_completion_time,
            csv_platform_duration, csv_operator_last_update_time, csv_upgrade_duration))

  # Produce the report card on the upgrade CGU and batches
  for cgu_name in cgus:
    logger.info("##########################################################################################")
    logger.info("Collected Data for CGU: {}".format(cgu_name))
    logger.info("CGU creationTimestamp: {}".format(cgus[cgu_name]["creationTimestamp"]))
    logger.info("CGU startedAt: {}".format(cgus[cgu_name]["startedAt"]))
    logger.info("Cluster Upgrade Batches: {}".format(len(cgus[cgu_name]["batches"])))
    for batch_index, batch in enumerate(cgus[cgu_name]["batches"]):
      if cgus[cgu_name]["batches"][batch_index]["platformEndTS"] != "":
        platform_duration = (cgus[cgu_name]["batches"][batch_index]["platformEndTS"] - cgus[cgu_name]["batches"][batch_index]["startTS"]).total_seconds()
        platform_duration_h = str(timedelta(seconds=platform_duration))
      else:
        platform_duration = "NA"
        platform_duration_h = ""
      if cgus[cgu_name]["batches"][batch_index]["operatorEndTS"] != "":
        upgrade_duration = (cgus[cgu_name]["batches"][batch_index]["operatorEndTS"] - cgus[cgu_name]["batches"][batch_index]["startTS"]).total_seconds()
        upgrade_duration_h = str(timedelta(seconds=upgrade_duration))
      else:
        upgrade_duration = "NA"
        upgrade_duration_h = ""
      total_clusters = len(cgus[cgu_name]["batches"][batch_index]["clusters"])
      platform_completed = len(cgus[cgu_name]["batches"][batch_index]["completed"])
      platform_partial = len(cgus[cgu_name]["batches"][batch_index]["partial"])
      platform_nonattempt = len(cgus[cgu_name]["batches"][batch_index]["nonattempt"])
      platform_unreachable = len(cgus[cgu_name]["batches"][batch_index]["unreachable"])
      operator_completed = len(cgus[cgu_name]["batches"][batch_index]["operator_completed"])
      operator_incomplete = len(cgus[cgu_name]["batches"][batch_index]["operator_incomplete"])
      plat_c_percent = round((platform_completed / total_clusters) * 100, 1)
      plat_p_percent = round((platform_partial / total_clusters) * 100, 1)
      plat_n_percent = round((platform_nonattempt / total_clusters) * 100, 1)
      plat_u_percent = round((platform_unreachable / total_clusters) * 100, 1)
      oper_c_percent = round((operator_completed / total_clusters) * 100, 1)
      oper_i_percent = round((operator_incomplete / total_clusters) * 100, 1)
      logger.info("#############################################")
      logger.info("Data from Batch {}".format(batch_index))
      logger.info("Cluster Start: {}".format(cgus[cgu_name]["batches"][batch_index]["clusters"][0]))
      logger.info("Cluster End: {}".format(cgus[cgu_name]["batches"][batch_index]["clusters"][-1]))
      logger.info("Total Clusters: {}".format(total_clusters))
      logger.info("Platform completed: {} :: {}%".format(platform_completed, plat_c_percent))
      logger.info("Platform partial: {} :: {}%".format(platform_partial, plat_p_percent))
      logger.info("Platform nonattempt: {} :: {}%".format(platform_nonattempt, plat_n_percent))
      logger.info("Platform unreachable: {} :: {}%".format(platform_unreachable, plat_u_percent))
      logger.info("Operator completed: {} :: {}%".format(operator_completed, oper_c_percent))
      logger.info("Operator incomplete: {} :: {}%".format(operator_incomplete, oper_i_percent))
      logger.info("Earliest platform start timestamp: {}".format(cgus[cgu_name]["batches"][batch_index]["startTS"]))
      logger.info("Latest platform end timestamp: {}".format(cgus[cgu_name]["batches"][batch_index]["platformEndTS"]))
      logger.info("Latest operator end timestamp: {}".format(cgus[cgu_name]["batches"][batch_index]["operatorEndTS"]))
      logger.info("Platform Duration(platformEndTS - startTS): {}s :: {}".format(platform_duration, platform_duration_h))
      logger.info("Upgrade Duration(operatorEndTS - startTS): {}s :: {}".format(upgrade_duration, upgrade_duration_h))

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))


if __name__ == "__main__":
  sys.exit(main())
