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
logger = logging.getLogger("analyze-sno-clusterversion")
logging.Formatter.converter = time.gmtime


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Analyze Each SNOs clusterversion data",
      prog="analyze-sno-clusterversion.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("-m", "--sno-manifests", type=str, default="/root/hv-sno/manifests",
                      help="The location of the SNO manifests, where kubeconfig is nested under each SNO directory")
  parser.add_argument("results_directory", type=str, help="The location to place analyzed data")
  cliargs = parser.parse_args()

  logger.info("Analyze sno-clusterversion")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")
  cv_csv_file = "{}/sno-clusterversion-{}.csv".format(cliargs.results_directory, ts)
  cv_stats_file = "{}/sno-clusterversion-{}.stats".format(cliargs.results_directory, ts)

  oc_cmd = ["oc", "get", "agentclusterinstalls", "-A", "-o", "json"]
  rc, output = command(oc_cmd, False, retries=3, no_log=True)
  if rc != 0:
    logger.error("analyze-agentclusterinstalls, oc get agentclusterinstalls rc: {}".format(rc))
    sys.exit(1)
  aci_data = json.loads(output)

  snos = []
  snos_total = 0
  snos_unreachable = []
  snos_ver_data = OrderedDict()

  for item in aci_data["items"]:
    aci_name = item["metadata"]["name"]
    for condition in item["status"]["conditions"]:
      if condition["type"] == "Completed":
        if condition["status"] == "True":
          if condition["reason"] == "InstallationCompleted":
            snos.append(aci_name)
        break;

  snos_total = len(snos)
  logger.info("Number of SNO clusterversions to examine: {}".format(snos_total))

  logger.info("Writing CSV: {}".format(cv_csv_file))
  with open(cv_csv_file, "w") as csv_file:
    csv_file.write("name,version,state,startedTime,completionTime,duration\n")

  for sno in snos:
    kubeconfig = "{}/{}/kubeconfig".format(cliargs.sno_manifests, sno)
    oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "clusterversion", "version", "-o", "json"]
    rc, output = command(oc_cmd, False, retries=2, no_log=True)
    if rc != 0:
      logger.error("analyze-sno-clusterversion, oc get clusterversion rc: {}".format(rc))
      snos_unreachable.append(sno)
      with open(cv_csv_file, "a") as csv_file:
        csv_file.write("{},NA,NA,,,\n".format(sno))
      continue
    cv_data = json.loads(output)

    for ver_hist_entry in cv_data["status"]["history"]:
      sno_cv_version = ver_hist_entry["version"]
      sno_cv_state = ver_hist_entry["state"]
      sno_cv_startedtime = ver_hist_entry["startedTime"]
      sno_cv_completiontime = ""
      sno_cv_duration = ""
      if sno_cv_version not in snos_ver_data:
        snos_ver_data[sno_cv_version] = {}
        snos_ver_data[sno_cv_version]["completed_durations"] = []
        snos_ver_data[sno_cv_version]["state"] = {}
        snos_ver_data[sno_cv_version]["count"] = 0
      if sno_cv_state not in snos_ver_data[sno_cv_version]["state"]:
        snos_ver_data[sno_cv_version]["state"][sno_cv_state] = []
      if sno not in snos_ver_data[sno_cv_version]["state"][sno_cv_state]:
        snos_ver_data[sno_cv_version]["state"][sno_cv_state].append(sno)
        snos_ver_data[sno_cv_version]["count"] += 1
      if sno_cv_state == "Completed":
        sno_cv_completiontime = ver_hist_entry["completionTime"]
        start = datetime.strptime(sno_cv_startedtime, "%Y-%m-%dT%H:%M:%SZ")
        end = datetime.strptime(sno_cv_completiontime, "%Y-%m-%dT%H:%M:%SZ")
        sno_cv_duration = (end - start).total_seconds()
        snos_ver_data[sno_cv_version]["completed_durations"].append(sno_cv_duration)
      with open(cv_csv_file, "a") as csv_file:
        csv_file.write("{},{},{},{},{},{}\n".format(sno, sno_cv_version, sno_cv_state, sno_cv_startedtime, sno_cv_completiontime, sno_cv_duration))

  percent_unreachable = round((len(snos_unreachable) / snos_total) * 100, 1)

  logger.info("Writing Stats: {}".format(cv_stats_file))
  logger.info("Stats only on clusterversion in Completed state")
  logger.info("Total SNOs: {}".format(snos_total))
  logger.info("Unreachable SNOs Count: {}".format(len(snos_unreachable)))
  logger.info("Unreachable SNOs Percent: {}%".format(percent_unreachable))
  logger.info("Unreachable SNOs: {}".format(snos_unreachable))
  with open(cv_stats_file, "w") as stats_file:
    stats_file.write("Stats only on clusterversion in Completed state\n")
    stats_file.write("Total SNOs: {}\n".format(snos_total))
    stats_file.write("Unreachable SNOs Count: {}\n".format(len(snos_unreachable)))
    stats_file.write("Unreachable SNOs Percent: {}%\n".format(percent_unreachable))
    stats_file.write("Unreachable SNOs: {}\n".format(snos_unreachable))

  for version in snos_ver_data:
    logger.info("#############################################")
    logger.info("Analyzing Version: {}".format(version))
    logger.info("Total entries: {}".format(snos_ver_data[version]["count"]))
    for state in snos_ver_data[version]["state"]:
      percent_of_total = round((len(snos_ver_data[version]["state"][state]) / snos_ver_data[version]["count"]) * 100, 1)
      if state != "Completed":
        logger.info("State: {}, Count: {}, Percent: {}%, SNOs: {}".format(state, len(snos_ver_data[version]["state"][state]), percent_of_total, snos_ver_data[version]["state"][state]))
      else:
        logger.info("State: {}, Count: {}, Percent: {}%".format(state, len(snos_ver_data[version]["state"][state]), percent_of_total))
    logger.info("Min: {}".format(np.min(snos_ver_data[version]["completed_durations"])))
    logger.info("Average: {}".format(round(np.mean(snos_ver_data[version]["completed_durations"]), 1)))
    logger.info("50 percentile: {}".format(round(np.percentile(snos_ver_data[version]["completed_durations"], 50), 1)))
    logger.info("95 percentile: {}".format(round(np.percentile(snos_ver_data[version]["completed_durations"], 95), 1)))
    logger.info("99 percentile: {}".format(round(np.percentile(snos_ver_data[version]["completed_durations"], 99), 1)))
    logger.info("Max: {}".format(np.max(snos_ver_data[version]["completed_durations"])))

    with open(cv_stats_file, "a") as stats_file:
      stats_file.write("#############################################\n")
      stats_file.write("Analyzing Version: {}\n".format(version))
      stats_file.write("Total entries: {}\n".format(snos_ver_data[version]["count"]))
      for state in snos_ver_data[version]["state"]:
        percent_of_total = round((len(snos_ver_data[version]["state"][state]) / snos_ver_data[version]["count"]) * 100, 1)
        if state != "Completed":
          stats_file.write("State: {}, Count: {}, Percent: {}%, SNOs: {}\n".format(state, len(snos_ver_data[version]["state"][state]), percent_of_total, snos_ver_data[version]["state"][state]))
        else:
          stats_file.write("State: {}, Count: {}, Percent: {}%\n".format(state, len(snos_ver_data[version]["state"][state]), percent_of_total))
      stats_file.write("Min: {}\n".format(np.min(snos_ver_data[version]["completed_durations"])))
      stats_file.write("Average: {}\n".format(round(np.mean(snos_ver_data[version]["completed_durations"]), 1)))
      stats_file.write("50 percentile: {}\n".format(round(np.percentile(snos_ver_data[version]["completed_durations"], 50), 1)))
      stats_file.write("95 percentile: {}\n".format(round(np.percentile(snos_ver_data[version]["completed_durations"], 95), 1)))
      stats_file.write("99 percentile: {}\n".format(round(np.percentile(snos_ver_data[version]["completed_durations"], 99), 1)))
      stats_file.write("Max: {}\n".format(np.max(snos_ver_data[version]["completed_durations"])))

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))


if __name__ == "__main__":
  sys.exit(main())
