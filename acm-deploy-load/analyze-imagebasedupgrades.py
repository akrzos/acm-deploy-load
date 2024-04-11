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
from utils.command import command
from utils.output import assemble_stats
from utils.output import log_write
import logging
import sys
import time


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def examine_ibu_cgu(phase, cgu_data, ibu_cgu_csv_file):
  cgus_completed = 0
  cgus_timedout = 0
  cgus_create_time = ""
  cgus_started_time = ""
  cgus_completed_time = ""
  cgus_succeeded_durations = []
  cgus_clusters_total = 0
  cgus_clusters_completed_count = 0
  cgus_clusters_timedout_count = 0
  cgus_clusters_timedout = []

  for item in cgu_data["items"]:
    cgu_name = item["metadata"]["name"]
    cgu_status = "unknown"
    cgu_created = ""
    cgu_startedAt = ""
    cgu_completedAt = ""
    cgu_duration = 0
    cgu_clusters_count = 0
    cgu_clusters_completed_count = 0
    cgu_clusters_timedout_count = 0
    cgu_clusters_timedout = []
    cgu_created = datetime.strptime(item["metadata"]["creationTimestamp"], "%Y-%m-%dT%H:%M:%SZ")
    if cgus_create_time == "":
      cgus_create_time = cgu_created
    elif cgus_create_time > cgu_created:
      logger.info("Replacing cgu created time {} with earlier time {}".format(cgus_create_time, cgu_created))
      cgus_create_time = cgu_created
    if "startedAt" in item["status"]["status"]:
      # Determine earliest startedAt time for the cgus in this namespace
      cgu_startedAt = datetime.strptime(item["status"]["status"]["startedAt"], "%Y-%m-%dT%H:%M:%SZ")
      if cgus_started_time == "":
        cgus_started_time = cgu_startedAt
      elif cgus_started_time > cgu_startedAt:
        logger.info("Replacing cgu started time {} with earlier time {}".format(cgus_started_time, cgu_startedAt))
        cgus_started_time = cgu_startedAt
    if "completedAt" in item["status"]["status"]:
      # Determine latest populated completed time
      cgu_completedAt = datetime.strptime(item["status"]["status"]["completedAt"], "%Y-%m-%dT%H:%M:%SZ")
      if cgus_completed_time == "":
        cgus_completed_time = cgu_completedAt
      elif cgus_completed_time < cgu_completedAt:
        logger.info("Replacing cgu completed time {} with later time {}".format(cgus_completed_time, cgu_completedAt))
        cgus_completed_time = cgu_completedAt
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
            cgus_timedout += 1
          if condition["type"] == "Succeeded" and condition["status"] == "True" and condition["reason"] == "Completed":
            cgu_status = "Completed"
            cgus_completed += 1
            cgus_succeeded_durations.append(cgu_duration)

    if "clusters" in item["status"]:
      cgu_clusters_total = len(item["status"]["clusters"])
      for cluster in item["status"]["clusters"]:
        if cluster["state"] == "complete":
          cgu_clusters_completed_count += 1
        elif cluster["state"] == "timedout":
          cgu_clusters_timedout_count += 1
          cgu_clusters_timedout.append(cluster["name"])
        else:
          logger.warn("Unexpected cluster state: {}".format(cluster["state"]))

      cgus_clusters_total += cgu_clusters_total
      cgus_clusters_completed_count += cgu_clusters_completed_count
      cgus_clusters_timedout_count += cgu_clusters_timedout_count
      cgus_clusters_timedout.extend(cgu_clusters_timedout)

    with open(ibu_cgu_csv_file, "a") as csv_file:
      csv_file.write("{},{},{},{},{},{},{},{},{}\n".format(cgu_name, cgu_status, cgu_created, cgu_startedAt, cgu_completedAt, cgu_duration, cgu_clusters_total, cgu_clusters_completed_count, cgu_clusters_timedout_count))

    logger.info("Name: {}".format(cgu_name))
    # logger.info("Status: {}".format(cgu_status))
    # logger.info("Created: {}".format(cgu_created))
    # logger.info("Started: {}".format(cgu_startedAt))
    # logger.info("Completed: {}".format(cgu_completedAt))
    # logger.info("Duration: {}".format(cgu_duration))
    # logger.info("Cluster Count: {}".format(cgu_clusters_total))
    # logger.info("Clusters Completed: {}".format(cgu_clusters_completed_count))
    # logger.info("Clusters Timedout: {}".format(cgu_clusters_timedout_count))

  phase["cgus"] = len(cgu_data["items"])
  phase["cgus_completed"] = cgus_completed
  phase["cgus_timedout"] = cgus_timedout
  phase["creationTimestamp"] = cgus_create_time
  phase["startedAt"] = cgus_started_time
  phase["completedAt"] = cgus_completed_time
  phase["succeeded_durations"] = cgus_succeeded_durations
  phase["clusters_total"] = cgus_clusters_total
  phase["clusters_completed_total"] = cgus_clusters_completed_count
  phase["clusters_timedout_total"] = cgus_clusters_timedout_count
  phase["clusters_timedout"] = cgus_clusters_timedout


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

  # parser.add_argument("-ni", "--no-ibu-analysis", action="store_true", default=False, help="Skip analyzing individual IBU objects")
  cliargs = parser.parse_args()

  logger.info("Analyze imagebasedupgrade")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")
  ibu_cgu_csv_file = "{}/ibu-cgus-{}.csv".format(cliargs.results_directory, ts)
  ibu_cgu_stats_file = "{}/ibu-cgus-{}.stats".format(cliargs.results_directory, ts)

  # Gather all CGU data for an IBU upgrade
  prep_label = "{}={}".format(cliargs.prep_label, cliargs.ocp_version)
  upgrade_label = "{}={}".format(cliargs.upgrade_label, cliargs.ocp_version)
  finalize_label = "{}={}".format(cliargs.finalize_label, cliargs.ocp_version)

  oc_cmd = ["oc", "get", "clustergroupupgrades", "-n", cliargs.namespace, "-l", prep_label, "-o", "json"]
  rc, output = command(oc_cmd, False, retries=3, no_log=True)
  if rc != 0:
    logger.error("analyze-imagebasedupgrade, oc get clustergroupupgrades -n {} -l {} rc: {}".format(cliargs.namespace, prep_label, cliargs.ocp_version, rc))
    sys.exit(1)
  cgu_prep_data = json.loads(output)

  oc_cmd = ["oc", "get", "clustergroupupgrades", "-n", cliargs.namespace, "-l", upgrade_label, "-o", "json"]
  rc, output = command(oc_cmd, False, retries=3, no_log=True)
  if rc != 0:
    logger.error("analyze-imagebasedupgrade, oc get clustergroupupgrades -n {} -l {} rc: {}".format(cliargs.namespace, upgrade_label, cliargs.ocp_version, rc))
    sys.exit(1)
  cgu_upgrade_data = json.loads(output)

  oc_cmd = ["oc", "get", "clustergroupupgrades", "-n", cliargs.namespace, "-l", finalize_label, "-o", "json"]
  rc, output = command(oc_cmd, False, retries=3, no_log=True)
  if rc != 0:
    logger.error("analyze-imagebasedupgrade, oc get clustergroupupgrades -n {} -l {} rc: {}".format(cliargs.namespace, finalize_label, cliargs.ocp_version, rc))
    sys.exit(1)
  cgu_finalize_data = json.loads(output)


  logger.info("Writing CSV: {}".format(ibu_cgu_csv_file))
  with open(ibu_cgu_csv_file, "w") as csv_file:
    csv_file.write("name,status,creationTimestamp,startedAt,completedAt,duration,clusterCount,clusterCompleted,clusterTimedout\n")

  # Examine all cgu data for a complete IBU upgrade
  phases = OrderedDict()

  if len(cgu_prep_data["items"]) == 0:
    logger.info("No prep cgu(s) to examine")
  else:
    logger.info("{} prep cgu(s) to examine".format(len(cgu_prep_data["items"])))
    phases["prep"] = {}
    examine_ibu_cgu(phases["prep"], cgu_prep_data, ibu_cgu_csv_file)

  if len(cgu_upgrade_data["items"]) == 0:
    logger.info("No upgrade cgu(s) to examine")
  else:
    logger.info("{} upgrade cgu(s) to examine".format(len(cgu_upgrade_data["items"])))
    phases["upgrade"] = {}
    examine_ibu_cgu(phases["upgrade"], cgu_upgrade_data, ibu_cgu_csv_file)

  if len(cgu_finalize_data["items"]) == 0:
    logger.info("No finalize cgu(s) to examine")
  else:
    logger.info("{} finalize cgu(s) to examine".format(len(cgu_finalize_data["items"])))
    phases["finalize"] = {}
    examine_ibu_cgu(phases["finalize"], cgu_finalize_data, ibu_cgu_csv_file)

  # Display summary of the collected CGU data
  logger.info("Writing Stats: {}".format(ibu_cgu_stats_file))
  with open(ibu_cgu_stats_file, "w") as stats_file:
    log_write(stats_file, "#############################################")
    log_write(stats_file, "Stats on imagebasedupgrade clustergroupupgrades CRs in namespace {}".format(cliargs.namespace))
    log_write(stats_file, "Expected OCP Version {}".format(cliargs.ocp_version))
    cgu_total = sum([phases[x]["cgus"] for x in phases ])
    log_write(stats_file, "Total CGUs: {}".format(cgu_total))
    log_write(stats_file, "#############################################")
    for phase in phases:
      phase_duration = (phases[phase]["completedAt"] - phases[phase]["creationTimestamp"]).total_seconds()
      log_write(stats_file, "Phase: {}".format(phase))
      cgus_completed_p = round(((phases[phase]["cgus_completed"] / phases[phase]["cgus"]) * 100), 1)
      cgus_timedout_p = round(((phases[phase]["cgus_timedout"] / phases[phase]["cgus"]) * 100), 1)
      log_write(stats_file, "CGUs: {} Total, {} Completed ({}%), {} TimedOut ({}%)".format(phases[phase]["cgus"], phases[phase]["cgus_completed"], cgus_completed_p, phases[phase]["cgus_timedout"], cgus_timedout_p))
      clusters_completed_p = round(((phases[phase]["clusters_completed_total"] / phases[phase]["clusters_total"]) * 100), 1)
      clusters_timedout_p = round(((phases[phase]["clusters_timedout_total"] / phases[phase]["clusters_total"]) * 100), 1)
      log_write(stats_file, "Clusters: {} Total, {} completed ({}%), {} timedout ({}%)".format(phases[phase]["clusters_total"], phases[phase]["clusters_completed_total"], clusters_completed_p, phases[phase]["clusters_timedout_total"], clusters_timedout_p))
      log_write(stats_file, "Timedout Clusters: {}".format(phases[phase]["clusters_timedout"]))
      log_write(stats_file, "Earliest CGU creationTimestamp: {}".format(phases[phase]["creationTimestamp"]))
      log_write(stats_file, "Earliest CGU startedAt timestamp: {}".format(phases[phase]["startedAt"]))
      log_write(stats_file, "Latest CGU completedAt timestamp: {}".format(phases[phase]["completedAt"]))
      log_write(stats_file, "Phase duration: {}s :: {}".format(phase_duration, str(timedelta(seconds=phase_duration))))
      if len(phases[phase]["succeeded_durations"]) > 0:
        log_write(stats_file, "CGU Success Durations count: {}".format(len(phases[phase]["succeeded_durations"])))
        log_write(stats_file, "CGU Success Durations Min/Avg/50p/95p/99p/Max (seconds): {}".format(assemble_stats(phases[phase]["succeeded_durations"])))
        log_write(stats_file, "CGU Success Durations Min/Avg/50p/95p/99p/Max: {}".format(assemble_stats(phases[phase]["succeeded_durations"], False)))
      log_write(stats_file, "#############################################")

  end_time = time.time()
  logger.info("##########################################################################################")
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
