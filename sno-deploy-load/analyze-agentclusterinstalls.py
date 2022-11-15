#!/usr/bin/env python3
#
# Analyze AgentClusterInstalls data on a hub cluster to determine count/min/avg/max/50p/95p/99p timings
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
from datetime import datetime
import json
from utils.command import command
import logging
import numpy as np
import sys
import time


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("analyze-agentclusterinstalls")
logging.Formatter.converter = time.gmtime


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Analyze AgentClusterInstalls data",
      prog="analyze-agentclusterinstalls.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("results_directory", type=str, help="The location to place analyzed data")
  cliargs = parser.parse_args()

  logger.info("Analyze agentclusterinstalls")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")
  aci_csv_file = "{}/agentclusterinstalls-{}.csv".format(cliargs.results_directory, ts)
  aci_stats_file = "{}/agentclusterinstalls-{}.stats".format(cliargs.results_directory, ts)

  oc_cmd = ["oc", "get", "agentclusterinstalls", "-A", "-o", "json"]
  rc, output = command(oc_cmd, False, retries=3, no_log=True)
  if rc != 0:
    logger.error("analyze-agentclusterinstalls, oc get agentclusterinstalls rc: {}".format(rc))
    sys.exit(1)
  aci_data = json.loads(output)

  logger.info("Writing CSV: {}".format(aci_csv_file))
  with open(aci_csv_file, "w") as csv_file:
    csv_file.write("name,status,creationTimestamp,completed.lastTransitionTime,duration\n")

  aci_installcompleted_values = []
  for item in aci_data["items"]:
    aci_name = item["metadata"]["name"]
    aci_status = "unknown"
    aci_creationTimestamp = item["metadata"]["creationTimestamp"]
    aci_completed_ltt = ""
    aci_duration = 0
    for condition in item["status"]["conditions"]:
      if condition["type"] == "Completed":
        if condition["status"] == "True":
          aci_completed_ltt = condition["lastTransitionTime"]
        aci_status = condition["reason"]
        break;

    if aci_status == "InstallationCompleted":
      start = datetime.strptime(aci_creationTimestamp, "%Y-%m-%dT%H:%M:%SZ")
      end = datetime.strptime(aci_completed_ltt, "%Y-%m-%dT%H:%M:%SZ")
      aci_duration = (end - start).total_seconds()
      aci_installcompleted_values.append(aci_duration)

    # logger.info("{},{},{},{},{}".format(aci_name, aci_status, aci_creationTimestamp, aci_completed_ltt, aci_duration))

    with open(aci_csv_file, "a") as csv_file:
      csv_file.write("{},{},{},{},{}\n".format(aci_name, aci_status, aci_creationTimestamp, aci_completed_ltt, aci_duration))

  logger.info("Writing Stats: {}".format(aci_stats_file))
  stats_count = len(aci_installcompleted_values)
  stats_min = 0
  stats_avg = 0
  stats_50p = 0
  stats_95p = 0
  stats_99p = 0
  stats_max = 0
  if stats_count > 0:
    stats_min = np.min(aci_installcompleted_values)
    stats_avg = round(np.mean(aci_installcompleted_values), 1)
    stats_50p = round(np.percentile(aci_installcompleted_values, 50), 1)
    stats_95p = round(np.percentile(aci_installcompleted_values, 95), 1)
    stats_99p = round(np.percentile(aci_installcompleted_values, 99), 1)
    stats_max = np.max(aci_installcompleted_values)

  logger.info("Stats only on AgentClusterInstall CRs in InstallationCompleted")
  logger.info("Count: {}".format(stats_count))
  logger.info("Min: {}".format(stats_min))
  logger.info("Average: {}".format(stats_avg))
  logger.info("50 percentile: {}".format(stats_50p))
  logger.info("95 percentile: {}".format(stats_95p))
  logger.info("99 percentile: {}".format(stats_99p))
  logger.info("Max: {}".format(stats_max))

  with open(aci_stats_file, "w") as stats_file:
    stats_file.write("Stats only on AgentClusterInstall CRs in InstallationCompleted\n")
    stats_file.write("Count: {}\n".format(stats_count))
    stats_file.write("Min: {}\n".format(stats_min))
    stats_file.write("Average: {}\n".format(stats_avg))
    stats_file.write("50 percentile: {}\n".format(stats_50p))
    stats_file.write("95 percentile: {}\n".format(stats_95p))
    stats_file.write("99 percentile: {}\n".format(stats_99p))
    stats_file.write("Max: {}\n".format(stats_max))

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
