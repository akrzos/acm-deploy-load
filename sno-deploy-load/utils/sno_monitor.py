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

from datetime import datetime
import json
import logging
import time
import os
from utils.command import command
import time
from threading import Thread
import traceback


logger = logging.getLogger("sno-deploy-load")


class SnoMonitor(Thread):
  def __init__(self, talm_minor, monitor_data, csv_file, dry_run, sample_interval):
    super(SnoMonitor, self).__init__()
    self.talm_minor = talm_minor
    self.monitor_data = monitor_data
    self.csv_file = csv_file
    self.dry_run = dry_run
    self.sample_interval = sample_interval
    self.signal = True

  def _real_run(self):
    logger.info("Starting SNO Monitor")

    with open(self.csv_file, "w") as csv_file:
      csv_file.write("date,sno_applied,sno_init,sno_notstarted,sno_booted,sno_discovered,sno_installing,sno_install_failed,sno_install_completed,managed,policy_init,policy_notstarted,policy_applying,policy_timedout,policy_compliant\n")

    while self.signal:
      start_sample_time = time.time()

      # Get agentclusterinstall data
      oc_cmd = ["oc", "get", "agentclusterinstall", "-A", "-o", "json"]
      rc, output = command(oc_cmd, self.dry_run, retries=3, no_log=True)
      aci_data = {"items": []}
      if rc != 0:
        logger.error("sno-deploy-load, oc get agentclusterinstall rc: {}".format(rc))
      else:
        if not self.dry_run:
          aci_data = json.loads(output)

      # Get clustergroupupgrades data
      oc_cmd = ["oc", "get", "clustergroupupgrades", "-n", "ztp-install", "-o", "json"]
      rc, output = command(oc_cmd, self.dry_run, retries=3, no_log=True)
      cgu_data = {"items": []}
      if rc != 0:
        logger.error("sno-deploy-load, oc get clustergroupupgrades rc: {}".format(rc))
      else:
        if not self.dry_run:
          cgu_data = json.loads(output)

      # Get baremetalhost data
      oc_cmd = ["oc", "get", "baremetalhost", "-A", "-o", "json"]
      rc, output = command(oc_cmd, self.dry_run, retries=3, no_log=True)
      bmh_data = {"items": []}
      if rc != 0:
        logger.error("sno-deploy-load, oc get baremetalhost rc: {}".format(rc))
      else:
        if not self.dry_run:
          bmh_data = json.loads(output)

      # Get agent data
      oc_cmd = ["oc", "get", "agent", "-A", "-o", "json"]
      rc, output = command(oc_cmd, self.dry_run, retries=3, no_log=True)
      agent_data = {"items": []}
      if rc != 0:
        logger.error("sno-deploy-load, oc get agent rc: {}".format(rc))
      else:
        if not self.dry_run:
          agent_data = json.loads(output)

      # Get managedcluster data
      oc_cmd = ["oc", "get", "managedcluster", "-A", "-o", "json"]
      rc, output = command(oc_cmd, self.dry_run, retries=3, no_log=True)
      mc_data = {"items": []}
      if rc != 0:
        logger.error("sno-deploy-load, oc get managedcluster rc: {}".format(rc))
      else:
        if not self.dry_run:
          mc_data = json.loads(output)

      sno_init = len(aci_data["items"])
      sno_notstarted = 0
      sno_booted = 0
      sno_discovered = len(agent_data["items"])
      sno_installing = 0
      sno_install_failed = 0
      sno_install_completed = 0
      sno_managed = 0
      sno_policy_init = len(cgu_data["items"])
      sno_policy_notstarted = 0
      sno_policy_applying = 0
      sno_policy_timedout = 0
      sno_policy_compliant = 0

      # Parse agentclusterinstall data
      for item in aci_data["items"]:
        if "status" in item and "conditions" in item["status"]:
          for condition in item["status"]["conditions"]:
            if "type" in condition:
              if condition["type"] == "Completed":
                if "reason" in condition:
                  logger.debug("ACI SNO: {} is {}".format(item["metadata"]["name"], condition["reason"]))
                  if condition["reason"] == "InstallationNotStarted":
                    sno_notstarted += 1
                  elif condition["reason"] == "InstallationInProgress":
                    sno_installing += 1
                  elif condition["reason"] == "InstallationFailed":
                    sno_install_failed += 1
                  elif condition["reason"] == "InstallationCompleted":
                    sno_install_completed += 1
                  else:
                    logger.info("aci: {}: Unrecognized Completed Reason: {}".format(item["metadata"]["name"], condition["reason"]))
                  break
                else:
                  logger.warn("reason missing from condition: {}".format(condition))
            else:
              logger.warn("aci: type missing from condition(item): {}".format(item))
              logger.warn("aci: type missing from condition(condition): {}".format(condition))
        else:
          logger.warn("status or conditions not found in clustergroupupgrades object: {}".format(item))

      # Parse clustergroupupgrades data
      for item in cgu_data["items"]:
        if "status" in item and "conditions" in item["status"]:
          for condition in item["status"]["conditions"]:
            if self.talm_minor >= 12:
              if "type" in condition:
                logger.debug("CGU SNO: {} Condition: {}".format(item["metadata"]["name"], condition))
                if (condition["type"] == "Progressing" and condition["status"] == "False"
                    and condition["reason"] != "Completed" and condition["reason"] != "TimedOut"):
                  sno_policy_notstarted += 1
                  break
                if condition["type"] == "Progressing" and condition["status"] == "True" and condition["reason"] == "InProgress":
                  sno_policy_applying += 1
                  break
                if condition["type"] == "Succeeded" and condition["status"] == "False" and condition["reason"] == "TimedOut":
                  sno_policy_timedout += 1
                  break
                if condition["type"] == "Succeeded" and condition["status"] == "True" and condition["reason"] == "Completed":
                  sno_policy_compliant += 1
                  break
              else:
                logger.warn("cgu: type missing from condition(item): {}".format(item))
                logger.warn("cgu: type missing from condition(condition): {}".format(condition))
            else:
              if "type" in condition:
                if condition["type"] == "Ready":
                  if "reason" in condition:
                    logger.debug("CGU SNO: {} is {}".format(item["metadata"]["name"], condition["reason"]))
                    if condition["reason"] == "UpgradeNotStarted":
                      sno_policy_notstarted += 1
                    elif condition["reason"] == "UpgradeNotCompleted":
                      sno_policy_applying += 1
                    elif condition["reason"] == "UpgradeTimedOut":
                      sno_policy_timedout += 1
                    elif condition["reason"] == "UpgradeCompleted":
                      sno_policy_compliant += 1
                    else:
                      logger.info("cgu: {}: Unrecognized Completed Reason: {}".format(item["metadata"]["name"], condition["reason"]))
                    break
                  else:
                    logger.warn("reason missing from condition: {}".format(condition))
              else:
                logger.warn("cgu: type missing from condition(item): {}".format(item))
                logger.warn("cgu: type missing from condition(condition): {}".format(condition))
        else:
          logger.warn("status or conditions not found in clustergroupupgrades object: {}".format(item))

      # Parse baremetalhost data
      for item in bmh_data["items"]:
        if "status" in item and "provisioning" in item["status"] and "state" in item["status"]["provisioning"]:
          if item["status"]["provisioning"]["state"] == "provisioned":
            logger.debug("BMH SNO: {} is {}".format(item["metadata"]["name"], item["status"]["provisioning"]["state"]))
            sno_booted += 1
        else:
          logger.warn("missing status or elements under status in baremetalhost object: {}".format(item))

      # Parse managedcluster data
      for item in mc_data["items"]:
        if "status" in item and "conditions" in item["status"]:
          for condition in item["status"]["conditions"]:
            if "type" in condition:
              if condition["type"] == "ManagedClusterConditionAvailable":
                logger.debug(
                    "MC SNO: {} is {} is {}".format(item["metadata"]["name"], condition["type"], condition["status"]))
                if condition["status"] == "True":
                  sno_managed += 1
                break
            else:
              logger.warn("mc: type missing from condition(item): {}".format(item))
              logger.warn("mc: type missing from condition(condition): {}".format(condition))
        else:
          logger.warn("status or conditions not found in managedcluster object: {}".format(item))

      self.monitor_data["sno_init"] = sno_init
      self.monitor_data["sno_notstarted"] = sno_notstarted
      self.monitor_data["sno_booted"] = sno_booted
      self.monitor_data["sno_discovered"] = sno_discovered
      self.monitor_data["sno_installing"] = sno_installing
      self.monitor_data["sno_install_failed"] = sno_install_failed
      self.monitor_data["sno_install_completed"] = sno_install_completed
      self.monitor_data["managed"] = sno_managed
      self.monitor_data["policy_init"] = sno_policy_init
      self.monitor_data["policy_notstarted"] = sno_policy_notstarted
      self.monitor_data["policy_applying"] = sno_policy_applying
      self.monitor_data["policy_timedout"] = sno_policy_timedout
      self.monitor_data["policy_compliant"] = sno_policy_compliant

      # Write csv data
      with open(self.csv_file, "a") as csv_file:
        csv_file.write("{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}\n".format(
            datetime.utcfromtimestamp(start_sample_time).strftime('%Y-%m-%dT%H:%M:%SZ'),
            self.monitor_data["sno_applied_committed"], sno_init, sno_notstarted, sno_booted, sno_discovered,
            sno_installing, sno_install_failed, sno_install_completed, sno_managed, sno_policy_init,
            sno_policy_notstarted, sno_policy_applying, sno_policy_timedout, sno_policy_compliant
        ))

      logger.debug("Applied/Committed SNOs: {}".format(self.monitor_data["sno_applied_committed"]))
      logger.debug("Initialized SNOs: {}".format(self.monitor_data["sno_init"]))
      logger.debug("Not Started SNOs: {}".format(self.monitor_data["sno_notstarted"]))
      logger.debug("Booted SNOs: {}".format(self.monitor_data["sno_booted"]))
      logger.debug("Discovered SNOs: {}".format(self.monitor_data["sno_discovered"]))
      logger.debug("Installing SNOs: {}".format(self.monitor_data["sno_installing"]))
      logger.debug("Failed SNOs: {}".format(self.monitor_data["sno_install_failed"]))
      logger.debug("Completed SNOs: {}".format(self.monitor_data["sno_install_completed"]))
      logger.debug("Managed SNOs: {}".format(self.monitor_data["managed"]))
      logger.debug("Initialized Policy SNOs: {}".format(self.monitor_data["policy_init"]))
      logger.debug("Policy Not Started SNOs: {}".format(self.monitor_data["policy_notstarted"]))
      logger.debug("Policy Applying SNOs: {}".format(self.monitor_data["policy_applying"]))
      logger.debug("Policy Timedout SNOs: {}".format(self.monitor_data["policy_timedout"]))
      logger.debug("Policy Compliant SNOs: {}".format(self.monitor_data["policy_compliant"]))

      end_sample_time = time.time()
      sample_time = round(end_sample_time - start_sample_time, 1)
      logger.info("Monitor sampled in {}".format(sample_time))

      time_to_sleep = self.sample_interval - sample_time
      if time_to_sleep > 0:
        time.sleep(time_to_sleep)
      else:
        logger.warn("Time to monitor exceeded monitor interval")
    logger.info("Monitor Thread terminating")

  def run(self):
    try:
      self._real_run()
    except Exception as e:
      logger.error("Error in Monitoring Thread: {}".format(e))
      logger.error('\n{}'.format(traceback.format_exc()))
      os._exit(1)
