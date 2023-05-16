#!/usr/bin/env python3
#
# Analyze "Upgrade" ClusterGroupUpgrades data on a hub cluster, clusterversion and clusterserviceversion data from the
# deployed clusters to determine success/failure and timings of platform+operator upgrades of deployed clusters
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
import logging
import numpy as np
import os
from pathlib import Path
import sys
import time
from utils.command import command
from utils.output import log_write


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime

# Latest defaults (5/9/2023)
default_operator_csvs = [
  "local-storage-operator.v4.12.0-202304190215",
  # For reasons unknown, cluster-logging csv shows a status.lastUpdateTime much beyond the time expected
  # "cluster-logging.v5.6.1",
  "ptp-operator.4.12.0-202304211142",
  "sriov-network-operator.v4.12.0-202304190215"
]

# TODO:
# * Only check platform
# * Operator start timestamp per cluster
#   * creationTimestamp is "too quick", will require installplan data

def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Analyze clusters after ZTP upgrade",
      prog="analyze-upgrade.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("-k", "--kubeconfigs", type=str, default="/root/hv-vm/kc",
                      help="The location of the kubeconfigs, nested under each cluster's directory")

  parser.add_argument("-p", "--platform-upgrade", type=str, default="4.12.16",
                      help="The version clusters are expected to have upgraded to")

  parser.add_argument("-o", "--operator-csvs", nargs="*", default=default_operator_csvs,
                      help="The expected operator CSVs to be installed/upgraded to")

  parser.add_argument("results_directory", type=str, help="The location to place analyzed data")
  parser.add_argument("--offline-process", action="store_true", default=False, help="Uses previously stored raw data")
  parser.add_argument("-s", "--display-summary", action="store_true", default=False, help="Display summerized data")
  parser.add_argument("-b", "--display-batch", action="store_true", default=False, help="Display CGU batch data")
  parser.add_argument("-d", "--debug", action="store_true", default=False, help="Set log level debug")
  cliargs = parser.parse_args()

  if cliargs.debug:
    logger.setLevel(logging.DEBUG)

  logger.info("Analyze upgrades")
  logger.info("Checking if clusters upgraded to {}".format(cliargs.platform_upgrade))
  logger.info("Checking if clusters have operator csvs {}".format(", ".join(cliargs.operator_csvs)))
  raw_data_dir = "{}/upgrade".format(cliargs.results_directory)
  Path(raw_data_dir).mkdir(parents=True, exist_ok=True)
  if cliargs.offline_process:
    logger.info("Reading raw data from: {}".format(raw_data_dir))
  else:
    logger.info("Storing raw data in: {}".format(raw_data_dir))
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")
  upgrade_csv_file = "{}/upgrade-{}.csv".format(cliargs.results_directory, ts)
  upgrade_stats_file = "{}/upgrade-{}.stats".format(cliargs.results_directory, ts)

  logger.info("Writing CSV: {}".format(upgrade_csv_file))
  with open(upgrade_csv_file, "w") as csv_file:
    csv_file.write("cgu,batch,name,state,platform_startedTime,platform_completionTime,platform_duration,operator_creationTimestamp,operator_lastUpdateTime,operator_duration,upgrade_duration\n")

  cgus = OrderedDict()

  if not cliargs.offline_process:
    oc_cmd = ["oc", "get", "clustergroupupgrade", "-n", "ztp-platform-upgrade", "-o", "json"]
    rc, output = command(oc_cmd, False, retries=3, no_log=True)
    if rc != 0:
      logger.error("analyze-upgrade, oc get clustergroupupgrade rc: {}".format(rc))
      sys.exit(1)
    with open("{}/cgus.json".format(raw_data_dir), "w") as cgu_data_file:
      cgu_data_file.write(output)

  with open("{}/cgus.json".format(raw_data_dir), "r") as cgu_data_file:
    cgu_data = json.load(cgu_data_file)

  for item in cgu_data["items"]:
    cgu_name = item["metadata"]["name"]
    cgu_creation_ts = item["metadata"]["creationTimestamp"]
    if "startedAt" in item["status"]["status"]:
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
        cgus[cgu_name]["batches"][batch_index]["completed"] = []
        cgus[cgu_name]["batches"][batch_index]["partial"] = []
        cgus[cgu_name]["batches"][batch_index]["nonattempt"] = []
        cgus[cgu_name]["batches"][batch_index]["unreachable"] = []
        cgus[cgu_name]["batches"][batch_index]["operator_completed"] = []
        cgus[cgu_name]["batches"][batch_index]["operator_incomplete"] = []
        cgus[cgu_name]["batches"][batch_index]["startTS"] = ""
        cgus[cgu_name]["batches"][batch_index]["platformEndTS"] = ""
        cgus[cgu_name]["batches"][batch_index]["operatorEndTS"] = ""
        cgus[cgu_name]["batches"][batch_index]["pc_durations"] = []
        cgus[cgu_name]["batches"][batch_index]["oc_durations"] = []
        cgus[cgu_name]["batches"][batch_index]["upgrade_durations"] = []

        # Gather per cluster data in a specific batch
        for cluster in batch:
          logger.info("Cluster: {}".format(cluster))
          csv_cluster_state = ""
          csv_platform_started_time = ""
          csv_platform_completion_time = ""
          csv_platform_duration = ""
          csv_operator_creation_timestamp = ""
          csv_operator_last_update_time = ""
          csv_operator_duration = ""
          csv_upgrade_duration = ""
          kubeconfig = "{}/{}/kubeconfig".format(cliargs.kubeconfigs, cluster)

          if not cliargs.offline_process:
            oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "clusterversion", "version", "-o", "json"]
            rc, output = command(oc_cmd, False, retries=2, no_log=True)
            if rc != 0:
              logger.error("analyze-upgrade, oc get clusterversion rc: {}".format(rc))
              output = ""
            with open("{}/{}-cv.json".format(raw_data_dir, cluster), "w") as cv_data_file:
              cv_data_file.write(output)

          if os.stat("{}/{}-cv.json".format(raw_data_dir, cluster)).st_size == 0:
            cv_data = ""
          else:
            with open("{}/{}-cv.json".format(raw_data_dir, cluster), "r") as cv_data_file:
              cv_data = json.load(cv_data_file)

          found_correct_platform_upgrade = False

          if cv_data == "":
            logger.info("Recording {} as an unreachable cluster".format(cluster))
            csv_cluster_state = "unreachable"
            cgus[cgu_name]["batches"][batch_index]["unreachable"].append(cluster)
          else:
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
                  cgus[cgu_name]["batches"][batch_index]["pc_durations"].append(csv_platform_duration)

                  logger.debug("Comparing batch platformEndTS: '{}' Cluster: '{}'".format(cgus[cgu_name]["batches"][batch_index]["platformEndTS"], cv_completiontime))
                  if cgus[cgu_name]["batches"][batch_index]["platformEndTS"] == "":
                    logger.debug("Recording intial batch platformEndTS: '{}'".format(cv_completiontime))
                    cgus[cgu_name]["batches"][batch_index]["platformEndTS"] = cv_completiontime
                  else:
                    if cgus[cgu_name]["batches"][batch_index]["platformEndTS"] < cv_completiontime:
                      logger.debug("Identified later batch platformEndTS: '{}'".format(cv_completiontime))
                      cgus[cgu_name]["batches"][batch_index]["platformEndTS"] = cv_completiontime

            # Cluster had completed, check operators
            if cluster in cgus[cgu_name]["batches"][batch_index]["completed"]:
              if not cliargs.offline_process:
                oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "clusterserviceversions", "-A", "-o", "json"]
                rc, output = command(oc_cmd, False, retries=2, no_log=True)
                if rc != 0:
                  logger.error("analyze-upgrade, oc get clusterserviceversions rc: {}".format(rc))
                  output = ""
                with open("{}/{}-csv.json".format(raw_data_dir, cluster), "w") as csv_data_file:
                  csv_data_file.write(output)

              if os.stat("{}/{}-csv.json".format(raw_data_dir, cluster)).st_size == 0:
                csv_data = ""
              else:
                with open("{}/{}-csv.json".format(raw_data_dir, cluster), "r") as csv_data_file:
                  csv_data = json.load(csv_data_file)

              if csv_data == "":
                logger.warn("No csv data found")
              else:
                operator_found = False
                for operator in cliargs.operator_csvs:
                  operator_found = False
                  logger.info("Checking if operator {} is installed".format(operator))
                  for item in csv_data["items"]:
                    if (item["metadata"]["name"] == operator and "status" in item) and item["status"]["phase"] == "Succeeded":
                      operator_found = True
                      operator_creation_ts = datetime.strptime(item["metadata"]["creationTimestamp"], "%Y-%m-%dT%H:%M:%SZ")
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

                      # if csv_operator_creation_timestamp == "":
                      #   csv_operator_creation_timestamp = item["metadata"]["creationTimestamp"]
                      # else:
                      #   if datetime.strptime(csv_operator_creation_timestamp, "%Y-%m-%dT%H:%M:%SZ") > operator_creation_ts:
                      #     csv_operator_creation_timestamp = item["metadata"]["creationTimestamp"]

                      if csv_operator_last_update_time == "":
                        csv_operator_last_update_time = item["status"]["lastUpdateTime"]
                      else:
                        if datetime.strptime(csv_operator_last_update_time, "%Y-%m-%dT%H:%M:%SZ") < operator_installed_ts:
                          csv_operator_last_update_time = item["status"]["lastUpdateTime"]

                      break;
                  if not operator_found:
                    logger.error("Cluster: {} failed to have Operator CSV: {} installed with phase Succeeded".format(cluster, operator))
                    cgus[cgu_name]["batches"][batch_index]["operator_incomplete"].append(cluster)
                    csv_operator_last_update_time = ""
                    # Don't bother checking the rest of the operators, the cluster already failed on an operator
                    break;
                if operator_found:
                  cgus[cgu_name]["batches"][batch_index]["operator_completed"].append(cluster)
                  # csv_operator_duration = (datetime.strptime(csv_operator_last_update_time, "%Y-%m-%dT%H:%M:%SZ") - datetime.strptime(csv_operator_creation_timestamp, "%Y-%m-%dT%H:%M:%SZ")).total_seconds()
                  csv_upgrade_duration = (datetime.strptime(csv_operator_last_update_time, "%Y-%m-%dT%H:%M:%SZ") - datetime.strptime(csv_platform_started_time, "%Y-%m-%dT%H:%M:%SZ")).total_seconds()
                  # cgus[cgu_name]["batches"][batch_index]["oc_durations"].append(csv_operator_duration)
                  cgus[cgu_name]["batches"][batch_index]["upgrade_durations"].append(csv_upgrade_duration)

            # Cluster not in completed and not in partial, cluster was never attempted
            elif cluster not in cgus[cgu_name]["batches"][batch_index]["partial"]:
              logger.info("Recording {} as an nonattempt cluster".format(cluster))
              cgus[cgu_name]["batches"][batch_index]["nonattempt"].append(cluster)
              csv_cluster_state = "nonattempt"

          with open(upgrade_csv_file, "a") as csv_file:
            csv_file.write("{},{},{},{},{},{},{},{},{},{},{}\n".format(
              cgu_name, batch_index, cluster, csv_cluster_state, csv_platform_started_time, csv_platform_completion_time,
              csv_platform_duration, csv_operator_creation_timestamp, csv_operator_last_update_time, csv_operator_duration,
              csv_upgrade_duration))

  # Produce the report card on the upgrade CGU and batches
  with open(upgrade_stats_file, "w") as stats_file:
    logger.info("##########################################################################################")
    log_write(stats_file, "Expected platform upgrade: {}".format(cliargs.platform_upgrade))
    log_write(stats_file, "Expected operator csv upgrade: {}".format(cliargs.operator_csvs))

    # Display summary data
    if cliargs.display_summary:
      cgu_total = 0
      batch_total = 0
      su_tc = 0
      su_pc = 0
      su_pp = 0
      su_pn = 0
      su_pu = 0
      su_oc = 0
      su_oi = 0
      su_oi_pc = 0
      su_pc_durations = []
      su_oc_durations = []
      su_upgrade_durations = []
      su_pp_clusters = []
      su_pn_clusters = []
      su_pu_clusters = []
      su_oi_clusters = []
      for cgu_name in cgus:
        cgu_total += 1
        for batch_index, batch in enumerate(cgus[cgu_name]["batches"]):
          batch_total += 1
          su_tc = su_tc + len(cgus[cgu_name]["batches"][batch_index]["clusters"])
          su_pc = su_pc + len(cgus[cgu_name]["batches"][batch_index]["completed"])
          su_pp = su_pp + len(cgus[cgu_name]["batches"][batch_index]["partial"])
          su_pn = su_pn + len(cgus[cgu_name]["batches"][batch_index]["nonattempt"])
          su_pu = su_pu + len(cgus[cgu_name]["batches"][batch_index]["unreachable"])
          su_oc = su_oc + len(cgus[cgu_name]["batches"][batch_index]["operator_completed"])
          su_oi = su_oi + len(cgus[cgu_name]["batches"][batch_index]["operator_incomplete"])
          su_pc_durations.extend(cgus[cgu_name]["batches"][batch_index]["pc_durations"])
          su_oc_durations.extend(cgus[cgu_name]["batches"][batch_index]["oc_durations"])
          su_upgrade_durations.extend(cgus[cgu_name]["batches"][batch_index]["upgrade_durations"])
          su_pp_clusters.extend(cgus[cgu_name]["batches"][batch_index]["partial"])
          su_pn_clusters.extend(cgus[cgu_name]["batches"][batch_index]["nonattempt"])
          su_pu_clusters.extend(cgus[cgu_name]["batches"][batch_index]["unreachable"])
          su_oi_clusters.extend(cgus[cgu_name]["batches"][batch_index]["operator_incomplete"])
      su_pc_percent = round((su_pc / su_tc) * 100, 1)
      su_pp_percent = round((su_pp / su_tc) * 100, 1)
      su_pn_percent = round((su_pn / su_tc) * 100, 1)
      su_pu_percent = round((su_pu / su_tc) * 100, 1)
      su_oc_percent = round((su_oc / su_tc) * 100, 1)
      su_oi_percent = round((su_oi / su_tc) * 100, 1)
      log_write(stats_file, "##########################################################################################")
      log_write(stats_file, "Summerized data over {} CGUs with {} total batches".format(cgu_total, batch_total))
      log_write(stats_file, "Total Clusters: {}".format(su_tc))
      log_write(stats_file, "Total Platform completed: {} :: {}%".format(su_pc, su_pc_percent))
      log_write(stats_file, "Total Platform partial: {} :: {}%".format(su_pp, su_pp_percent))
      log_write(stats_file, "Total Platform nonattempt: {} :: {}%".format(su_pn, su_pn_percent))
      log_write(stats_file, "Total Platform unreachable: {} :: {}%".format(su_pu, su_pu_percent))
      log_write(stats_file, "Total Operator completed: {} :: {}%".format(su_oc, su_oc_percent))
      log_write(stats_file, "Total Operator incomplete: {} :: {}%".format(su_oi, su_oi_percent))
      log_write(stats_file, "Total Platform Completed Durations Min/Avg/50p/95p/99p/Max (seconds): {}".format(assemble_stats(su_pc_durations)))
      # log_write(stats_file, "Total Operator Completed Durations Min/Avg/50p/95p/99p/Max (seconds): {}".format(assemble_stats(su_oc_durations)))
      log_write(stats_file, "Total Upgrade Completed Durations Min/Avg/50p/95p/99p/Max (seconds): {}".format(assemble_stats(su_upgrade_durations)))
      log_write(stats_file, "Total Platform Completed Durations Min/Avg/50p/95p/99p/Max: {}".format(assemble_stats(su_pc_durations, False)))
      # log_write(stats_file, "Total Operator Completed Durations Min/Avg/50p/95p/99p/Max: {}".format(assemble_stats(su_oc_durations, False)))
      log_write(stats_file, "Total Upgrade Completed Durations Min/Avg/50p/95p/99p/Max: {}".format(assemble_stats(su_upgrade_durations, False)))
      log_write(stats_file, "#############################################")
      log_write(stats_file, "Erroneous Clusters over {} CGUs with {} total batches".format(cgu_total, batch_total))
      log_write(stats_file, "Platform partial: {}".format(su_pp_clusters))
      log_write(stats_file, "Platform nonattempt: {}".format(su_pn_clusters))
      log_write(stats_file, "Platform unreachable: {}".format(su_pu_clusters))
      log_write(stats_file, "Operator incomplete: {}".format(su_oi_clusters))
    # End summary data

    # Display CGU data
    for cgu_name in cgus:
      cgu_tc = 0
      cgu_pc = 0
      cgu_pp = 0
      cgu_pn = 0
      cgu_pu = 0
      cgu_oc = 0
      cgu_oi = 0
      cgu_oi_pc = 0
      cgu_pc_durations = []
      cgu_oc_durations = []
      cgu_upgrade_durations = []
      for batch_index, batch in enumerate(cgus[cgu_name]["batches"]):
        cgu_tc = cgu_tc + len(cgus[cgu_name]["batches"][batch_index]["clusters"])
        cgu_pc = cgu_pc + len(cgus[cgu_name]["batches"][batch_index]["completed"])
        cgu_pp = cgu_pp + len(cgus[cgu_name]["batches"][batch_index]["partial"])
        cgu_pn = cgu_pn + len(cgus[cgu_name]["batches"][batch_index]["nonattempt"])
        cgu_pu = cgu_pu + len(cgus[cgu_name]["batches"][batch_index]["unreachable"])
        cgu_oc = cgu_oc + len(cgus[cgu_name]["batches"][batch_index]["operator_completed"])
        cgu_oi = cgu_oi + len(cgus[cgu_name]["batches"][batch_index]["operator_incomplete"])
        cgu_pc_durations.extend(cgus[cgu_name]["batches"][batch_index]["pc_durations"])
        cgu_oc_durations.extend(cgus[cgu_name]["batches"][batch_index]["oc_durations"])
        cgu_upgrade_durations.extend(cgus[cgu_name]["batches"][batch_index]["upgrade_durations"])
      cgu_pc_percent = round((cgu_pc / cgu_tc) * 100, 1)
      cgu_pp_percent = round((cgu_pp / cgu_tc) * 100, 1)
      cgu_pn_percent = round((cgu_pn / cgu_tc) * 100, 1)
      cgu_pu_percent = round((cgu_pu / cgu_tc) * 100, 1)
      cgu_oc_percent = round((cgu_oc / cgu_tc) * 100, 1)
      cgu_oi_percent = round((cgu_oi / cgu_tc) * 100, 1)
      log_write(stats_file, "##########################################################################################")
      log_write(stats_file, "Collected Data for CGU: {}".format(cgu_name))
      log_write(stats_file, "CGU creationTimestamp: {}".format(cgus[cgu_name]["creationTimestamp"]))
      log_write(stats_file, "CGU startedAt: {}".format(cgus[cgu_name]["startedAt"]))
      log_write(stats_file, "CGU Batches: {}".format(len(cgus[cgu_name]["batches"])))
      log_write(stats_file, "CGU Total Clusters: {}".format(cgu_tc))
      log_write(stats_file, "CGU Platform completed: {} :: {}%".format(cgu_pc, cgu_pc_percent))
      log_write(stats_file, "CGU Platform partial: {} :: {}%".format(cgu_pp, cgu_pp_percent))
      log_write(stats_file, "CGU Platform nonattempt: {} :: {}%".format(cgu_pn, cgu_pn_percent))
      log_write(stats_file, "CGU Platform unreachable: {} :: {}%".format(cgu_pu, cgu_pu_percent))
      log_write(stats_file, "CGU Operator completed: {} :: {}%".format(cgu_oc, cgu_oc_percent))
      log_write(stats_file, "CGU Operator incomplete: {} :: {}%".format(cgu_oi, cgu_oi_percent))
      log_write(stats_file, "CGU Platform Completed Durations Min/Avg/50p/95p/99p/Max (seconds): {}".format(assemble_stats(cgu_pc_durations)))
      # log_write(stats_file, "CGU Operator Completed Durations Min/Avg/50p/95p/99p/Max (seconds): {}".format(assemble_stats(cgu_oc_durations)))
      log_write(stats_file, "CGU Upgrade Completed Durations Min/Avg/50p/95p/99p/Max (seconds): {}".format(assemble_stats(cgu_upgrade_durations)))
      log_write(stats_file, "CGU Platform Completed Durations Min/Avg/50p/95p/99p/Max: {}".format(assemble_stats(cgu_pc_durations, False)))
      # log_write(stats_file, "CGU Operator Completed Durations Min/Avg/50p/95p/99p/Max: {}".format(assemble_stats(cgu_oc_durations, False)))
      log_write(stats_file, "CGU Upgrade Completed Durations Min/Avg/50p/95p/99p/Max: {}".format(assemble_stats(cgu_upgrade_durations, False)))
      # Now show for each batch in the CGU
      if cliargs.display_batch:
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
          batch_tc = len(cgus[cgu_name]["batches"][batch_index]["clusters"])
          batch_pc = len(cgus[cgu_name]["batches"][batch_index]["completed"])
          batch_pp = len(cgus[cgu_name]["batches"][batch_index]["partial"])
          batch_pn = len(cgus[cgu_name]["batches"][batch_index]["nonattempt"])
          batch_pu = len(cgus[cgu_name]["batches"][batch_index]["unreachable"])
          batch_oc = len(cgus[cgu_name]["batches"][batch_index]["operator_completed"])
          batch_oi = len(cgus[cgu_name]["batches"][batch_index]["operator_incomplete"])
          batch_pc_percent = round((batch_pc / batch_tc) * 100, 1)
          batch_pp_percent = round((batch_pp / batch_tc) * 100, 1)
          batch_pn_percent = round((batch_pn / batch_tc) * 100, 1)
          batch_pu_percent = round((batch_pu / batch_tc) * 100, 1)
          batch_oc_percent = round((batch_oc / batch_tc) * 100, 1)
          batch_oi_percent = round((batch_oi / batch_tc) * 100, 1)
          log_write(stats_file, "#############################################")
          log_write(stats_file, "Data from {} Batch {}".format(cgu_name, batch_index))
          log_write(stats_file, "Cluster Start: {}".format(cgus[cgu_name]["batches"][batch_index]["clusters"][0]))
          log_write(stats_file, "Cluster End: {}".format(cgus[cgu_name]["batches"][batch_index]["clusters"][-1]))
          log_write(stats_file, "Total Clusters: {}".format(batch_tc))
          log_write(stats_file, "Platform completed: {} :: {}%".format(batch_pc, batch_pc_percent))
          log_write(stats_file, "Platform partial: {} :: {}%".format(batch_pp, batch_pp_percent))
          log_write(stats_file, "Platform nonattempt: {} :: {}%".format(batch_pn, batch_pn_percent))
          log_write(stats_file, "Platform unreachable: {} :: {}%".format(batch_pu, batch_pu_percent))
          log_write(stats_file, "Operator completed: {} :: {}%".format(batch_oc, batch_oc_percent))
          log_write(stats_file, "Operator incomplete: {} :: {}%".format(batch_oi, batch_oi_percent))
          log_write(stats_file, "Earliest platform start timestamp: {}".format(cgus[cgu_name]["batches"][batch_index]["startTS"]))
          log_write(stats_file, "Latest platform end timestamp: {}".format(cgus[cgu_name]["batches"][batch_index]["platformEndTS"]))
          log_write(stats_file, "Latest operator end timestamp: {}".format(cgus[cgu_name]["batches"][batch_index]["operatorEndTS"]))
          log_write(stats_file, "Platform Duration(platformEndTS - startTS): {}s :: {}".format(platform_duration, platform_duration_h))
          log_write(stats_file, "Upgrade Duration(operatorEndTS - startTS): {}s :: {}".format(upgrade_duration, upgrade_duration_h))
          log_write(stats_file, "Platform Completed Durations Min/Avg/50p/95p/99p/Max (seconds): {}".format(
              assemble_stats(cgus[cgu_name]["batches"][batch_index]["pc_durations"])))
          # log_write(stats_file, "Operator Completed Durations Min/Avg/50p/95p/99p/Max (seconds): {}".format(
          #     assemble_stats(cgus[cgu_name]["batches"][batch_index]["oc_durations"])))
          log_write(stats_file, "Upgrade Completed Durations Min/Avg/50p/95p/99p/Max (seconds): {}".format(
              assemble_stats(cgus[cgu_name]["batches"][batch_index]["upgrade_durations"])))
          log_write(stats_file, "Platform Completed Durations Min/Avg/50p/95p/99p/Max: {}".format(
              assemble_stats(cgus[cgu_name]["batches"][batch_index]["pc_durations"], False)))
          # log_write(stats_file, "Operator Completed Durations Min/Avg/50p/95p/99p/Max: {}".format(
          #     assemble_stats(cgus[cgu_name]["batches"][batch_index]["oc_durations"], False)))
          log_write(stats_file, "Upgrade Completed Durations Min/Avg/50p/95p/99p/Max: {}".format(
              assemble_stats(cgus[cgu_name]["batches"][batch_index]["upgrade_durations"], False)))
        for batch_index, batch in enumerate(cgus[cgu_name]["batches"]):
          log_write(stats_file, "#############################################")
          log_write(stats_file, "Erroneous Clusters from {} Batch {}".format(cgu_name, batch_index))
          log_write(stats_file, "Platform partial: {}".format(cgus[cgu_name]["batches"][batch_index]["partial"]))
          log_write(stats_file, "Platform nonattempt: {}".format(cgus[cgu_name]["batches"][batch_index]["nonattempt"]))
          log_write(stats_file, "Platform unreachable: {}".format(cgus[cgu_name]["batches"][batch_index]["unreachable"]))
          log_write(stats_file, "Operator incomplete: {}".format(cgus[cgu_name]["batches"][batch_index]["operator_incomplete"]))
      # End display batch data
    # End display CGU data

  end_time = time.time()
  logger.info("##########################################################################################")
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

