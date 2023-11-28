#!/usr/bin/env python3
#
# Analyze AnsibleJobs data on a hub cluster to determine durations and targets
#
#  Copyright 2023 Red Hat
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
      description="Analyze AnsibleJobs data",
      prog="analyze-ansiblejobs.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("results_directory", type=str, help="The location to place analyzed data")
  cliargs = parser.parse_args()

  logger.info("Analyze ansiblejobs")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")
  aj_csv_file = "{}/ansiblejobs-{}.csv".format(cliargs.results_directory, ts)
  # aj_stats_file = "{}/ansiblejobs-{}.stats".format(cliargs.results_directory, ts)

  oc_cmd = ["oc", "get", "ansiblejobs", "-A", "-o", "json"]
  rc, output = command(oc_cmd, False, retries=3, no_log=True)
  if rc != 0:
    logger.error("analyze-ansiblejobs, oc get ansiblejobs rc: {}".format(rc))
    sys.exit(1)
  aj_data = json.loads(output)

  logger.info("Writing CSV: {}".format(aj_csv_file))
  with open(aj_csv_file, "w") as csv_file:
    csv_file.write("name,tower_id,target_count,status,changed,failed,elapsed,creationTimestamp,started,finished,complete_duration,create_started_duration,started_finished_duration\n")

  for item in aj_data["items"]:
    aj_name = item["metadata"]["name"]
    aj_creationTimestamp = item["metadata"]["creationTimestamp"]
    aj_tower_id = item["metadata"]["labels"]["tower_job_id"]
    aj_target_count = len(item["spec"]["extra_vars"]["target_clusters"])

    aj_result_changed = item["status"]["ansibleJobResult"]["changed"]
    aj_result_status = item["status"]["ansibleJobResult"]["status"]
    aj_result_failed = item["status"]["ansibleJobResult"]["failed"]
    aj_result_started = item["status"]["ansibleJobResult"]["started"]
    aj_result_finished = item["status"]["ansibleJobResult"]["finished"]
    aj_result_elapsed = item["status"]["ansibleJobResult"]["elapsed"]

    created_dt = datetime.strptime(aj_creationTimestamp, "%Y-%m-%dT%H:%M:%SZ")
    started_dt = datetime.strptime(aj_result_started, "%Y-%m-%dT%H:%M:%S.%fZ")
    finished_dt = datetime.strptime(aj_result_finished, "%Y-%m-%dT%H:%M:%S.%fZ")
    complete_duration = (finished_dt - created_dt).total_seconds()
    create_started_duration = (started_dt - created_dt).total_seconds()
    started_finished_duration = (finished_dt - started_dt).total_seconds()

    with open(aj_csv_file, "a") as csv_file:
      csv_file.write("{},{},{},{},{},{},{},{},{},{},{},{},{}\n".format(
          aj_name, aj_tower_id, aj_target_count, aj_result_status, aj_result_changed, aj_result_failed,
          aj_result_elapsed, aj_creationTimestamp, aj_result_started, aj_result_finished, complete_duration,
          create_started_duration, started_finished_duration))

  # Stats oin jobs not determined yet
  # logger.info("Writing Stats: {}".format(aj_stats_file))
  # stats_count = len(aci_installcompleted_values)
  # stats_min = 0
  # stats_avg = 0
  # stats_50p = 0
  # stats_95p = 0
  # stats_99p = 0
  # stats_max = 0
  # if stats_count > 0:
  #   stats_min = np.min(aci_installcompleted_values)
  #   stats_avg = round(np.mean(aci_installcompleted_values), 1)
  #   stats_50p = round(np.percentile(aci_installcompleted_values, 50), 1)
  #   stats_95p = round(np.percentile(aci_installcompleted_values, 95), 1)
  #   stats_99p = round(np.percentile(aci_installcompleted_values, 99), 1)
  #   stats_max = np.max(aci_installcompleted_values)
  #
  # with open(aj_stats_file, "w") as stats_file:
  #   log_write(stats_file, "Stats only on AgentClusterInstall CRs in InstallationCompleted")
  #   log_write(stats_file, "Count: {}".format(stats_count))
  #   log_write(stats_file, "Min: {}".format(stats_min))
  #   log_write(stats_file, "Average: {}".format(stats_avg))
  #   log_write(stats_file, "50 percentile: {}".format(stats_50p))
  #   log_write(stats_file, "95 percentile: {}".format(stats_95p))
  #   log_write(stats_file, "99 percentile: {}".format(stats_99p))
  #   log_write(stats_file, "Max: {}".format(stats_max))

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
