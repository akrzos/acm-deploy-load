#!/usr/bin/env python3
#
# Analyze all deployed cluster's clusterversion objects to determine success and timing of upgrades. Also records all
# data into a csv file.
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
import json
from utils.command import command
from utils.output import log_write
import logging
import numpy as np
import sys
import time


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Analyze each deployed cluster's clusterversion data",
      prog="analyze-clusterversion.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("-k", "--kubeconfigs", type=str, default="/root/hv-vm/kc",
                      help="The location of the kubeconfigs, nested under each cluster's directory")
  parser.add_argument("results_directory", type=str, help="The location to place analyzed data")
  cliargs = parser.parse_args()

  logger.info("Analyze clusterversion")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")
  cv_csv_file = "{}/clusterversion-{}.csv".format(cliargs.results_directory, ts)
  cv_stats_file = "{}/clusterversion-{}.stats".format(cliargs.results_directory, ts)

  oc_cmd = ["oc", "get", "agentclusterinstalls", "-A", "-o", "json"]
  rc, output = command(oc_cmd, False, retries=3, no_log=True)
  if rc != 0:
    logger.error("analyze-clusterversion, oc get agentclusterinstalls rc: {}".format(rc))
    sys.exit(1)
  aci_data = json.loads(output)

  clusters = []
  clusters_total = 0
  clusters_unreachable = []
  clusterversions_data = OrderedDict()
  clusters_dup_entries = []

  for item in aci_data["items"]:
    aci_name = item["metadata"]["name"]
    for condition in item["status"]["conditions"]:
      if condition["type"] == "Completed":
        if condition["status"] == "True":
          if condition["reason"] == "InstallationCompleted":
            clusters.append(aci_name)
        break;

  clusters_total = len(clusters)
  logger.info("Number of cluster clusterversions to examine: {}".format(clusters_total))

  logger.info("Writing CSV: {}".format(cv_csv_file))
  with open(cv_csv_file, "w") as csv_file:
    csv_file.write("name,version,state,startedTime,completionTime,duration\n")

  for cluster in clusters:
    kubeconfig = "{}/{}/kubeconfig".format(cliargs.kubeconfigs, cluster)
    oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "clusterversion", "version", "-o", "json"]
    rc, output = command(oc_cmd, False, retries=2, no_log=True)
    if rc != 0:
      logger.error("analyze-clusterversion, oc get clusterversion rc: {}".format(rc))
      clusters_unreachable.append(cluster)
      with open(cv_csv_file, "a") as csv_file:
        csv_file.write("{},NA,NA,,,\n".format(cluster))
      continue
    cv_data = json.loads(output)

    for ver_hist_entry in cv_data["status"]["history"]:
      cv_version = ver_hist_entry["version"]
      cv_state = ver_hist_entry["state"]
      cv_startedtime = ver_hist_entry["startedTime"]
      cv_completiontime = ""
      cv_duration = ""
      if cv_version not in clusterversions_data:
        clusterversions_data[cv_version] = {}
        clusterversions_data[cv_version]["completed_durations"] = []
        clusterversions_data[cv_version]["state"] = {}
        clusterversions_data[cv_version]["count"] = 0
      if cv_state not in clusterversions_data[cv_version]["state"]:
        clusterversions_data[cv_version]["state"][cv_state] = []
      if cluster not in clusterversions_data[cv_version]["state"][cv_state]:
        # Do not add duplicated entry if a Completed entry already exists
        if "Completed" in clusterversions_data[cv_version]["state"] and cluster in clusterversions_data[cv_version]["state"]["Completed"]:
          logger.warn("Cluster {} has entry for Completed {} and a duplicate entry for {}".format(cluster, cv_version, cv_state))
          if cluster not in clusters_dup_entries:
            clusters_dup_entries.append(cluster)
        else:
          clusterversions_data[cv_version]["state"][cv_state].append(cluster)
          clusterversions_data[cv_version]["count"] += 1
      if cv_state == "Completed":
        cv_completiontime = ver_hist_entry["completionTime"]
        start = datetime.strptime(cv_startedtime, "%Y-%m-%dT%H:%M:%SZ")
        end = datetime.strptime(cv_completiontime, "%Y-%m-%dT%H:%M:%SZ")
        cv_duration = (end - start).total_seconds()
        clusterversions_data[cv_version]["completed_durations"].append(cv_duration)
        # Remove errornous partial upgrade history from stats
        if "Partial" in clusterversions_data[cv_version]["state"] and cluster in clusterversions_data[cv_version]["state"]["Partial"]:
          logger.warn("Cluster {} has a duplicate Partial entry for version {}".format(cluster, cv_version))
          clusterversions_data[cv_version]["state"]["Partial"].remove(cluster)
          clusterversions_data[cv_version]["count"] -= 1
          if cluster not in clusters_dup_entries:
            clusters_dup_entries.append(cluster)
      with open(cv_csv_file, "a") as csv_file:
        csv_file.write("{},{},{},{},{},{}\n".format(cluster, cv_version, cv_state, cv_startedtime, cv_completiontime, cv_duration))

  percent_unreachable = round((len(clusters_unreachable) / clusters_total) * 100, 1)

  logger.info("Writing Stats: {}".format(cv_stats_file))
  with open(cv_stats_file, "w") as stats_file:
    log_write(stats_file, "Stats only on clusterversion in Completed state")
    log_write(stats_file, "Total Clusters: {}".format(clusters_total))
    log_write(stats_file, "Unreachable Cluster Count: {}".format(len(clusters_unreachable)))
    log_write(stats_file, "Unreachable Cluster Percent: {}%".format(percent_unreachable))
    log_write(stats_file, "Unreachable Clusters: {}".format(clusters_unreachable))
    log_write(stats_file, "Duplicated clusterversion history Cluster Count: {}".format(len(clusters_dup_entries)))
    log_write(stats_file, "Duplicated clusterversion history Clusters: {}".format(clusters_dup_entries))

  for version in clusterversions_data:
    with open(cv_stats_file, "a") as stats_file:
      log_write(stats_file, "#############################################")
      log_write(stats_file, "Analyzing Version: {}".format(version))
      log_write(stats_file, "Total entries: {}".format(clusterversions_data[version]["count"]))
      for state in clusterversions_data[version]["state"]:
        percent_of_total = round((len(clusterversions_data[version]["state"][state]) / clusterversions_data[version]["count"]) * 100, 1)
        if state != "Completed":
          log_write(stats_file, "State: {}, Count: {}, Percent: {}%, SNOs: {}".format(state, len(clusterversions_data[version]["state"][state]), percent_of_total, clusterversions_data[version]["state"][state]))
        else:
          log_write(stats_file, "State: {}, Count: {}, Percent: {}%".format(state, len(clusterversions_data[version]["state"][state]), percent_of_total))
      log_write(stats_file, "Min: {}".format(np.min(clusterversions_data[version]["completed_durations"])))
      log_write(stats_file, "Average: {}".format(round(np.mean(clusterversions_data[version]["completed_durations"]), 1)))
      log_write(stats_file, "50 percentile: {}".format(round(np.percentile(clusterversions_data[version]["completed_durations"], 50), 1)))
      log_write(stats_file, "95 percentile: {}".format(round(np.percentile(clusterversions_data[version]["completed_durations"], 95), 1)))
      log_write(stats_file, "99 percentile: {}".format(round(np.percentile(clusterversions_data[version]["completed_durations"], 99), 1)))
      log_write(stats_file, "Max: {}".format(np.max(clusterversions_data[version]["completed_durations"])))

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
