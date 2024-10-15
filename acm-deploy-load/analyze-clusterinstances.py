#!/usr/bin/env python3
#
# Analyze ClusterInstance data on a hub cluster to determine count/min/avg/max/50p/95p/99p timings
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
      description="Analyze ClusterInstance data",
      prog="analyze-clusterinstances.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("-o", "--offline-process", action="store_true", default=False,
                      help="Uses previously stored raw data")
  parser.add_argument("-r", "--raw-data-file", type=str, default="",
                    help="Set raw json data file for offline processing. Empty finds last file")
  parser.add_argument("results_directory", type=str, help="The location to place analyzed data")
  cliargs = parser.parse_args()

  logger.info("Analyze clusterinstances")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")

  raw_data_file = "{}/clusterinstances-{}.json".format(cliargs.results_directory, ts)
  if cliargs.offline_process:
    if cliargs.raw_data_file == "":
      # Detect last raw data file
      dir_scan = sorted([ f.path for f in os.scandir(cliargs.results_directory) if f.is_file() and "clusterinstances" in f.path and "json" in f.path ])
      if len(dir_scan) == 0:
        logger.error("No previous offline file found. Exiting")
        sys.exit(1)
      raw_data_file = dir_scan[-1]
    else:
      raw_data_file = cliargs.raw_data_file
    logger.info("Reading raw data from: {}".format(raw_data_file))
  else:
    logger.info("Storing raw data file at: {}".format(raw_data_file))

  ci_csv_file = "{}/clusterinstances-{}.csv".format(cliargs.results_directory, ts)
  ci_stats_file = "{}/clusterinstances-{}.stats".format(cliargs.results_directory, ts)

  if not cliargs.offline_process:
    oc_cmd = ["oc", "get", "clusterinstances", "-A", "-o", "json"]
    rc, output = command(oc_cmd, False, retries=3, no_log=True)
    if rc != 0:
      logger.error("analyze-clusterinstances, oc get clusterinstances rc: {}".format(rc))
      sys.exit(1)
    with open(raw_data_file, "w") as ci_data_file:
      ci_data_file.write(output)
  with open(raw_data_file, "r") as ci_file_data:
    ci_data = json.load(ci_file_data)

  logger.info("Writing CSV: {}".format(ci_csv_file))
  with open(ci_csv_file, "w") as csv_file:
    csv_file.write("name,status,creationTimestamp,ClusterInstanceValidated.lastTransitionTime,"
        "RenderedTemplates.lastTransitionTime,RenderedTemplatesValidated.lastTransitionTime,"
        "RenderedTemplatesApplied.lastTransitionTime,Provisioned.lastTransitionTime,"
        "ci_ct_iv_duration,ci_iv_rt_duration,ci_rt_rtv_duration,ci_rtv_rta_duration,"
        "ci_rta_p_duration,total_duration\n")

  ci_instancevalidated_durations = []
  ci_provisioned_durations = []
  for item in ci_data["items"]:
    ci_name = item["metadata"]["name"]
    ci_status = "unknown"
    ci_creationTimestamp = datetime.strptime(item["metadata"]["creationTimestamp"], "%Y-%m-%dT%H:%M:%SZ")
    ci_instancevalidated_ts = ""
    ci_renderedtemplates_ts = ""
    ci_renderedtemplatesvalidated_ts = ""
    ci_renderedtemplatesapplied_ts = ""
    ci_provisioned_ts = ""

    if "status" in item and "conditions" in item["status"]:
      for condition in item["status"]["conditions"]:
        if "type" in condition and "status" in condition:
          if condition["type"] == "ClusterInstanceValidated" and condition["status"] == "True":
            ci_instancevalidated_ts = datetime.strptime(condition["lastTransitionTime"], "%Y-%m-%dT%H:%M:%SZ")
          elif condition["type"] == "RenderedTemplates" and condition["status"] == "True":
            ci_renderedtemplates_ts = datetime.strptime(condition["lastTransitionTime"], "%Y-%m-%dT%H:%M:%SZ")
          elif condition["type"] == "RenderedTemplatesValidated" and condition["status"] == "True":
            ci_renderedtemplatesvalidated_ts = datetime.strptime(condition["lastTransitionTime"], "%Y-%m-%dT%H:%M:%SZ")
          elif condition["type"] == "RenderedTemplatesApplied" and condition["status"] == "True":
            ci_renderedtemplatesapplied_ts = datetime.strptime(condition["lastTransitionTime"], "%Y-%m-%dT%H:%M:%SZ")
          elif condition["type"] == "Provisioned" and condition["status"] == "True":
            ci_provisioned_ts = datetime.strptime(condition["lastTransitionTime"], "%Y-%m-%dT%H:%M:%SZ")
            ci_status = "Provisioned"
        else:
          logger.warning("ICI: {}, 'type' or 'status' missing in condition: {}".format(ici_name, condition))
    else:
      logger.warning("status or conditions not found in imageclusterinstall object: {}".format(item))

    logger.info("{}, {}, {}, {}, {}, {}, {}, {}".format(
        ci_name, ci_status, ci_creationTimestamp, ci_instancevalidated_ts, ci_renderedtemplates_ts,
        ci_renderedtemplatesvalidated_ts, ci_renderedtemplatesapplied_ts, ci_provisioned_ts))

    ci_ct_iv_duration = (ci_instancevalidated_ts - ci_creationTimestamp).total_seconds()
    ci_iv_rt_duration = (ci_renderedtemplates_ts - ci_instancevalidated_ts).total_seconds()
    if ci_renderedtemplatesvalidated_ts != "":
      ci_rt_rtv_duration = (ci_renderedtemplatesvalidated_ts - ci_renderedtemplates_ts).total_seconds()
    else:
      ci_rt_rtv_duration = 0
    if ci_renderedtemplatesvalidated_ts != "" and ci_renderedtemplatesapplied_ts != "":
      ci_rtv_rta_duration = (ci_renderedtemplatesapplied_ts - ci_renderedtemplatesvalidated_ts).total_seconds()
    else:
      ci_rtv_rta_duration = 0
    if ci_renderedtemplatesapplied_ts != "" and ci_provisioned_ts != "":
      ci_rta_p_duration = (ci_provisioned_ts - ci_renderedtemplatesapplied_ts).total_seconds()
    else:
      ci_rta_p_duration = 0
    if ci_provisioned_ts != "":
      total_duration = (ci_provisioned_ts - ci_creationTimestamp).total_seconds()
    else:
      total_duration = 0

    ci_instancevalidated_durations.append(ci_ct_iv_duration)
    if ci_status == "Provisioned":
      ci_provisioned_durations.append(total_duration)

    # logger.info("Durations: {}, {}, {}, {}, {}, {}".format(
    #     ci_ct_iv_duration, ci_iv_rt_duration, ci_rt_rtv_duration, ci_rtv_rta_duration,
    #     ci_rta_p_duration, total_duration))

    with open(ci_csv_file, "a") as csv_file:
      csv_file.write(
          "{},{},{},{},{},{},{},{},{},{},{},{},{},{}\n".format(ci_name, ci_status,
          ci_creationTimestamp, ci_instancevalidated_ts, ci_renderedtemplates_ts,
          ci_renderedtemplatesvalidated_ts, ci_renderedtemplatesapplied_ts, ci_provisioned_ts,
          ci_ct_iv_duration, ci_iv_rt_duration, ci_rt_rtv_duration, ci_rtv_rta_duration,
          ci_rta_p_duration, total_duration))

  logger.info("Writing Stats: {}".format(ci_stats_file))

  with open(ci_stats_file, "w") as stats_file:
    stats_count = len(ci_instancevalidated_durations)
    stats_min = 0
    stats_avg = 0
    stats_50p = 0
    stats_95p = 0
    stats_99p = 0
    stats_max = 0
    if stats_count > 0:
      stats_min = np.min(ci_instancevalidated_durations)
      stats_avg = round(np.mean(ci_instancevalidated_durations), 1)
      stats_50p = round(np.percentile(ci_instancevalidated_durations, 50), 1)
      stats_95p = round(np.percentile(ci_instancevalidated_durations, 95), 1)
      stats_99p = round(np.percentile(ci_instancevalidated_durations, 99), 1)
      stats_max = np.max(ci_instancevalidated_durations)
    log_write(stats_file, "Stats on ClusterInstances CRs with CreationTimeStamp until InstanceValidated Timestamp")
    log_write(stats_file, "Count: {}".format(stats_count))
    log_write(stats_file, "Min: {}".format(stats_min))
    log_write(stats_file, "Average: {}".format(stats_avg))
    log_write(stats_file, "50 percentile: {}".format(stats_50p))
    log_write(stats_file, "95 percentile: {}".format(stats_95p))
    log_write(stats_file, "99 percentile: {}".format(stats_99p))
    log_write(stats_file, "Max: {}".format(stats_max))

    stats_count = len(ci_provisioned_durations)
    stats_min = 0
    stats_avg = 0
    stats_50p = 0
    stats_95p = 0
    stats_99p = 0
    stats_max = 0
    if stats_count > 0:
      stats_min = np.min(ci_provisioned_durations)
      stats_avg = round(np.mean(ci_provisioned_durations), 1)
      stats_50p = round(np.percentile(ci_provisioned_durations, 50), 1)
      stats_95p = round(np.percentile(ci_provisioned_durations, 95), 1)
      stats_99p = round(np.percentile(ci_provisioned_durations, 99), 1)
      stats_max = np.max(ci_provisioned_durations)
    log_write(stats_file, "Total Duration Stats only on ClusterInstances CRs in Provisioned")
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
