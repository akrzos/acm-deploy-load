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
from csv import reader
from datetime import datetime
from datetime import timedelta
import logging
import pandas as pd
import pathlib
import sys
import time


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("sno-deploy-time")
logging.Formatter.converter = time.gmtime


def main():
  parser = argparse.ArgumentParser(
      description="Determine total test time from monitor data",
      prog="sno-deploy-time.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  # Name of csv file found in results directory
  parser.add_argument("--monitor-data-file-name", type=str, default="monitor_data.csv",
      help="The name of the monitor data csv file.")
  parser.add_argument("results_directory", type=str, help="The location of a sno-deploy-load results")
  cliargs = parser.parse_args()

  logger.info("SNO Deploy Time")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")
  md_csv_file = "{}/{}".format(cliargs.results_directory, cliargs.monitor_data_file_name)
  sno_time_file = "{}/deploy-time-{}".format(cliargs.results_directory, ts)
  if not pathlib.Path(md_csv_file).is_file():
    logger.error("File not found: {}".format(md_csv_file))
    sys.exit(1)

  found_start_ts = False
  start_ts = ""
  peak_sno_installing = 0
  peak_du_applying = 0
  peak_concurrency = 0
  data = []
  with open(md_csv_file, "r") as sno_cv_csv:
    csv_reader = reader(sno_cv_csv)

    # Determine official "start time" and read entire file into list
    # Remove the csv header first
    header = next(csv_reader)
    if header != None:
      for row in csv_reader:
        row_ts = datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ")
        concurrency = int(row[5]) + int(row[11])
        if int(row[5]) > peak_sno_installing:
          peak_sno_installing = int(row[5])
        if int(row[11]) > peak_du_applying:
          peak_du_applying = int(row[11])
        if concurrency > peak_concurrency:
          peak_concurrency = concurrency
        if (start_ts == "") and (int(row[1]) > 0):
          start_ts = row_ts
        data.append(row)

    sno_installed = int(data[-1][7])
    deployment_completed = int(data[-1][13])
    sno_completed = int(data[-1][12]) + int(data[-1][13])

    last_ts = datetime.strptime(data[-1][0], "%Y-%m-%dT%H:%M:%SZ")
    sno_installed_ts = datetime.strptime(data[-1][0], "%Y-%m-%dT%H:%M:%SZ")
    deployment_completed_ts = datetime.strptime(data[-1][0], "%Y-%m-%dT%H:%M:%SZ")
    completed_ts = datetime.strptime(data[-1][0], "%Y-%m-%dT%H:%M:%SZ")

  # Find when test was completed with max du compliant+du_timeout reached
  for row in reversed(data):
    if (int(row[12]) + int(row[13])) < sno_completed:
      completed_ts = completed_ts
      break
    completed_ts = datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ")

  # Find when test is considered deployment completed by first time we reach max du compliant
  for row in reversed(data):
    if int(row[13]) < deployment_completed:
      deployment_completed_ts = deployment_completed_ts
      break
    deployment_completed_ts = datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ")

  # Find when test is considered sno install completed by first time we reach max snos installed
  for row in reversed(data):
    if int(row[7]) < sno_installed:
      sno_installed_ts = sno_installed_ts
      break
    sno_installed_ts = datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ")

  sno_install_duration = int((sno_installed_ts - start_ts).total_seconds())
  deployed_complete_duration = int((deployment_completed_ts - start_ts).total_seconds())
  completed_duration = int((completed_ts - start_ts).total_seconds())
  full_duration = int((last_ts - start_ts).total_seconds())

  with open(sno_time_file, "w") as time_file:
    log_write(time_file, "Start TS: {}".format(start_ts))
    log_write(time_file, "SNO Install TS: {}".format(sno_installed_ts))
    log_write(time_file, "Deployment Complete TS: {}".format(deployment_completed_ts))
    log_write(time_file, "Completed TS: {}".format(completed_ts))
    log_write(time_file, "Last TS: {}".format(last_ts))
    log_write(time_file, "################################################################")
    log_write(time_file, "SNO Install Duration (SNO Install Completed): {}s :: {}".format(sno_install_duration, str(timedelta(seconds=sno_install_duration))))
    log_write(time_file, "Deployment Complete Duration (DU Compliant): {}s :: {}".format(deployed_complete_duration, str(timedelta(seconds=deployed_complete_duration))))
    log_write(time_file, "Completed Duration (DU Timeout+Compliant): {}s :: {}".format(completed_duration, str(timedelta(seconds=completed_duration))))
    log_write(time_file, "Full Duration: {}, :: {}".format(full_duration, str(timedelta(seconds=full_duration))))
    log_write(time_file, "################################################################")
    deployed_installed_time_diff = deployed_complete_duration - sno_install_duration
    log_write(time_file, "Deployment Complete - SNO Install Completed: {}s :: {}".format(deployed_installed_time_diff, str(timedelta(seconds=deployed_installed_time_diff))))
    log_write(time_file, "################################################################")
    log_write(time_file, "Peak SNO Installing: {}".format(peak_sno_installing))
    log_write(time_file, "Peak DU Applying: {}".format(peak_du_applying))
    log_write(time_file, "Peak Concurrency (sno_installing + policy_applying): {}".format(peak_concurrency))

  logger.info("Complete")

def log_write(file, message):
  logger.info(message)
  file.write(message + "\n")

if __name__ == "__main__":
  sys.exit(main())