def assemble_stats(the_list, seconds=True):
  stats_min = 0
  stats_avg = 0
  stats_p50 = 0
  stats_p95 = 0
  stats_p99 = 0
  stats_max = 0
  if len(the_list) > 0:
    if seconds:
      stats_min = np.min(the_list)
      stats_avg = round(np.mean(the_list), 1)
      stats_p50 = round(np.percentile(the_list, 50), 1)
      stats_p95 = round(np.percentile(the_list, 95), 1)
      stats_p99 = round(np.percentile(the_list, 99), 1)
      stats_max = np.max(the_list)
    else:
      stats_min = str(timedelta(seconds=np.min(the_list)))
      stats_avg = str(timedelta(seconds=round(np.mean(the_list))))
      stats_p50 = str(timedelta(seconds=round(np.percentile(the_list, 50))))
      stats_p95 = str(timedelta(seconds=round(np.percentile(the_list, 95))))
      stats_p99 = str(timedelta(seconds=round(np.percentile(the_list, 99))))
      stats_max = str(timedelta(seconds=np.max(the_list)))
  return "{} :: {} :: {} :: {} :: {} :: {}".format(stats_min, stats_avg, stats_p50, stats_p95, stats_p99, stats_max)

if __name__ == "__main__":
  sys.exit(main())
