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
from datetime import datetime
from datetime import timedelta
import json
from utils.command import command
import logging
import numpy as np
import sys
import time


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("analyze-clustergroupupgrades")
logging.Formatter.converter = time.gmtime


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Analyze ClusterGroupUpgrades data",
      prog="analyze-clustergroupupgrades.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("results_directory", type=str, help="The location to place analyzed data")
  parser.add_argument("-n", "--namespace", type=str, default="ztp-install", help="Namespace of the CGUs to analyze")
  cliargs = parser.parse_args()

  logger.info("Analyze clustergroupupgrades")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")
  cgu_csv_file = "{}/clustergroupupgrades-{}-{}.csv".format(cliargs.results_directory, cliargs.namespace, ts)
  cgu_stats_file = "{}/clustergroupupgrades-{}-{}.stats".format(cliargs.results_directory, cliargs.namespace, ts)

  oc_cmd = ["oc", "get", "clustergroupupgrades", "-n", cliargs.namespace, "-o", "json"]
  rc, output = command(oc_cmd, False, retries=3, no_log=True)
  if rc != 0:
    logger.error("analyze-clustergroupupgrades, oc get clustergroupupgrades -n {} rc: {}".format(cliargs.namespace, rc))
    sys.exit(1)
  cgu_data = json.loads(output)

  cgus_total = len(cgu_data["items"])
  cgu_conditions = {}
  cgus_create_time = ""
  cgus_started_time = ""
  cgus_completed_time = ""

  logger.info("Writing CSV: {}".format(cgu_csv_file))
  with open(cgu_csv_file, "w") as csv_file:
    csv_file.write("name,status,startedAt,completedAt,duration\n")

  cgu_upgradecompleted_values = []
  for item in cgu_data["items"]:
    cgu_name = item["metadata"]["name"]
    cgu_status = "unknown"

    # Determine earliest creationTimestamp for the cgus in this namespace
    cgu_created = datetime.strptime(item["metadata"]["creationTimestamp"], "%Y-%m-%dT%H:%M:%SZ")
    if cgus_create_time == "":
      cgus_create_time = cgu_created
    elif cgus_create_time > cgu_created:
      logger.info("Replacing cgu created time {} with earlier time {}".format(cgus_create_time, cgu_created))
      cgus_create_time = cgu_created

    cgu_startedAt = ""
    if "startedAt" in item["status"]["status"]:
      # Determine earliest startedAt time for the cgus in this namespace
      cgu_startedAt = datetime.strptime(item["status"]["status"]["startedAt"], "%Y-%m-%dT%H:%M:%SZ")
      if cgus_started_time == "":
        cgus_started_time = cgu_startedAt
      elif cgus_started_time > cgu_startedAt:
        logger.info("Replacing cgu started time {} with earlier time {}".format(cgus_started_time, cgu_startedAt))
        cgus_started_time = cgu_startedAt

    cgu_completedAt = ""
    cgu_duration = 0
    for condition in item["status"]["conditions"]:
      if condition["reason"] not in cgu_conditions:
        cgu_conditions[condition["reason"]] = 1
      else:
        cgu_conditions[condition["reason"]] += 1
      if condition["type"] == "Ready":
        if condition["status"] == "True":
          if "completedAt" in item["status"]["status"]:
            # Determine latest populated completed time
            cgu_completedAt = datetime.strptime(item["status"]["status"]["completedAt"], "%Y-%m-%dT%H:%M:%SZ")
            if cgus_completed_time == "":
              cgus_completed_time = cgu_completedAt
            elif cgus_completed_time < cgu_completedAt:
              logger.info("Replacing cgu completed time {} with later time {}".format(cgus_completed_time, cgu_completedAt))
              cgus_completed_time = cgu_completedAt

        cgu_status = condition["reason"]
        break;

    if cgu_status == "UpgradeCompleted" and cgu_startedAt != "" and cgu_completedAt != "":
      cgu_duration = (cgu_completedAt - cgu_startedAt).total_seconds()
      cgu_upgradecompleted_values.append(cgu_duration)

    # logger.info("{},{},{},{},{}".format(cgu_name, cgu_status, cgu_startedAt, cgu_completedAt, cgu_duration))

    with open(cgu_csv_file, "a") as csv_file:
      csv_file.write("{},{},{},{},{}\n".format(cgu_name, cgu_status, cgu_startedAt, cgu_completedAt, cgu_duration))

  logger.info("Writing Stats: {}".format(cgu_stats_file))
  stats_count = len(cgu_upgradecompleted_values)
  stats_min = 0
  stats_avg = 0
  stats_50p = 0
  stats_95p = 0
  stats_99p = 0
  stats_max = 0
  if stats_count > 0:
    stats_min = np.min(cgu_upgradecompleted_values)
    stats_avg = round(np.mean(cgu_upgradecompleted_values), 1)
    stats_50p = round(np.percentile(cgu_upgradecompleted_values, 50), 1)
    stats_95p = round(np.percentile(cgu_upgradecompleted_values, 95), 1)
    stats_99p = round(np.percentile(cgu_upgradecompleted_values, 99), 1)
    stats_max = np.max(cgu_upgradecompleted_values)

  duration_create_start = (cgus_started_time - cgus_create_time).total_seconds()
  duration_start_completed = (cgus_completed_time - cgus_started_time).total_seconds()
  duration_create_completed = (cgus_completed_time - cgus_create_time).total_seconds()

  logger.info("#############################################")
  logger.info("Stats on clustergroupupgrades CRs in namespace {}".format(cliargs.namespace))
  logger.info("Total CGUs - {}".format(cgus_total))
  for condition in cgu_conditions:
    logger.info("CGUs with {}: {} - {}%".format(condition, cgu_conditions[condition], round((cgu_conditions[condition] / cgus_total) * 100, 1)))
  logger.info("Earliest CGU creationTimestamp: {}".format(cgus_create_time))
  logger.info("Earliest CGU startedAt Timestamp: {}".format(cgus_started_time))
  logger.info("Latest CGU completedAt Timestamp: {}".format(cgus_completed_time))
  logger.info("Duration between creation and startedAt: {}s :: {}".format(duration_create_start, str(timedelta(seconds=duration_create_start))))
  logger.info("Duration between startedAt and completedAt: {}s :: {}".format(duration_start_completed, str(timedelta(seconds=duration_start_completed))))
  logger.info("Duration between creation and completedAt: {}s :: {}".format(duration_create_completed, str(timedelta(seconds=duration_create_completed))))
  logger.info("#############################################")
  logger.info("Stats only on clustergroupupgrades CRs in UpgradeCompleted")
  logger.info("Count: {}".format(stats_count))
  logger.info("Min: {}".format(stats_min))
  logger.info("Average: {}".format(stats_avg))
  logger.info("50 percentile: {}".format(stats_50p))
  logger.info("95 percentile: {}".format(stats_95p))
  logger.info("99 percentile: {}".format(stats_99p))
  logger.info("Max: {}".format(stats_max))

  with open(cgu_stats_file, "w") as stats_file:
    stats_file.write("#############################################\n")
    stats_file.write("Stats on clustergroupupgrades CRs in namespace {}\n".format(cliargs.namespace))
    stats_file.write("Total CGUs - {}\n".format(cgus_total))
    for condition in cgu_conditions:
      stats_file.write("CGUs with {}: {} - {}%\n".format(condition, cgu_conditions[condition], round((cgu_conditions[condition] / cgus_total) * 100, 1)))
    stats_file.write("Earliest CGU creationTimestamp: {}\n".format(cgus_create_time))
    stats_file.write("Earliest CGU startedAt Timestamp: {}\n".format(cgus_started_time))
    stats_file.write("Latest CGU completedAt Timestamp: {}\n".format(cgus_completed_time))
    stats_file.write("Duration between creation and startedAt: {}s :: {}\n".format(duration_create_start, str(timedelta(seconds=duration_create_start))))
    stats_file.write("Duration between startedAt and completedAt: {}s :: {}\n".format(duration_start_completed, str(timedelta(seconds=duration_start_completed))))
    stats_file.write("Duration between creation and completedAt: {}s :: {}\n".format(duration_create_completed, str(timedelta(seconds=duration_create_completed))))
    stats_file.write("#############################################\n")
    stats_file.write("Stats only on clustergroupupgrades CRs in UpgradeCompleted\n")
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
