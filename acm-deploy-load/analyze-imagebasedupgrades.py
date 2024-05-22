#!/usr/bin/env python3
#
# Analyze ClusterGroupUpgrade and ImageBasedUpgrade data on hub and spoke clusters to determine upgrade
# count/min/avg/max/50p/95p/99p timings and success rate
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
from collections import OrderedDict
from datetime import datetime
from datetime import timedelta
import json
import logging
import os
from pathlib import Path
from utils.command import command
from utils.output import assemble_stats
from utils.output import log_write
import sys
import time


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def examine_ibu_cgu(stages, stage, cgu_data, ibu_cgu_csv_file):
  stages[stage] = {}
  stages[stage]["cgus"] = {}
  stages[stage]["cgus_count"] = len(cgu_data["items"])
  stages[stage]["cgus_completed_count"] = 0
  stages[stage]["cgus_timedout_count"] = 0
  stages[stage]["creationTimestamp"] = ""
  stages[stage]["startedAt"] = ""
  stages[stage]["completedAt"] = ""
  stages[stage]["succeeded_durations"] = []
  stages[stage]["ibu_succeeded_durations"] = []
  stages[stage]["batches_count"] = 0
  stages[stage]["clusters_count"] = 0
  stages[stage]["clusters_completed_count"] = 0
  stages[stage]["clusters_timedout_count"] = 0
  stages[stage]["clusters_timedout"] = []

  current_stage_completed_clusters = []

  for item in cgu_data["items"]:
    cgu_name = item["metadata"]["name"]
    cgu_status = "unknown"
    cgu_created = datetime.strptime(item["metadata"]["creationTimestamp"], "%Y-%m-%dT%H:%M:%SZ")
    cgu_startedAt = ""
    cgu_completedAt = ""
    cgu_duration = 0
    cgu_clusters_max_concurrency = item["spec"]["remediationStrategy"]["maxConcurrency"]
    cgu_timeout = item["spec"]["remediationStrategy"]["timeout"]
    cgu_batches_count = 0
    cgu_clusters_count = 0
    cgu_clusters_completed_count = 0
    cgu_clusters_timedout_count = 0
    cgu_clusters_timedout = []
    logger.info("Name: {}".format(cgu_name))
    if stages[stage]["creationTimestamp"] == "":
      stages[stage]["creationTimestamp"] = cgu_created
    elif stages[stage]["creationTimestamp"] > cgu_created:
      logger.info("Replacing cgu created time {} with earlier time {}".format(stages[stage]["creationTimestamp"], cgu_created))
      stages[stage]["creationTimestamp"] = cgu_created
    if "startedAt" in item["status"]["status"]:
      # Determine earliest startedAt time for the cgus in this namespace
      cgu_startedAt = datetime.strptime(item["status"]["status"]["startedAt"], "%Y-%m-%dT%H:%M:%SZ")
      if stages[stage]["startedAt"] == "":
        stages[stage]["startedAt"] = cgu_startedAt
      elif stages[stage]["startedAt"] > cgu_startedAt:
        logger.info("Replacing cgu started time {} with earlier time {}".format(stages[stage]["startedAt"], cgu_startedAt))
        stages[stage]["startedAt"] = cgu_startedAt
    if "completedAt" in item["status"]["status"]:
      # Determine latest populated completed time
      cgu_completedAt = datetime.strptime(item["status"]["status"]["completedAt"], "%Y-%m-%dT%H:%M:%SZ")
      if stages[stage]["completedAt"] == "":
        stages[stage]["completedAt"] = cgu_completedAt
      elif stages[stage]["completedAt"] < cgu_completedAt:
        logger.info("Replacing cgu completed time {} with later time {}".format(stages[stage]["completedAt"], cgu_completedAt))
        stages[stage]["completedAt"] = cgu_completedAt
      cgu_duration = (cgu_completedAt - cgu_startedAt).total_seconds()

    if "conditions" in item["status"]:
      for condition in item["status"]["conditions"]:
        if "type" in condition:
          if (condition["type"] == "Progressing" and condition["status"] == "False"
              and condition["reason"] != "Completed" and condition["reason"] != "TimedOut"):
            cgu_status = "NotStarted"
          if condition["type"] == "Progressing" and condition["status"] == "True" and condition["reason"] == "InProgress":
            cgu_status = "InProgress"
          if condition["type"] == "Succeeded" and condition["status"] == "False" and condition["reason"] == "TimedOut":
            cgu_status = "TimedOut"
            stages[stage]["cgus_timedout_count"] += 1
          if condition["type"] == "Succeeded" and condition["status"] == "True" and condition["reason"] == "Completed":
            cgu_status = "Completed"
            stages[stage]["cgus_completed_count"] += 1
            stages[stage]["succeeded_durations"].append(cgu_duration)

    if "clusters" in item["status"]:
      cgu_clusters_count = len(item["status"]["clusters"])
      for cluster in item["status"]["clusters"]:
        if cluster["state"] == "complete":
          cgu_clusters_completed_count += 1
          current_stage_completed_clusters.append(cluster["name"])
        elif cluster["state"] == "timedout":
          cgu_clusters_timedout_count += 1
          cgu_clusters_timedout.append(cluster["name"])
        else:
          logger.warn("Unexpected cluster state: {}".format(cluster["state"]))

      stages[stage]["clusters_count"] += cgu_clusters_count
      stages[stage]["clusters_completed_count"] += cgu_clusters_completed_count
      stages[stage]["clusters_timedout_count"] += cgu_clusters_timedout_count
      stages[stage]["clusters_timedout"].extend(cgu_clusters_timedout)

    stages[stage]["cgus"][cgu_name] = {}
    stages[stage]["cgus"][cgu_name]["remediationPlan"] = OrderedDict()

    # cgu_batches_count = cgu_clusters_count // cgu_clusters_max_concurrency
    # if (cgu_clusters_count % cgu_clusters_max_concurrency) > 0:
    #   cgu_batches_count += 1
    # stages[stage]["batches_count"] += cgu_batches_count
    #
    # for idx, cluster in enumerate(item["spec"]["clusters"]):
    #   batch_index = idx // cgu_clusters_max_concurrency
    #   if str(batch_index) not in stages[stage]["cgus"][cgu_name]["remediationPlan"]:
    #     stages[stage]["cgus"][cgu_name]["remediationPlan"][str(batch_index)] = {}
    #   stages[stage]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster] = {}
    #   if cluster in current_stage_completed_clusters:
    #     stages[stage]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["status"] = "succeeded"
    #   else:
    #     stages[stage]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["status"] = "timedout"
    #   if stage == "prep":
    #     stages[stage]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["prepStarted"] = ""
    #     stages[stage]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["prepCompleted"] = ""
    #   elif stage == "upgrade":
    #     stages[stage]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["cguStarted"] = cgu_startedAt
    #     stages[stage]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["upgradeCompleted"] = ""
    #   stages[stage]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["duration"] = 0

    if "remediationPlan" in item["status"]:
      cgu_batches_count = len(item["status"]["remediationPlan"])
      stages[stage]["batches_count"] += cgu_batches_count
      for batch_index, batch in enumerate(item["status"]["remediationPlan"]):
        logger.info("Batch Index: {}, {} Clusters".format(batch_index, len(batch)))
        for cluster in sorted(batch):
          if str(batch_index) not in stages[stage]["cgus"][cgu_name]["remediationPlan"]:
            stages[stage]["cgus"][cgu_name]["remediationPlan"][str(batch_index)] = {}
          stages[stage]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster] = {}
          if cluster in current_stage_completed_clusters:
            stages[stage]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["status"] = "succeeded"
          else:
            stages[stage]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["status"] = "timedout"
          if stage == "prep":
            stages[stage]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["prepStarted"] = ""
            stages[stage]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["prepCompleted"] = ""
          elif stage == "upgrade":
            stages[stage]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["cguStarted"] = cgu_startedAt
            stages[stage]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["upgradeCompleted"] = ""
          elif stage == "rollback":
            stages[stage]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["rollbackStarted"] = cgu_startedAt
            stages[stage]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["rollbackCompleted"] = ""
          stages[stage]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["duration"] = 0

    with open(ibu_cgu_csv_file, "a") as csv_file:
      csv_file.write("{},{},{},{},{},{},{},{},{},{},{}\n".format(cgu_name, cgu_status, cgu_created, cgu_startedAt, cgu_completedAt, cgu_duration, cgu_timeout, cgu_batches_count, cgu_clusters_count, cgu_clusters_completed_count, cgu_clusters_timedout_count))

    stages[stage]["cgus"][cgu_name]["status"] = cgu_status
    stages[stage]["cgus"][cgu_name]["creationTimestamp"] = cgu_created
    stages[stage]["cgus"][cgu_name]["startedAt"] = cgu_startedAt
    stages[stage]["cgus"][cgu_name]["completedAt"] = cgu_completedAt
    stages[stage]["cgus"][cgu_name]["duration"] = cgu_duration
    stages[stage]["cgus"][cgu_name]["max_concurrency"] = cgu_clusters_max_concurrency
    stages[stage]["cgus"][cgu_name]["timeout"] = cgu_timeout
    stages[stage]["cgus"][cgu_name]["batches_count"] = cgu_batches_count
    stages[stage]["cgus"][cgu_name]["clusters_count"] = cgu_clusters_count
    stages[stage]["cgus"][cgu_name]["clusters_completed_count"] = cgu_clusters_completed_count
    stages[stage]["cgus"][cgu_name]["clusters_timedout_count"] = cgu_clusters_timedout_count
    stages[stage]["cgus"][cgu_name]["clusters_timedout"] = cgu_clusters_timedout


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Analyze ImageBasedUpgrade data",
      prog="analyze-imagebasedupgrades.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument("ocp_version", type=str, help="The expected version for clusters to have been upgraded to")
  parser.add_argument("results_directory", type=str, help="The location to place analyzed data")
  parser.add_argument("-n", "--namespace", type=str, default="ztp-platform-upgrade", help="Namespace of the CGUs to analyze")

  parser.add_argument("-p", "--prep-label", type=str, default="ibu-prep", help="Expected label to equal expected version for preparation cgu(s)")
  parser.add_argument("-u", "--upgrade-label", type=str, default="ibu-upgrade", help="Expected label to equal expected version for upgrade cgu(s)")
  parser.add_argument("-r", "--rollback-label", type=str, default="ibu-rollback", help="Expected label to equal expected version for rollback cgu(s)")
  parser.add_argument("-f", "--finalize-label", type=str, default="ibu-finalize", help="Expected label to equal expected version for finalize cgu(s)")

  parser.add_argument("--offline-process", action="store_true", default=False, help="Uses previously stored raw data")
  parser.add_argument("--raw-data-directory", type=str, default="",
                    help="Set raw data directory for offline processing. Empty finds last directory")
  parser.add_argument("-k", "--kubeconfigs", type=str, default="/root/hv-vm/kc",
                      help="The location of the kubeconfigs, nested under each cluster's directory")
  parser.add_argument("-ni", "--no-ibu-analysis", action="store_true", default=False, help="Skip analyzing individual IBU objects")
  cliargs = parser.parse_args()

  ibu_analysis = not cliargs.no_ibu_analysis

  logger.info("Analyze imagebasedupgrade")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")
  raw_data_dir = "{}/ibu-{}-cgu-{}".format(cliargs.results_directory, cliargs.ocp_version, ts)
  if cliargs.offline_process:
    if cliargs.raw_data_directory == "":
      # Detect last raw data directory
      dir_scan = sorted([ f.path for f in os.scandir(cliargs.results_directory) if f.is_dir() and "ibu-{}-cgu".format(cliargs.ocp_version) in f.path ])
      if len(dir_scan) == 0:
        logger.error("No previous offline directories found. Exiting")
        sys.exit(1)
      raw_data_dir = dir_scan[-1]
    else:
      raw_data_dir = cliargs.raw_data_directory
    logger.info("Reading raw data from: {}".format(raw_data_dir))
  else:
    Path(raw_data_dir).mkdir(parents=True, exist_ok=True)
    logger.info("Storing raw data in: {}".format(raw_data_dir))
  ibu_cgu_csv_file = "{}/ibu-{}-cgus-{}.csv".format(cliargs.results_directory, cliargs.ocp_version, ts)
  ibu_prep_csv_file = "{}/ibu-{}-prep-{}.csv".format(cliargs.results_directory, cliargs.ocp_version, ts)
  ibu_upgrade_csv_file = "{}/ibu-{}-upgrade-{}.csv".format(cliargs.results_directory, cliargs.ocp_version, ts)
  ibu_rollback_csv_file = "{}/ibu-{}-rollback-{}.csv".format(cliargs.results_directory, cliargs.ocp_version, ts)
  ibu_cgu_stats_file = "{}/ibu-{}-cgus-{}.stats".format(cliargs.results_directory, cliargs.ocp_version, ts)

  # Gather all CGU data for an IBU upgrade, Stage label = file
  gather_stages = OrderedDict()
  gather_stages[cliargs.prep_label] = "prep-cgus.json"
  gather_stages[cliargs.upgrade_label] = "upgrade-cgus.json"
  gather_stages[cliargs.rollback_label] = "rollback-cgus.json"
  gather_stages[cliargs.finalize_label] = "finalize-cgus.json"

  for stage_label in gather_stages:
    if not cliargs.offline_process:
      label_selector = "{}={}".format(stage_label, cliargs.ocp_version)
      oc_cmd = ["oc", "get", "clustergroupupgrades", "-n", cliargs.namespace, "-l", label_selector, "-o", "json"]
      rc, output = command(oc_cmd, False, retries=3, no_log=True)
      if rc != 0:
        logger.error("analyze-imagebasedupgrade, oc get clustergroupupgrades -n {} -l {} rc: {}".format(cliargs.namespace, label_selector, cliargs.ocp_version, rc))
        sys.exit(1)
      with open("{}/{}".format(raw_data_dir, gather_stages[stage_label]), "w") as cgu_data_file:
        cgu_data_file.write(output)

  logger.info("Reading {}/prep-cgus.json".format(raw_data_dir))
  with open("{}/prep-cgus.json".format(raw_data_dir), "r") as cgu_data_file:
    cgu_prep_data = json.load(cgu_data_file)

  logger.info("Reading {}/upgrade-cgus.json".format(raw_data_dir))
  with open("{}/upgrade-cgus.json".format(raw_data_dir), "r") as cgu_data_file:
    cgu_upgrade_data = json.load(cgu_data_file)

  logger.info("Reading {}/rollback-cgus.json".format(raw_data_dir))
  with open("{}/rollback-cgus.json".format(raw_data_dir), "r") as cgu_data_file:
    cgu_rollback_data = json.load(cgu_data_file)

  logger.info("Reading {}/finalize-cgus.json".format(raw_data_dir))
  with open("{}/finalize-cgus.json".format(raw_data_dir), "r") as cgu_data_file:
    cgu_finalize_data = json.load(cgu_data_file)

  # Examine all cgu data for a complete IBU upgrade
  stages = OrderedDict()
  ibus = []

  if len(cgu_prep_data["items"]) == 0:
    logger.error("No prep cgu(s) to examine")
    sys.exit(1)

  logger.info("Writing CSV: {}".format(ibu_cgu_csv_file))
  with open(ibu_cgu_csv_file, "w") as csv_file:
    csv_file.write("name,status,creationTimestamp,startedAt,completedAt,duration,timeout,batchCount,clusterCount,clusterCompleted,clusterTimedout\n")

  logger.info("{} prep cgu(s) to examine".format(len(cgu_prep_data["items"])))
  examine_ibu_cgu(stages, "prep", cgu_prep_data, ibu_cgu_csv_file)
  # Use prep stage for all ibu data to collect
  for item in cgu_prep_data["items"]:
    for cluster in item["status"]["clusters"]:
      ibus.append(cluster["name"])
  ibus = sorted(ibus)

  if len(cgu_upgrade_data["items"]) == 0:
    logger.info("No upgrade cgu(s) to examine")
  else:
    logger.info("{} upgrade cgu(s) to examine".format(len(cgu_upgrade_data["items"])))
    examine_ibu_cgu(stages, "upgrade", cgu_upgrade_data, ibu_cgu_csv_file)

  if len(cgu_rollback_data["items"]) == 0:
    logger.info("No rollback cgu(s) to examine")
  else:
    logger.info("{} rollback cgu(s) to examine".format(len(cgu_rollback_data["items"])))
    examine_ibu_cgu(stages, "rollback", cgu_rollback_data, ibu_cgu_csv_file)

  if len(cgu_finalize_data["items"]) == 0:
    logger.info("No finalize cgu(s) to examine")
  else:
    logger.info("{} finalize cgu(s) to examine".format(len(cgu_finalize_data["items"])))
    examine_ibu_cgu(stages, "finalize", cgu_finalize_data, ibu_cgu_csv_file)

  if ibu_analysis:
    # Get individual cluster IBU data here
    for cluster in ibus:
      kubeconfig = "{}/{}/kubeconfig".format(cliargs.kubeconfigs, cluster)
      if not cliargs.offline_process:
        oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "ibu", "upgrade", "-o", "json"]
        rc, output = command(oc_cmd, False, retries=2, no_log=True)
        if rc != 0:
          logger.error("analyze-imagebasedupgrade, oc get ibu rc: {}".format(rc))
          output = ""
        with open("{}/{}-ibu.json".format(raw_data_dir, cluster), "w") as ibu_data_file:
          ibu_data_file.write(output)

      if os.stat("{}/{}-ibu.json".format(raw_data_dir, cluster)).st_size == 0:
        ibu_data = ""
      else:
        with open("{}/{}-ibu.json".format(raw_data_dir, cluster), "r") as ibu_data_file:
          ibu_data = json.load(ibu_data_file)

      # Determine timestamps from conditions in IBU data
      ibu_prep_started_time = ""
      ibu_prep_completed_time = ""
      ibu_upgrade_completed_time = ""
      if "status" in ibu_data:
        if "conditions" in ibu_data["status"]:
          for condition in ibu_data["status"]["conditions"]:
            if condition["type"] == "Idle":
              ibu_prep_started_time = datetime.strptime(condition["lastTransitionTime"], "%Y-%m-%dT%H:%M:%SZ")
            if condition["type"] == "PrepCompleted" and condition["status"] == "True":
              ibu_prep_completed_time = datetime.strptime(condition["lastTransitionTime"], "%Y-%m-%dT%H:%M:%SZ")
            if condition["type"] == "UpgradeCompleted" and condition["status"] == "True":
              ibu_upgrade_completed_time = datetime.strptime(condition["lastTransitionTime"], "%Y-%m-%dT%H:%M:%SZ")

      # Match timestamps from IBU data to the correct cluster
      for stage in stages:
        for cgu in stages[stage]["cgus"]:
          found_batch = False
          for batch in stages[stage]["cgus"][cgu]["remediationPlan"]:
            if cluster in stages[stage]["cgus"][cgu]["remediationPlan"][batch]:
              duration = 0
              if stage == "prep":
                stages[stage]["cgus"][cgu]["remediationPlan"][batch][cluster]["prepStarted"] = ibu_prep_started_time
                stages[stage]["cgus"][cgu]["remediationPlan"][batch][cluster]["prepCompleted"] = ibu_prep_completed_time
                if ibu_prep_started_time != "" and ibu_prep_completed_time != "":
                  duration = (ibu_prep_completed_time - ibu_prep_started_time).total_seconds()
              elif stage == "upgrade" and ibu_upgrade_completed_time != "":
                ibu_cgu_upgrade_started_time = stages[stage]["cgus"][cgu]["remediationPlan"][batch][cluster]["cguStarted"]
                stages[stage]["cgus"][cgu]["remediationPlan"][batch][cluster]["upgradeCompleted"] = ibu_upgrade_completed_time
                if ibu_upgrade_completed_time != "":
                  duration = (ibu_upgrade_completed_time - ibu_cgu_upgrade_started_time).total_seconds()
              stages[stage]["cgus"][cgu]["remediationPlan"][batch][cluster]["duration"] = duration
              if duration > 0:
                stages[stage]["ibu_succeeded_durations"].append(duration)
              found_batch = True
              break
          if found_batch:
            break
    # Write the IBU data to a CSV for prep stage
    logger.info("Writing CSV: {}".format(ibu_prep_csv_file))
    with open(ibu_prep_csv_file, "a") as csv_file:
      csv_file.write("name,status,cgu,batch,prepStarted,prepCompleted,duration\n")
      for cgu in stages["prep"]["cgus"]:
        for batch in stages["prep"]["cgus"][cgu]["remediationPlan"]:
          for cluster in stages["prep"]["cgus"][cgu]["remediationPlan"][batch]:
            status = stages["prep"]["cgus"][cgu]["remediationPlan"][batch][cluster]["status"]
            prep_started = stages["prep"]["cgus"][cgu]["remediationPlan"][batch][cluster]["prepStarted"]
            prep_completed = stages["prep"]["cgus"][cgu]["remediationPlan"][batch][cluster]["prepCompleted"]
            duration = stages["prep"]["cgus"][cgu]["remediationPlan"][batch][cluster]["duration"]
            # if duration == 0:
            #   logger.error("Cluster with 0 duration: {}".format(cluster))
            csv_file.write("{},{},{},{},{},{},{}\n".format(cluster, status, cgu, batch, prep_started, prep_completed, duration))

    # Write the IBU data to a CSV for upgrade stage
    if "upgrade" in stages:
      logger.info("Writing CSV: {}".format(ibu_upgrade_csv_file))
      with open(ibu_upgrade_csv_file, "a") as csv_file:
        csv_file.write("name,status,cgu,batch,cguStarted,upgradeCompleted,duration\n")
        for cgu in stages["upgrade"]["cgus"]:
          for batch in stages["upgrade"]["cgus"][cgu]["remediationPlan"]:
            for cluster in stages["upgrade"]["cgus"][cgu]["remediationPlan"][batch]:
              status = stages["upgrade"]["cgus"][cgu]["remediationPlan"][batch][cluster]["status"]
              cgu_started = stages["upgrade"]["cgus"][cgu]["remediationPlan"][batch][cluster]["cguStarted"]
              upgrade_completed = stages["upgrade"]["cgus"][cgu]["remediationPlan"][batch][cluster]["upgradeCompleted"]
              duration = stages["upgrade"]["cgus"][cgu]["remediationPlan"][batch][cluster]["duration"]
              csv_file.write("{},{},{},{},{},{},{}\n".format(cluster, status, cgu, batch, cgu_started, upgrade_completed, duration))
  # End ibu_analysis

  # Display summary of the collected CGU data
  logger.info("Writing Stats: {}".format(ibu_cgu_stats_file))
  with open(ibu_cgu_stats_file, "w") as stats_file:
    # log_write(stats_file, "#############################################")
    log_write(stats_file, "##########################################################################################")
    log_write(stats_file, "Stats on imagebasedupgrade clustergroupupgrades CRs in namespace {}".format(cliargs.namespace))
    log_write(stats_file, "Expected OCP Version {}".format(cliargs.ocp_version))
    cgu_total = sum([stages[x]["cgus_count"] for x in stages ])
    log_write(stats_file, "Total CGUs for all stages: {}".format(cgu_total))
    log_write(stats_file, "##########################################################################################")
    # log_write(stats_file, "#############################################")
    for stage in stages:
      stage_duration = (stages[stage]["completedAt"] - stages[stage]["creationTimestamp"]).total_seconds()
      log_write(stats_file, "Stage: {}".format(stage))
      cgus_completed_p = round(((stages[stage]["cgus_completed_count"] / stages[stage]["cgus_count"]) * 100), 1)
      cgus_timedout_p = round(((stages[stage]["cgus_timedout_count"] / stages[stage]["cgus_count"]) * 100), 1)
      log_write(stats_file, "CGUs: {} Total, {} Completed ({}%), {} TimedOut ({}%)".format(stages[stage]["cgus_count"], stages[stage]["cgus_completed_count"], cgus_completed_p, stages[stage]["cgus_timedout_count"], cgus_timedout_p))
      log_write(stats_file, "Count of Batches for stage: {}".format(stages[stage]["batches_count"]))
      clusters_completed_p = round(((stages[stage]["clusters_completed_count"] / stages[stage]["clusters_count"]) * 100), 1)
      clusters_timedout_p = round(((stages[stage]["clusters_timedout_count"] / stages[stage]["clusters_count"]) * 100), 1)
      log_write(stats_file, "Clusters: {} Total, {} completed ({}%), {} timedout ({}%)".format(stages[stage]["clusters_count"], stages[stage]["clusters_completed_count"], clusters_completed_p, stages[stage]["clusters_timedout_count"], clusters_timedout_p))
      log_write(stats_file, "Timedout Clusters: {}".format(stages[stage]["clusters_timedout"]))
      log_write(stats_file, "Earliest CGU creationTimestamp: {}".format(stages[stage]["creationTimestamp"]))
      log_write(stats_file, "Earliest CGU startedAt timestamp: {}".format(stages[stage]["startedAt"]))
      log_write(stats_file, "Latest CGU completedAt timestamp: {}".format(stages[stage]["completedAt"]))
      log_write(stats_file, "Stage duration: {}s :: {}".format(stage_duration, str(timedelta(seconds=stage_duration))))
      if len(stages[stage]["succeeded_durations"]) > 0:
        log_write(stats_file, "CGU Success Durations count: {}".format(len(stages[stage]["succeeded_durations"])))
        log_write(stats_file, "CGU Success Durations Min/Avg/50p/95p/99p/Max (seconds): {}".format(assemble_stats(stages[stage]["succeeded_durations"])))
        log_write(stats_file, "CGU Success Durations Min/Avg/50p/95p/99p/Max: {}".format(assemble_stats(stages[stage]["succeeded_durations"], False)))
      log_write(stats_file, "CGU IBU recorded Duration Total Count: {}".format(len(stages[stage]["ibu_succeeded_durations"])))
      log_write(stats_file, "CGU IBU Recorded Durations Min/Avg/50p/95p/99p/Max (seconds): {}".format(assemble_stats(stages[stage]["ibu_succeeded_durations"])))
      log_write(stats_file, "CGU IBU Recorded Durations Min/Avg/50p/95p/99p/Max: {}".format(assemble_stats(stages[stage]["ibu_succeeded_durations"], False)))
      for cgu in stages[stage]["cgus"]:
        log_write(stats_file, "#############################################")
        status = stages[stage]["cgus"][cgu]["status"]
        created = stages[stage]["cgus"][cgu]["creationTimestamp"]
        startedAt = stages[stage]["cgus"][cgu]["startedAt"]
        completedAt = stages[stage]["cgus"][cgu]["completedAt"]
        duration = stages[stage]["cgus"][cgu]["duration"]
        timeout = stages[stage]["cgus"][cgu]["timeout"]
        batches = stages[stage]["cgus"][cgu]["batches_count"]
        clusters = stages[stage]["cgus"][cgu]["clusters_count"]
        clusters_completed = stages[stage]["cgus"][cgu]["clusters_completed_count"]
        clusters_timedout = stages[stage]["cgus"][cgu]["clusters_timedout_count"]
        completed_p = round(((clusters_completed / clusters) * 100), 1)
        timedout_p = round(((clusters_timedout / clusters) * 100), 1)
        log_write(stats_file, "CGU: {}, Status: {}, Batches: {}".format(cgu, status, batches))
        log_write(stats_file, "Clusters: {}, completed: {} ({}%), timedout: {} ({}%)".format(clusters, clusters_completed, completed_p, clusters_timedout, timedout_p))
        log_write(stats_file, "Timedout Clusters: {}".format(stages[stage]["cgus"][cgu]["clusters_timedout"]))
        log_write(stats_file, "creationTimestamp: {}".format(created))
        log_write(stats_file, "startedAt: {}".format(startedAt))
        log_write(stats_file, "completedAt: {}".format(completedAt))
        log_write(stats_file, "Duration: {}s :: {}, Timeout: {}".format(duration, str(timedelta(seconds=duration)), timeout))
        for batch in stages[stage]["cgus"][cgu]["remediationPlan"]:
          b_clusters = len(stages[stage]["cgus"][cgu]["remediationPlan"][batch])
          recorded_durations = []
          for cluster in stages[stage]["cgus"][cgu]["remediationPlan"][batch]:
            if stages[stage]["cgus"][cgu]["remediationPlan"][batch][cluster]["duration"] > 0:
              recorded_durations.append(stages[stage]["cgus"][cgu]["remediationPlan"][batch][cluster]["duration"])
          log_write(stats_file, "Batch: {}, Clusters: {}, Recorded Samples: {}".format(batch, b_clusters, len(recorded_durations)))
          log_write(stats_file, "(IBU) Batch Recorded Durations Min/Avg/50p/95p/99p/Max (seconds): {}".format(assemble_stats(recorded_durations)))
          log_write(stats_file, "(IBU) Batch Recorded Durations Min/Avg/50p/95p/99p/Max: {}".format(assemble_stats(recorded_durations, False)))
      log_write(stats_file, "##########################################################################################")

  end_time = time.time()
  logger.info("##########################################################################################")
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
