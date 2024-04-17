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


def examine_ibu_cgu(phases, phase, cgu_data, ibu_cgu_csv_file):
  phases[phase] = {}
  phases[phase]["cgus"] = {}
  phases[phase]["cgus_count"] = len(cgu_data["items"])
  phases[phase]["cgus_completed_count"] = 0
  phases[phase]["cgus_timedout_count"] = 0
  phases[phase]["creationTimestamp"] = ""
  phases[phase]["startedAt"] = ""
  phases[phase]["completedAt"] = ""
  phases[phase]["succeeded_durations"] = []
  phases[phase]["batches_count"] = 0
  phases[phase]["clusters_count"] = 0
  phases[phase]["clusters_completed_count"] = 0
  phases[phase]["clusters_timedout_count"] = 0
  phases[phase]["clusters_timedout"] = []

  current_phase_completed_clusters = []

  for item in cgu_data["items"]:
    cgu_name = item["metadata"]["name"]
    cgu_status = "unknown"
    cgu_created = datetime.strptime(item["metadata"]["creationTimestamp"], "%Y-%m-%dT%H:%M:%SZ")
    cgu_startedAt = ""
    cgu_completedAt = ""
    cgu_duration = 0
    cgu_timeout = item["spec"]["remediationStrategy"]["timeout"]
    cgu_batches_count = 0
    cgu_clusters_count = 0
    cgu_clusters_completed_count = 0
    cgu_clusters_timedout_count = 0
    cgu_clusters_timedout = []
    logger.info("Name: {}".format(cgu_name))
    if phases[phase]["creationTimestamp"] == "":
      phases[phase]["creationTimestamp"] = cgu_created
    elif phases[phase]["creationTimestamp"] > cgu_created:
      logger.info("Replacing cgu created time {} with earlier time {}".format(phases[phase]["creationTimestamp"], cgu_created))
      phases[phase]["creationTimestamp"] = cgu_created
    if "startedAt" in item["status"]["status"]:
      # Determine earliest startedAt time for the cgus in this namespace
      cgu_startedAt = datetime.strptime(item["status"]["status"]["startedAt"], "%Y-%m-%dT%H:%M:%SZ")
      if phases[phase]["startedAt"] == "":
        phases[phase]["startedAt"] = cgu_startedAt
      elif phases[phase]["startedAt"] > cgu_startedAt:
        logger.info("Replacing cgu started time {} with earlier time {}".format(phases[phase]["startedAt"], cgu_startedAt))
        phases[phase]["startedAt"] = cgu_startedAt
    if "completedAt" in item["status"]["status"]:
      # Determine latest populated completed time
      cgu_completedAt = datetime.strptime(item["status"]["status"]["completedAt"], "%Y-%m-%dT%H:%M:%SZ")
      if phases[phase]["completedAt"] == "":
        phases[phase]["completedAt"] = cgu_completedAt
      elif phases[phase]["completedAt"] < cgu_completedAt:
        logger.info("Replacing cgu completed time {} with later time {}".format(phases[phase]["completedAt"], cgu_completedAt))
        phases[phase]["completedAt"] = cgu_completedAt
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
            phases[phase]["cgus_timedout_count"] += 1
          if condition["type"] == "Succeeded" and condition["status"] == "True" and condition["reason"] == "Completed":
            cgu_status = "Completed"
            phases[phase]["cgus_completed_count"] += 1
            phases[phase]["succeeded_durations"].append(cgu_duration)

    if "clusters" in item["status"]:
      cgu_clusters_total = len(item["status"]["clusters"])
      for cluster in item["status"]["clusters"]:
        if cluster["state"] == "complete":
          cgu_clusters_completed_count += 1
          current_phase_completed_clusters.append(cluster["name"])
        elif cluster["state"] == "timedout":
          cgu_clusters_timedout_count += 1
          cgu_clusters_timedout.append(cluster["name"])
        else:
          logger.warn("Unexpected cluster state: {}".format(cluster["state"]))

      phases[phase]["clusters_count"] += cgu_clusters_total
      phases[phase]["clusters_completed_count"] += cgu_clusters_completed_count
      phases[phase]["clusters_timedout_count"] += cgu_clusters_timedout_count
      phases[phase]["clusters_timedout"].extend(cgu_clusters_timedout)

    phases[phase]["cgus"][cgu_name] = {}
    phases[phase]["cgus"][cgu_name]["remediationPlan"] = OrderedDict()

    if "remediationPlan" in item["status"]:
      cgu_batches_count = len(item["status"]["remediationPlan"])
      phases[phase]["batches_count"] += cgu_batches_count
      for batch_index, batch in enumerate(item["status"]["remediationPlan"]):
        logger.info("Batch Index: {}, {} Clusters".format(batch_index, len(batch)))
        for cluster in sorted(batch):
          if str(batch_index) not in phases[phase]["cgus"][cgu_name]["remediationPlan"]:
            phases[phase]["cgus"][cgu_name]["remediationPlan"][str(batch_index)] = {}
          phases[phase]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster] = {}
          if cluster in current_phase_completed_clusters:
            phases[phase]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["status"] = "succeeded"
          else:
            phases[phase]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["status"] = "timedout"
          if phase == "prep":
            phases[phase]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["prepStarted"] = ""
            phases[phase]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["prepCompleted"] = ""
          elif phase == "upgrade":
            phases[phase]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["cguStarted"] = cgu_startedAt
            phases[phase]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["upgradeCompleted"] = ""
          phases[phase]["cgus"][cgu_name]["remediationPlan"][str(batch_index)][cluster]["duration"] = 0

    with open(ibu_cgu_csv_file, "a") as csv_file:
      csv_file.write("{},{},{},{},{},{},{},{},{},{},{}\n".format(cgu_name, cgu_status, cgu_created, cgu_startedAt, cgu_completedAt, cgu_duration, cgu_timeout, cgu_batches_count, cgu_clusters_total, cgu_clusters_completed_count, cgu_clusters_timedout_count))

    phases[phase]["cgus"][cgu_name]["status"] = cgu_status
    phases[phase]["cgus"][cgu_name]["creationTimestamp"] = cgu_created
    phases[phase]["cgus"][cgu_name]["startedAt"] = cgu_startedAt
    phases[phase]["cgus"][cgu_name]["completedAt"] = cgu_completedAt
    phases[phase]["cgus"][cgu_name]["duration"] = cgu_duration
    phases[phase]["cgus"][cgu_name]["timeout"] = cgu_timeout
    phases[phase]["cgus"][cgu_name]["batches_count"] = cgu_batches_count
    phases[phase]["cgus"][cgu_name]["clusters_count"] = cgu_clusters_total
    phases[phase]["cgus"][cgu_name]["clusters_completed_count"] = cgu_clusters_completed_count
    phases[phase]["cgus"][cgu_name]["clusters_timedout_count"] = cgu_clusters_timedout_count
    phases[phase]["cgus"][cgu_name]["clusters_timedout"] = cgu_clusters_timedout


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
  ibu_cgu_stats_file = "{}/ibu-{}-cgus-{}.stats".format(cliargs.results_directory, cliargs.ocp_version, ts)

  # Gather all CGU data for an IBU upgrade
  prep_label = "{}={}".format(cliargs.prep_label, cliargs.ocp_version)
  upgrade_label = "{}={}".format(cliargs.upgrade_label, cliargs.ocp_version)
  finalize_label = "{}={}".format(cliargs.finalize_label, cliargs.ocp_version)

  if not cliargs.offline_process:
    oc_cmd = ["oc", "get", "clustergroupupgrades", "-n", cliargs.namespace, "-l", prep_label, "-o", "json"]
    rc, output = command(oc_cmd, False, retries=3, no_log=True)
    if rc != 0:
      logger.error("analyze-imagebasedupgrade, oc get clustergroupupgrades -n {} -l {} rc: {}".format(cliargs.namespace, prep_label, cliargs.ocp_version, rc))
      sys.exit(1)
    with open("{}/prep-cgus.json".format(raw_data_dir), "w") as cgu_data_file:
      cgu_data_file.write(output)
  else:
    logger.info("Reading {}/prep-cgus.json".format(raw_data_dir))

  with open("{}/prep-cgus.json".format(raw_data_dir), "r") as cgu_data_file:
    cgu_prep_data = json.load(cgu_data_file)

  if not cliargs.offline_process:
    oc_cmd = ["oc", "get", "clustergroupupgrades", "-n", cliargs.namespace, "-l", upgrade_label, "-o", "json"]
    rc, output = command(oc_cmd, False, retries=3, no_log=True)
    if rc != 0:
      logger.error("analyze-imagebasedupgrade, oc get clustergroupupgrades -n {} -l {} rc: {}".format(cliargs.namespace, upgrade_label, cliargs.ocp_version, rc))
      sys.exit(1)
    with open("{}/upgrade-cgus.json".format(raw_data_dir), "w") as cgu_data_file:
      cgu_data_file.write(output)
  else:
    logger.info("Reading {}/upgrade-cgus.json".format(raw_data_dir))

  with open("{}/upgrade-cgus.json".format(raw_data_dir), "r") as cgu_data_file:
    cgu_upgrade_data = json.load(cgu_data_file)

  if not cliargs.offline_process:
    oc_cmd = ["oc", "get", "clustergroupupgrades", "-n", cliargs.namespace, "-l", finalize_label, "-o", "json"]
    rc, output = command(oc_cmd, False, retries=3, no_log=True)
    if rc != 0:
      logger.error("analyze-imagebasedupgrade, oc get clustergroupupgrades -n {} -l {} rc: {}".format(cliargs.namespace, finalize_label, cliargs.ocp_version, rc))
      sys.exit(1)
    with open("{}/finalize-cgus.json".format(raw_data_dir), "w") as cgu_data_file:
      cgu_data_file.write(output)
  else:
    logger.info("Reading {}/finalize-cgus.json".format(raw_data_dir))

  with open("{}/finalize-cgus.json".format(raw_data_dir), "r") as cgu_data_file:
    cgu_finalize_data = json.load(cgu_data_file)
  # Examine all cgu data for a complete IBU upgrade
  phases = OrderedDict()
  ibus = []

  if len(cgu_prep_data["items"]) == 0:
    logger.error("No prep cgu(s) to examine")
    sys.exit(1)

  logger.info("Writing CSV: {}".format(ibu_cgu_csv_file))
  with open(ibu_cgu_csv_file, "w") as csv_file:
    csv_file.write("name,status,creationTimestamp,startedAt,completedAt,duration,timeout,batchCount,clusterCount,clusterCompleted,clusterTimedout\n")

  logger.info("{} prep cgu(s) to examine".format(len(cgu_prep_data["items"])))
  examine_ibu_cgu(phases, "prep", cgu_prep_data, ibu_cgu_csv_file)
  # Use prep phase for all ibu data to collect
  for item in cgu_prep_data["items"]:
    for cluster in item["status"]["clusters"]:
      ibus.append(cluster["name"])
  ibus = sorted(ibus)

  if len(cgu_upgrade_data["items"]) == 0:
    logger.info("No upgrade cgu(s) to examine")
  else:
    logger.info("{} upgrade cgu(s) to examine".format(len(cgu_upgrade_data["items"])))
    examine_ibu_cgu(phases, "upgrade", cgu_upgrade_data, ibu_cgu_csv_file)

  if len(cgu_finalize_data["items"]) == 0:
    logger.info("No finalize cgu(s) to examine")
  else:
    logger.info("{} finalize cgu(s) to examine".format(len(cgu_finalize_data["items"])))
    examine_ibu_cgu(phases, "finalize", cgu_finalize_data, ibu_cgu_csv_file)

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
      for phase in phases:
        for cgu in phases[phase]["cgus"]:
          found_batch = False
          for batch in phases[phase]["cgus"][cgu]["remediationPlan"]:
            if cluster in phases[phase]["cgus"][cgu]["remediationPlan"][batch]:
              duration = 0
              if phase == "prep":
                phases[phase]["cgus"][cgu]["remediationPlan"][batch][cluster]["prepStarted"] = ibu_prep_started_time
                phases[phase]["cgus"][cgu]["remediationPlan"][batch][cluster]["prepCompleted"] = ibu_prep_completed_time
                if ibu_prep_started_time != "" and ibu_prep_completed_time != "":
                  duration = (ibu_prep_completed_time - ibu_prep_started_time).total_seconds()
              elif phase == "upgrade" and ibu_upgrade_completed_time != "":
                ibu_cgu_upgrade_started_time = phases[phase]["cgus"][cgu]["remediationPlan"][batch][cluster]["cguStarted"]
                phases[phase]["cgus"][cgu]["remediationPlan"][batch][cluster]["upgradeCompleted"] = ibu_upgrade_completed_time
                if ibu_upgrade_completed_time != "":
                  duration = (ibu_upgrade_completed_time - ibu_cgu_upgrade_started_time).total_seconds()
              phases[phase]["cgus"][cgu]["remediationPlan"][batch][cluster]["duration"] = duration
              found_batch = True
              break
          if found_batch:
            break
    # Write the IBU data to a CSV for prep phase
    logger.info("Writing CSV: {}".format(ibu_prep_csv_file))
    with open(ibu_prep_csv_file, "a") as csv_file:
      csv_file.write("name,status,cgu,batch,prepStarted,prepCompleted,duration\n")
      for cgu in phases["prep"]["cgus"]:
        for batch in phases["prep"]["cgus"][cgu]["remediationPlan"]:
          for cluster in phases["prep"]["cgus"][cgu]["remediationPlan"][batch]:
            status = phases["prep"]["cgus"][cgu]["remediationPlan"][batch][cluster]["status"]
            prep_started = phases["prep"]["cgus"][cgu]["remediationPlan"][batch][cluster]["prepStarted"]
            prep_completed = phases["prep"]["cgus"][cgu]["remediationPlan"][batch][cluster]["prepCompleted"]
            duration = phases["prep"]["cgus"][cgu]["remediationPlan"][batch][cluster]["duration"]
            # if duration == 0:
            #   logger.error("Cluster with 0 duration: {}".format(cluster))
            csv_file.write("{},{},{},{},{},{},{}\n".format(cluster, status, cgu, batch, prep_started, prep_completed, duration))

    # Write the IBU data to a CSV for upgrade phase
    if "upgrade" in phases:
      logger.info("Writing CSV: {}".format(ibu_upgrade_csv_file))
      with open(ibu_upgrade_csv_file, "a") as csv_file:
        csv_file.write("name,status,cgu,batch,cguStarted,upgradeCompleted,duration\n")
        for cgu in phases["upgrade"]["cgus"]:
          for batch in phases["upgrade"]["cgus"][cgu]["remediationPlan"]:
            for cluster in phases["upgrade"]["cgus"][cgu]["remediationPlan"][batch]:
              status = phases["upgrade"]["cgus"][cgu]["remediationPlan"][batch][cluster]["status"]
              cgu_started = phases["upgrade"]["cgus"][cgu]["remediationPlan"][batch][cluster]["cguStarted"]
              upgrade_completed = phases["upgrade"]["cgus"][cgu]["remediationPlan"][batch][cluster]["upgradeCompleted"]
              duration = phases["upgrade"]["cgus"][cgu]["remediationPlan"][batch][cluster]["duration"]
              csv_file.write("{},{},{},{},{},{},{}\n".format(cluster, status, cgu, batch, cgu_started, upgrade_completed, duration))
  # End ibu_analysis

  # Display summary of the collected CGU data
  logger.info("Writing Stats: {}".format(ibu_cgu_stats_file))
  with open(ibu_cgu_stats_file, "w") as stats_file:
    # log_write(stats_file, "#############################################")
    log_write(stats_file, "##########################################################################################")
    log_write(stats_file, "Stats on imagebasedupgrade clustergroupupgrades CRs in namespace {}".format(cliargs.namespace))
    log_write(stats_file, "Expected OCP Version {}".format(cliargs.ocp_version))
    cgu_total = sum([phases[x]["cgus_count"] for x in phases ])
    log_write(stats_file, "Total CGUs for all phases: {}".format(cgu_total))
    log_write(stats_file, "##########################################################################################")
    # log_write(stats_file, "#############################################")
    for phase in phases:
      phase_duration = (phases[phase]["completedAt"] - phases[phase]["creationTimestamp"]).total_seconds()
      log_write(stats_file, "Phase: {}".format(phase))
      cgus_completed_p = round(((phases[phase]["cgus_completed_count"] / phases[phase]["cgus_count"]) * 100), 1)
      cgus_timedout_p = round(((phases[phase]["cgus_timedout_count"] / phases[phase]["cgus_count"]) * 100), 1)
      log_write(stats_file, "CGUs: {} Total, {} Completed ({}%), {} TimedOut ({}%)".format(phases[phase]["cgus_count"], phases[phase]["cgus_completed_count"], cgus_completed_p, phases[phase]["cgus_timedout_count"], cgus_timedout_p))
      log_write(stats_file, "Count of Batches for phase: {}".format(phases[phase]["batches_count"]))
      clusters_completed_p = round(((phases[phase]["clusters_completed_count"] / phases[phase]["clusters_count"]) * 100), 1)
      clusters_timedout_p = round(((phases[phase]["clusters_timedout_count"] / phases[phase]["clusters_count"]) * 100), 1)
      log_write(stats_file, "Clusters: {} Total, {} completed ({}%), {} timedout ({}%)".format(phases[phase]["clusters_count"], phases[phase]["clusters_completed_count"], clusters_completed_p, phases[phase]["clusters_timedout_count"], clusters_timedout_p))
      log_write(stats_file, "Timedout Clusters: {}".format(phases[phase]["clusters_timedout"]))
      log_write(stats_file, "Earliest CGU creationTimestamp: {}".format(phases[phase]["creationTimestamp"]))
      log_write(stats_file, "Earliest CGU startedAt timestamp: {}".format(phases[phase]["startedAt"]))
      log_write(stats_file, "Latest CGU completedAt timestamp: {}".format(phases[phase]["completedAt"]))
      log_write(stats_file, "Phase duration: {}s :: {}".format(phase_duration, str(timedelta(seconds=phase_duration))))
      if len(phases[phase]["succeeded_durations"]) > 0:
        log_write(stats_file, "CGU Success Durations count: {}".format(len(phases[phase]["succeeded_durations"])))
        log_write(stats_file, "CGU Success Durations Min/Avg/50p/95p/99p/Max (seconds): {}".format(assemble_stats(phases[phase]["succeeded_durations"])))
        log_write(stats_file, "CGU Success Durations Min/Avg/50p/95p/99p/Max: {}".format(assemble_stats(phases[phase]["succeeded_durations"], False)))
      for cgu in phases[phase]["cgus"]:
        log_write(stats_file, "#############################################")
        status = phases[phase]["cgus"][cgu]["status"]
        created = phases[phase]["cgus"][cgu]["creationTimestamp"]
        startedAt = phases[phase]["cgus"][cgu]["startedAt"]
        completedAt = phases[phase]["cgus"][cgu]["completedAt"]
        duration = phases[phase]["cgus"][cgu]["duration"]
        timeout = phases[phase]["cgus"][cgu]["timeout"]
        batches = phases[phase]["cgus"][cgu]["batches_count"]
        clusters = phases[phase]["cgus"][cgu]["clusters_count"]
        clusters_completed = phases[phase]["cgus"][cgu]["clusters_completed_count"]
        clusters_timedout = phases[phase]["cgus"][cgu]["clusters_timedout_count"]
        completed_p = round(((clusters_completed / clusters) * 100), 1)
        timedout_p = round(((clusters_timedout / clusters) * 100), 1)
        log_write(stats_file, "CGU: {}, Status: {}, Batches: {}".format(cgu, status, batches))
        log_write(stats_file, "Clusters: {}, completed: {} ({}%), timedout: {} ({}%)".format(clusters, clusters_completed, completed_p, clusters_timedout, timedout_p))
        log_write(stats_file, "Timedout Clusters: {}".format(phases[phase]["cgus"][cgu]["clusters_timedout"]))
        log_write(stats_file, "creationTimestamp: {}".format(created))
        log_write(stats_file, "startedAt: {}".format(startedAt))
        log_write(stats_file, "completedAt: {}".format(completedAt))
        log_write(stats_file, "Duration: {}s :: {}, Timeout: {}".format(duration, str(timedelta(seconds=duration)), timeout))
        for batch in phases[phase]["cgus"][cgu]["remediationPlan"]:
          b_clusters = len(phases[phase]["cgus"][cgu]["remediationPlan"][batch])
          recorded_durations = []
          for cluster in phases[phase]["cgus"][cgu]["remediationPlan"][batch]:
            if phases[phase]["cgus"][cgu]["remediationPlan"][batch][cluster]["duration"] > 0:
              recorded_durations.append(phases[phase]["cgus"][cgu]["remediationPlan"][batch][cluster]["duration"])
          log_write(stats_file, "Batch: {}, Clusters: {}, Recorded Samples: {}".format(batch, b_clusters, len(recorded_durations)))
          log_write(stats_file, "(IBU) Batch Recorded Durations Min/Avg/50p/95p/99p/Max (seconds): {}".format(assemble_stats(recorded_durations)))
          log_write(stats_file, "(IBU) Batch Recorded Durations Min/Avg/50p/95p/99p/Max: {}".format(assemble_stats(recorded_durations, False)))
      log_write(stats_file, "##########################################################################################")

  end_time = time.time()
  logger.info("##########################################################################################")
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
