#!/usr/bin/env python3
#
# Analyze ImageClusterInstalls data on a hub cluster to determine count/min/avg/max/50p/95p/99p timings
#
#  Copyright 2024 Red Hat
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
from datetime import datetime
import json
from utils.command import command
from utils.output import log_write
import logging
import numpy as np
import os
import sys
import time


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Analyze ImageClusterInstalls data",
      prog="analyze-imageclusterinstalls.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("-o", "--offline-process", action="store_true", default=False,
                      help="Uses previously stored raw data")
  parser.add_argument("-r", "--raw-data-file", type=str, default="",
                    help="Set raw json data file for offline processing. Empty finds last file")
  parser.add_argument("results_directory", type=str, help="The location to place analyzed data")
  cliargs = parser.parse_args()

  logger.info("Analyze imageclusterinstalls")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")

  raw_data_file = "{}/imageclusterinstalls-{}.json".format(cliargs.results_directory, ts)
  if cliargs.offline_process:
    if cliargs.raw_data_file == "":
      # # Detect last raw data file
      dir_scan = sorted([ f.path for f in os.scandir(cliargs.results_directory) if f.is_file() and "imageclusterinstalls" in f.path and "json" in f.path ])
      if len(dir_scan) == 0:
        logger.error("No previous offline file found. Exiting")
        sys.exit(1)
      raw_data_file = dir_scan[-1]
    else:
      raw_data_file = cliargs.raw_data_file
    logger.info("Reading raw data from: {}".format(raw_data_file))
  else:
    logger.info("Storing raw data file at: {}".format(raw_data_file))

  ici_csv_file = "{}/imageclusterinstalls-{}.csv".format(cliargs.results_directory, ts)
  ici_stats_file = "{}/imageclusterinstalls-{}.stats".format(cliargs.results_directory, ts)

  if not cliargs.offline_process:
    oc_cmd = ["oc", "get", "imageclusterinstalls", "-A", "-o", "json"]
    rc, output = command(oc_cmd, False, retries=3, no_log=True)
    if rc != 0:
      logger.error("analyze-imageclusterinstalls, oc get imageclusterinstalls rc: {}".format(rc))
      sys.exit(1)
    with open(raw_data_file, "w") as ici_data_file:
      ici_data_file.write(output)
  with open(raw_data_file, "r") as ici_file_data:
    ici_data = json.load(ici_file_data)

  logger.info("Writing CSV: {}".format(ici_csv_file))
  with open(ici_csv_file, "w") as csv_file:
    csv_file.write("name,status,creationTimestamp,bootTime,RequirementsMet.lastTransitionTime,"
        "completed.lastTransitionTime,ct_boot_duration,boot_rm_duration,rm_completed_duration,"
        "total_duration\n")

  ici_installcompleted_values = []
  for item in ici_data["items"]:
    ici_name = item["metadata"]["name"]
    ici_status = "unknown"
    ici_creationTimestamp = datetime.strptime(item["metadata"]["creationTimestamp"], "%Y-%m-%dT%H:%M:%SZ")
    ici_boot_ts = datetime.strptime(item["status"]["bootTime"], "%Y-%m-%dT%H:%M:%SZ")
    ici_requirements_met_ts = ""
    ici_completed_ts = ""
    ici_ct_boot_duration = 0
    ici_boot_rm_duration = 0
    ici_rm_completed_duration = 0
    ici_total_duration = 0
    for condition in item["status"]["conditions"]:
      if condition["type"] == "RequirementsMet" and condition["status"] == "True":
        ici_requirements_met_ts = datetime.strptime(condition["lastTransitionTime"], "%Y-%m-%dT%H:%M:%SZ")
      elif condition["type"] == "Completed" and condition["status"] == "True":
        ici_completed_ts = datetime.strptime(condition["lastTransitionTime"], "%Y-%m-%dT%H:%M:%SZ")
        ici_status = condition["reason"]
        break

    ici_ct_boot_duration = (ici_boot_ts - ici_creationTimestamp).total_seconds()
    if ici_requirements_met_ts != "":
      ici_boot_rm_duration = (ici_requirements_met_ts - ici_boot_ts).total_seconds()
      if ici_completed_ts != "":
        ici_rm_completed_duration = (ici_completed_ts - ici_requirements_met_ts).total_seconds()

    if ici_status == "ClusterInstallationSucceeded":
      ici_total_duration = (ici_completed_ts - ici_creationTimestamp).total_seconds()
      # Exclude values of 0
      if ici_total_duration > 0:
        ici_installcompleted_values.append(ici_total_duration)

    with open(ici_csv_file, "a") as csv_file:
      csv_file.write(
          "{},{},{},{},{},{},{},{},{},{}\n".format(ici_name, ici_status, ici_creationTimestamp,
          ici_boot_ts, ici_requirements_met_ts, ici_completed_ts, ici_ct_boot_duration,
          ici_boot_rm_duration, ici_rm_completed_duration, ici_total_duration))

  logger.info("Writing Stats: {}".format(ici_stats_file))
  stats_count = len(ici_installcompleted_values)
  stats_min = 0
  stats_avg = 0
  stats_50p = 0
  stats_95p = 0
  stats_99p = 0
  stats_max = 0
  if stats_count > 0:
    stats_min = np.min(ici_installcompleted_values)
    stats_avg = round(np.mean(ici_installcompleted_values), 1)
    stats_50p = round(np.percentile(ici_installcompleted_values, 50), 1)
    stats_95p = round(np.percentile(ici_installcompleted_values, 95), 1)
    stats_99p = round(np.percentile(ici_installcompleted_values, 99), 1)
    stats_max = np.max(ici_installcompleted_values)

  with open(ici_stats_file, "w") as stats_file:
    log_write(stats_file, "Stats only on ImageClusterInstalls CRs in ClusterInstallationSucceeded")
    log_write(stats_file, "Count: {}".format(stats_count))
    log_write(stats_file, "Min: {}".format(stats_min))
    log_write(stats_file, "Average: {}".format(stats_avg))
    log_write(stats_file, "50 percentile: {}".format(stats_50p))
    log_write(stats_file, "95 percentile: {}".format(stats_95p))
    log_write(stats_file, "99 percentile: {}".format(stats_99p))
    log_write(stats_file, "Max: {}".format(stats_max))

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
