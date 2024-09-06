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
  parser.add_argument("results_directory", type=str, help="The location to place analyzed data")
  cliargs = parser.parse_args()

  logger.info("Analyze imageclusterinstalls")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")
  ici_csv_file = "{}/imageclusterinstalls-{}.csv".format(cliargs.results_directory, ts)
  ici_stats_file = "{}/imageclusterinstalls-{}.stats".format(cliargs.results_directory, ts)

  oc_cmd = ["oc", "get", "imageclusterinstalls", "-A", "-o", "json"]
  rc, output = command(oc_cmd, False, retries=3, no_log=True)
  if rc != 0:
    logger.error("analyze-imageclusterinstalls, oc get imageclusterinstalls rc: {}".format(rc))
    sys.exit(1)
  ici_data = json.loads(output)

  logger.info("Writing CSV: {}".format(ici_csv_file))
  with open(ici_csv_file, "w") as csv_file:
    csv_file.write("name,status,creationTimestamp,completed.lastTransitionTime,duration\n")

  ici_installcompleted_values = []
  for item in ici_data["items"]:
    ici_name = item["metadata"]["name"]
    ici_status = "unknown"
    ici_creationTimestamp = item["metadata"]["creationTimestamp"]
    ici_completed_ltt = ""
    ici_duration = 0
    for condition in item["status"]["conditions"]:
      if condition["type"] == "Completed":
        if condition["status"] == "True":
          ici_completed_ltt = condition["lastTransitionTime"]
        ici_status = condition["reason"]
        break

    if ici_status == "ClusterInstallationSucceeded":
      start = datetime.strptime(ici_creationTimestamp, "%Y-%m-%dT%H:%M:%SZ")
      end = datetime.strptime(ici_completed_ltt, "%Y-%m-%dT%H:%M:%SZ")
      ici_duration = (end - start).total_seconds()
      # Exclude values of 0
      if ici_duration > 0:
        ici_installcompleted_values.append(ici_duration)

    # logger.info("{},{},{},{},{}".format(ici_name, ici_status, ici_creationTimestamp, ici_completed_ltt, ici_duration))

    with open(ici_csv_file, "a") as csv_file:
      csv_file.write("{},{},{},{},{}\n".format(ici_name, ici_status, ici_creationTimestamp, ici_completed_ltt, ici_duration))

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
