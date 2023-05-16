#!/usr/bin/env python3
#
# Graph csv data as time-series from analyze-clusterversion.py script
#
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
from csv import reader
from datetime import datetime
from datetime import timedelta
import logging
import os
import pandas as pd
import pathlib
import plotly as py
import plotly.figure_factory as ff
import plotly.graph_objects as go
import plotly.express as px
import sys
import time


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Graph deployed cluster's clusterversion data",
      prog="graph-clusterversion.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  # Graph size
  parser.add_argument("-w", "--width", type=int, default=1000, help="Sets width of all graphs")
  parser.add_argument("-t", "--height", type=int, default=700, help="Sets height of all graphs")

  parser.add_argument("-b", "--buffer-minutes", type=int, default=5,
                      help="Buffers start/end time stamps of graphs in minutes")

  # The path to the csv file to split into graphs
  parser.add_argument("data_file", type=str, help="The path to the clusterversion csv file to be graphed")

  cliargs = parser.parse_args()

  logger.info("Graph analyzed clusterversion data")
  # logger.info("CLI Args: {}".format(cliargs))
  if not pathlib.Path(cliargs.data_file).is_file():
    logger.error("File not found: {}".format(cliargs.data_file))
    sys.exit(1)

  results_directory = os.path.dirname(os.path.abspath(cliargs.data_file))
  base_file_name = os.path.splitext(os.path.basename(cliargs.data_file))[0]
  samples_csv_file = "{}/{}-samples.csv".format(results_directory, base_file_name)
  upgrade_graph_file_path = "{}/{}-all.png".format(results_directory, base_file_name)
  logger.info("Graphs will be placed in this directory: {}".format(results_directory))
  logger.info("Base graph name: {}".format(base_file_name))

  # Find start/end time for csv file and all recorded clusterversions
  clusterversions = OrderedDict()
  csv_start_time = ""
  csv_end_time = ""
  with open(cliargs.data_file, "r") as cluster_cv_csv:
    csv_reader = reader(cluster_cv_csv)
    # Remove the csv header first
    header = next(csv_reader)
    if header != None:
      for row in csv_reader:
        if row[2].lower() == "completed":
          row_starttime = datetime.strptime(row[3], "%Y-%m-%dT%H:%M:%SZ").replace(second=0, microsecond=0)
          row_endtime = datetime.strptime(row[4], "%Y-%m-%dT%H:%M:%SZ").replace(second=0, microsecond=0) + timedelta(minutes=1)

          # Determine the start and end times of the csv file
          if csv_start_time == "":
            csv_start_time = row_starttime
          else:
            if row_starttime < csv_start_time:
              # The row start time is earlier than the saved start time
              csv_start_time = row_starttime
          if csv_end_time == "":
            csv_end_time = row_endtime
          else:
            if row_endtime > csv_end_time:
              # The row end time is later than the saved end time
              csv_end_time = row_endtime

          if row[1] not in clusterversions:
            clusterversions[row[1]] = {"start": row_starttime, "end": row_endtime}
          else:
            if row_starttime < clusterversions[row[1]]["start"]:
              clusterversions[row[1]]["start"] = row_starttime
            if row_endtime > clusterversions[row[1]]["end"]:
              clusterversions[row[1]]["end"] = row_endtime
        else:
          logger.info("Partially updated cluster ({} :: {}) is not included in graphs".format(row[0], row[1]))

  # Subtract/Add buffer minutes to the start/end time stamps
  csv_start_time = csv_start_time - timedelta(minutes=cliargs.buffer_minutes)
  csv_end_time = csv_end_time + timedelta(minutes=cliargs.buffer_minutes)

  # Create 1 minute buckets
  data_buckets = OrderedDict()
  bucket_count = int((csv_end_time - csv_start_time).total_seconds() / 60) + 1
  for i in range(bucket_count):
    data_bk_ts = csv_start_time + timedelta(minutes=i)
    data_buckets[data_bk_ts] = OrderedDict()
    for version in clusterversions:
      data_buckets[data_bk_ts][version] = 0

  # Populate buckets by reading the original csv a 2nd time
  with open(cliargs.data_file, "r") as cluster_cv_csv:
    csv_reader = reader(cluster_cv_csv)
    # Remove the csv header first
    header = next(csv_reader)
    if header != None:
      for row in csv_reader:
        # Partially completed upgrades are not included in the graphs at this time
        if row[2].lower() == "completed":
          row_version = row[1]
          row_starttime = (datetime.strptime(row[3], "%Y-%m-%dT%H:%M:%SZ")).replace(second=0, microsecond=0)
          row_endtime = (datetime.strptime(row[4], "%Y-%m-%dT%H:%M:%SZ") + timedelta(minutes=1)).replace(second=0, microsecond=0)
          bucket_count = int((row_endtime - row_starttime).total_seconds() / 60) + 1
          for i in range(bucket_count):
            data_bk_ts = row_starttime + timedelta(minutes=i)
            data_buckets[data_bk_ts][row_version] += 1

  # Write the new samples csv file which contains:
  # datetime, ver1_updating_count, ver2_updating_count, ver3_updating_count ...
  with open(samples_csv_file, "w") as csv_file:
    # Write the header first
    csv_file.write("datetime")
    for version in clusterversions:
      csv_file.write(",{}".format(version))
    csv_file.write("\n")
    # Write the row
    for sample in data_buckets:
      csv_file.write("{}".format(sample.strftime("%Y-%m-%dT%H:%M:%SZ")))
      for version in clusterversions:
        csv_file.write(",{}".format(data_buckets[sample][version]))
      csv_file.write("\n")

  # Have pandas read in the samples csv for graphs
  df = pd.read_csv(samples_csv_file)

  title_upgrade = "Upgrade Graph - All clusterversions"
  y_upgrade = [version for version in clusterversions]
  l = {"value" : "# clusters", "date" : ""}

  logger.info("Creating Graph - {}".format(upgrade_graph_file_path))
  fig_graph = px.line(df, x="datetime", y=y_upgrade, labels=l, width=cliargs.width, height=cliargs.height)
  fig_graph.update_layout(title=title_upgrade, legend_orientation="v")
  fig_graph.write_image(upgrade_graph_file_path)

  for version in clusterversions:
    version_st = clusterversions[version]["start"] - timedelta(minutes=cliargs.buffer_minutes)
    version_et = clusterversions[version]["end"] + timedelta(minutes=cliargs.buffer_minutes)

    df['Datetime'] = pd.to_datetime(df['datetime'], format='%Y-%m-%dT%H:%M:%SZ')
    df = df.set_index(pd.DatetimeIndex(df['Datetime']))
    df_version = df.loc[str(version_st): str(version_et)]

    version_graph_file_path = "{}/{}-{}.png".format(results_directory, base_file_name, version)
    title_upgrade = "Upgrade Graph - {}".format(version)
    y_upgrade = [version]

    logger.info("Creating Graph - {}".format(version_graph_file_path))
    fig_version = px.line(df_version, x="datetime", y=y_upgrade, labels=l, width=cliargs.width, height=cliargs.height)
    fig_version.update_layout(title=title_upgrade, legend_orientation="v")
    fig_version.write_image(version_graph_file_path)

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
