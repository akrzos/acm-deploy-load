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

  # Directory to find the csv file for graphing
  parser.add_argument("results_directory", type=str, help="The location of a sno-deploy-load results")

  cliargs = parser.parse_args()

  logger.info("SNO Deploy Time")
  # logger.info("CLI Args: {}".format(cliargs))
  md_csv_file = "{}/{}".format(cliargs.results_directory, cliargs.monitor_data_file_name)
  if not pathlib.Path(md_csv_file).is_file():
    logger.error("File not found: {}".format(md_csv_file))
    sys.exit(1)

  found_start_ts = False
  start_ts = ""
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
        if concurrency > peak_concurrency:
          peak_concurrency = concurrency
        if (start_ts == "") and (int(row[1]) > 0):
          start_ts = row_ts
        data.append(row)

    sno_completed = int(data[-1][12]) + int(data[-1][13])
    last_ts = datetime.strptime(data[-1][0], "%Y-%m-%dT%H:%M:%SZ")
    completed_ts = datetime.strptime(data[-1][0], "%Y-%m-%dT%H:%M:%SZ")

    # Find when test was completed by first time that all compliant/timed out du profile snos first appeared
    for row in reversed(data):
      if (int(row[12]) + int(row[13])) < sno_completed:
        completed_ts = completed_ts
        break
      completed_ts = datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ")

  logger.info("Start TS: {}".format(start_ts))
  logger.info("Last TS: {}".format(last_ts))
  logger.info("Completed TS: {}".format(completed_ts))

  completed_duration = int((completed_ts - start_ts).total_seconds())
  full_duration = int((last_ts - start_ts).total_seconds())
  logger.info("Full Duration: {}".format(full_duration))
  logger.info("Completed Duration: {}".format(completed_duration))
  logger.info("Peak Concurrency (sno_installing + policy_applying): {}".format(peak_concurrency))

  logger.info("Complete")

if __name__ == "__main__":
  sys.exit(main())
