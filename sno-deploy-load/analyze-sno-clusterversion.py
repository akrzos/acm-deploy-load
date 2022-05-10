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
  cv_csv_file = "{}/sno-clusterversion.csv".format(cliargs.results_directory)
  cv_stats_file = "{}/sno-clusterversion.stats".format(cliargs.results_directory)

  oc_cmd = ["oc", "get", "agentclusterinstalls", "-A", "-o", "json"]
  rc, output = command(oc_cmd, False, retries=3, no_log=True)
  if rc != 0:
    logger.error("analyze-agentclusterinstalls, oc get agentclusterinstalls rc: {}".format(rc))
    sys.exit(1)
  aci_data = json.loads(output)

  snos = []
  sno_ver_data = OrderedDict()

  for item in aci_data["items"]:
    aci_name = item["metadata"]["name"]
    for condition in item["status"]["conditions"]:
      if condition["type"] == "Completed":
        if condition["status"] == "True":
          if condition["reason"] == "InstallationCompleted":
            snos.append(aci_name)
        break;

  logger.info("Number of SNO clusterversions to examine: {}".format(len(snos)))

  with open(cv_csv_file, "w") as csv_file:
    csv_file.write("name,version,state,startedTime,completionTime,duration\n")

  for sno in snos:
    kubeconfig = "{}/{}/kubeconfig".format(cliargs.sno_manifests, sno)
    oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "clusterversion", "version", "-o", "json"]
    rc, output = command(oc_cmd, False, retries=2, no_log=True)
    if rc != 0:
      logger.error("analyze-sno-clusterversion, oc get clusterdeployment rc: {}".format(rc))
      continue
    cv_data = json.loads(output)

    for ver_hist_entry in cv_data["status"]["history"]:
      sno_cv_version = ver_hist_entry["version"]
      sno_cv_state = ver_hist_entry["state"]
      sno_cv_startedtime = ver_hist_entry["startedTime"]
      sno_cv_completiontime = ""
      sno_cv_duration = ""
      if sno_cv_state == "Completed":
        sno_cv_completiontime = ver_hist_entry["completionTime"]
        start = datetime.strptime(sno_cv_startedtime, "%Y-%m-%dT%H:%M:%SZ")
        end = datetime.strptime(sno_cv_completiontime, "%Y-%m-%dT%H:%M:%SZ")
        sno_cv_duration = (end - start).total_seconds()
        if sno_cv_version not in sno_ver_data:
          sno_ver_data[sno_cv_version] = []
        sno_ver_data[sno_cv_version].append(sno_cv_duration)
      with open(cv_csv_file, "a") as csv_file:
        csv_file.write("{},{},{},{},{},{}\n".format(sno, sno_cv_version, sno_cv_state, sno_cv_startedtime, sno_cv_completiontime, sno_cv_duration))

  logger.info("Stats only on clusterversion in Completed state")
  with open(cv_stats_file, "w") as stats_file:
    stats_file.write("Stats only on clusterversion in Completed state\n")

  for version in sno_ver_data:
    logger.info("Analyzing Version: {}".format(version))
    logger.info("Count: {}".format(len(sno_ver_data[version])))
    logger.info("Min: {}".format(np.min(sno_ver_data[version])))
    logger.info("Average: {}".format(round(np.mean(sno_ver_data[version]), 1)))
    logger.info("50 percentile: {}".format(round(np.percentile(sno_ver_data[version], 50), 1)))
    logger.info("95 percentile: {}".format(round(np.percentile(sno_ver_data[version], 95), 1)))
    logger.info("99 percentile: {}".format(round(np.percentile(sno_ver_data[version], 99), 1)))
    logger.info("Max: {}".format(np.max(sno_ver_data[version])))

    with open(cv_stats_file, "a") as stats_file:
      stats_file.write("Analyzing Version: {}\n".format(version))
      stats_file.write("Count: {}\n".format(len(sno_ver_data[version])))
      stats_file.write("Min: {}\n".format(np.min(sno_ver_data[version])))
      stats_file.write("Average: {}\n".format(round(np.mean(sno_ver_data[version]), 1)))
      stats_file.write("50 percentile: {}\n".format(round(np.percentile(sno_ver_data[version], 50), 1)))
      stats_file.write("95 percentile: {}\n".format(round(np.percentile(sno_ver_data[version], 95), 1)))
      stats_file.write("99 percentile: {}\n".format(round(np.percentile(sno_ver_data[version], 99), 1)))
      stats_file.write("Max: {}\n".format(np.max(sno_ver_data[version])))

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))


if __name__ == "__main__":
  sys.exit(main())
