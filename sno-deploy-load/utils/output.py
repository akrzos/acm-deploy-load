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
from datetime import timedelta
import logging

logger = logging.getLogger("sno-deploy-load")


def generate_report(start_time, end_time, deploy_start_time, deploy_end_time, wait_sno_start_time, wait_sno_end_time,
    wait_du_profile_start_time, wait_du_profile_end_time, available_snos, total_deployed_snos, monitor_data, cliargs,
    total_intervals, report_dir):

  # Determine result data
  total_deploy_time = round(deploy_end_time - deploy_start_time)
  total_sno_install_time = round(wait_sno_end_time - wait_sno_start_time)
  total_duprofile_time = round(wait_du_profile_end_time - wait_du_profile_start_time)
  total_time = round(end_time - start_time)
  success_sno_percent = 0
  failed_sno_percent = 0
  success_managed_percent = 0
  failed_managed_percent = 0
  success_du_percent = 0
  failed_du_percent = 0
  if total_deployed_snos > 0:
    success_sno_percent = round((monitor_data["sno_install_completed"] / total_deployed_snos) * 100, 1)
    failed_sno_percent = round(100 - success_sno_percent, 1)
  if monitor_data["sno_install_completed"] > 0:
    success_managed_percent = round((monitor_data["managed"] / monitor_data["sno_install_completed"]) * 100, 1)
    failed_managed_percent = round(100 - success_managed_percent, 1)
  if monitor_data["policy_init"] > 0:
    success_du_percent = round((monitor_data["policy_compliant"] / monitor_data["policy_init"]) * 100, 1)
    failed_du_percent = round(100 - success_du_percent, 1)

  # Log the report and output to report.txt in results directory
  with open("{}/report.txt".format(report_dir), "w") as report:
    phase_break(True, report)
    log_write(report, "sno-deploy-load Report Card")
    phase_break(True, report)
    log_write(report, "Versions")
    log_write(report, " * ACM: {}".format(cliargs.acm_version))
    log_write(report, " * Test: {}".format(cliargs.test_version))
    log_write(report, " * Hub OCP: {}".format(cliargs.hub_version))
    log_write(report, " * SNO OCP: {}".format(cliargs.sno_version))
    log_write(report, "SNO Results")
    log_write(report, " * Available SNOs: {}".format(available_snos))
    log_write(report, " * Deployed SNOs: {}".format(total_deployed_snos))
    log_write(report, " * Installed SNOs: {}".format(monitor_data["sno_install_completed"]))
    log_write(report, " * Failed SNOs: {}".format(monitor_data["sno_install_failed"]))
    if monitor_data["sno_notstarted"] > 0:
      log_write(report, " * NotStarted SNOs: {}".format(monitor_data["sno_notstarted"]))
    log_write(report, " * SNO Successful Percent: {}%".format(success_sno_percent))
    log_write(report, " * SNO Failed Percent: {}%".format(failed_sno_percent))
    log_write(report, "Managed SNO Results")
    log_write(report, " * Installed SNOs: {}".format(monitor_data["sno_install_completed"]))
    log_write(report, " * Managed SNOs: {}".format(monitor_data["managed"]))
    log_write(report, " * Managed Successful Percent: {}%".format(success_managed_percent))
    log_write(report, " * Managed Failed Percent: {}%".format(failed_managed_percent))
    log_write(report, "DU Profile Results")
    log_write(report, " * DU Profile Initialized: {}".format(monitor_data["policy_init"]))
    log_write(report, " * DU Profile Compliant: {}".format(monitor_data["policy_compliant"]))
    log_write(report, " * DU Profile Timeout: {}".format(monitor_data["policy_timedout"]))
    log_write(report, " * DU Profile Successful Percent: {}%".format(success_du_percent))
    log_write(report, " * DU Profile Failed Percent: {}%".format(failed_du_percent))
    log_write(report, "SNO Orchestration")
    log_write(report, " * Method: {}".format(cliargs.rate))
    log_write(report, " * SNO Start: {} End: {}".format(cliargs.start, cliargs.end))
    if cliargs.rate == "interval":
      log_write(report, " * {} SNO(s) per {}s interval".format(cliargs.batch, cliargs.interval))
      log_write(report, " * Actual Intervals: {}".format(total_intervals))
    log_write(report, " * Wan Emulation: {}".format(cliargs.wan_emulation))
    log_write(report, "Workload Duration Results")
    log_write(report, " * Start Time: {} {}".format(
        datetime.utcfromtimestamp(start_time).strftime("%Y-%m-%dT%H:%M:%SZ"), int(start_time * 1000)))
    log_write(report, " * End Time: {} {}".format(
        datetime.utcfromtimestamp(end_time).strftime("%Y-%m-%dT%H:%M:%SZ"), int(end_time * 1000)))
    log_write(report, " * SNO Deploying duration: {}s :: {}".format(total_deploy_time, str(timedelta(seconds=total_deploy_time))))
    if not cliargs.skip_wait_sno:
      log_write(report, " * SNO Install wait duration: {}s :: {}".format(total_sno_install_time, str(timedelta(seconds=total_sno_install_time))))
    if cliargs.wait_du_profile:
      log_write(report, " * DU Profile wait duration: {}s :: {}".format(total_duprofile_time, str(timedelta(seconds=total_duprofile_time))))
    log_write(report, " * Total duration: {}s :: {}".format(total_time, str(timedelta(seconds=total_time))))
  # Done outputing the report card

def log_write(file, message):
  logger.info(message)
  file.write(message + "\n")


def phase_break(lw=False, file=None):
  if lw:
    log_write(file, "###############################################################################")
  else:
    logger.info("###############################################################################")
