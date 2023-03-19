#!/usr/bin/env python3
#
# Graph time-series csv from analyze-sno-upgrade script
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
logger = logging.getLogger("graph-sno-upgrade")
logging.Formatter.converter = time.gmtime


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Graph SNOs upgrade data",
      prog="graph-sno-upgrade.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  # Graph size
  parser.add_argument("-w", "--width", type=int, default=1000, help="Sets width of all graphs")
  parser.add_argument("-t", "--height", type=int, default=700, help="Sets height of all graphs")

  parser.add_argument("-b", "--buffer-minutes", type=int, default=5,
                      help="Buffers start/end time stamps of graphs in minutes")

  parser.add_argument("-a", "--batches", nargs="*", default=['0', '1'], help="The batches to include in the graph")

  # The path to the csv file to split into graphs
  parser.add_argument("data_file", type=str, help="The path to the sno-upgrade csv file to be graphed")

  cliargs = parser.parse_args()

  logger.info("Graph sno-upgrade data")
  logger.info("CLI Args: {}".format(cliargs))
  if not pathlib.Path(cliargs.data_file).is_file():
    logger.error("File not found: {}".format(cliargs.data_file))
    sys.exit(1)

  results_directory = os.path.dirname(os.path.abspath(cliargs.data_file))
  base_file_name = os.path.splitext(os.path.basename(cliargs.data_file))[0]
  samples_csv_file = "{}/{}-samples.csv".format(results_directory, base_file_name)
  upgrade_graph_file_path = "{}/{}-all.png".format(results_directory, base_file_name)
  logger.info("Graphs will be placed in this directory: {}".format(results_directory))
  logger.info("Base graph name: {}".format(base_file_name))

  # Find start/end time for csv file and all completed SNOs in the inspected batches
  batches = OrderedDict()
  csv_start_time = ""
  csv_end_time = ""
  with open(cliargs.data_file, "r") as sno_cv_csv:
    csv_reader = reader(sno_cv_csv)
    # Remove the csv header first
    header = next(csv_reader)
    if header != None:
      for row in csv_reader:
        batch = row[1]
        if batch in cliargs.batches:
          if row[8] != "":
            row_starttime = datetime.strptime(row[4], "%Y-%m-%dT%H:%M:%SZ").replace(second=0, microsecond=0)
            row_endtime = datetime.strptime(row[8], "%Y-%m-%dT%H:%M:%SZ").replace(second=0, microsecond=0) + timedelta(minutes=1)

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

            if batch not in batches:
              batches[batch] = {"start": row_starttime, "end": row_endtime}
            else:
              if row_starttime < batches[batch]["start"]:
                batches[batch]["start"] = row_starttime
              if row_endtime > batches[batch]["end"]:
                batches[batch]["end"] = row_endtime
          else:
            logger.info("Incomplete cluster {} upgrade (Status: {}) in batch {} is not included in graphs".format(row[2], row[3], batch))
        # else:
        #   logger.info("Cluster timings not inspected due to batch {} not include in {}".format(batch, cliargs.batches))


  # Subtract/Add buffer minutes to the start/end time stamps
  csv_start_time = csv_start_time - timedelta(minutes=cliargs.buffer_minutes)
  csv_end_time = csv_end_time + timedelta(minutes=cliargs.buffer_minutes)

  # Create 1 minute buckets
  data_buckets = OrderedDict()
  bucket_count = int((csv_end_time - csv_start_time).total_seconds() / 60) + 1
  for i in range(bucket_count):
    data_bk_ts = csv_start_time + timedelta(minutes=i)
    data_buckets[data_bk_ts] = OrderedDict()
    for batch in batches:
      data_buckets[data_bk_ts]["batch_{}_platform".format(batch)] = 0
      data_buckets[data_bk_ts]["batch_{}_operator".format(batch)] = 0

  # for ts in data_buckets:
  #   logger.info("TS: {}, Data: {}".format(ts, data_buckets[ts]))

  # Populate buckets by reading the original csv a 2nd time
  with open(cliargs.data_file, "r") as sno_cv_csv:
    csv_reader = reader(sno_cv_csv)
    # Remove the csv header first
    header = next(csv_reader)
    if header != None:
      for row in csv_reader:
        batch = row[1]
        if batch in cliargs.batches:
          if row[8] != "":
            row_platform_starttime = (datetime.strptime(row[4], "%Y-%m-%dT%H:%M:%SZ")).replace(second=0, microsecond=0)
            row_platform_endtime = (datetime.strptime(row[5], "%Y-%m-%dT%H:%M:%SZ")).replace(second=0, microsecond=0)
            row_operator_endtime = (datetime.strptime(row[8], "%Y-%m-%dT%H:%M:%SZ") + timedelta(minutes=1)).replace(second=0, microsecond=0)
            platform_bucket_count = int((row_platform_endtime - row_platform_starttime).total_seconds() / 60) + 1
            operator_bucket_count = int((row_operator_endtime - row_platform_endtime).total_seconds() / 60) + 1
            for i in range(platform_bucket_count):
              data_bk_ts = row_platform_starttime + timedelta(minutes=i)
              data_buckets[data_bk_ts]["batch_{}_platform".format(batch)] += 1
            for i in range(1, operator_bucket_count):
              data_bk_ts = row_platform_endtime + timedelta(minutes=(i))
              data_buckets[data_bk_ts]["batch_{}_operator".format(batch)] += 1

  # Write the new samples csv file which contains:
  # datetime, batch_0_platform, batch_0_operator, batch_1_platform ...
  with open(samples_csv_file, "w") as csv_file:
    # Write the header first
    csv_file.write("datetime")
    for batch in batches:
      csv_file.write(",batch_{}_platform".format(batch))
      csv_file.write(",batch_{}_operator".format(batch))
    csv_file.write("\n")
    # Write the row
    for sample in data_buckets:
      csv_file.write("{}".format(sample.strftime("%Y-%m-%dT%H:%M:%SZ")))
      for batch in batches:
        csv_file.write(",{}".format(data_buckets[sample]["batch_{}_platform".format(batch)]))
        csv_file.write(",{}".format(data_buckets[sample]["batch_{}_operator".format(batch)]))
      csv_file.write("\n")

  # Have pandas read in the samples csv for graphs
  df = pd.read_csv(samples_csv_file)

  title_upgrade = "SNO Upgrade Graph - Batches {}".format(",".join(batches.keys()))
  y_upgrade = []
  for batch in batches:
    y_upgrade.append("batch_{}_platform".format(batch))
    y_upgrade.append("batch_{}_operator".format(batch))

  l = {"value" : "# clusters", "date" : ""}

  logger.info("Creating Graph - {}".format(upgrade_graph_file_path))
  fig_sno = px.area(df, x="datetime", y=y_upgrade, labels=l, width=cliargs.width, height=cliargs.height)
  fig_sno.update_layout(title=title_upgrade, legend_orientation="v")
  fig_sno.write_image(upgrade_graph_file_path)

  for batch in batches:
    batch_st = batches[batch]["start"] - timedelta(minutes=cliargs.buffer_minutes)
    batch_et = batches[batch]["end"] + timedelta(minutes=cliargs.buffer_minutes)

    df['Datetime'] = pd.to_datetime(df['datetime'], format='%Y-%m-%dT%H:%M:%SZ')
    df = df.set_index(pd.DatetimeIndex(df['Datetime']))
    df_batch = df.loc[str(batch_st): str(batch_et)]

    batch_graph_file_path = "{}/{}-{}.png".format(results_directory, base_file_name, batch)
    title_upgrade = "Upgrade Graph Batch {}".format(batch)
    y_upgrade = ["batch_{}_platform".format(batch), "batch_{}_operator".format(batch)]

    logger.info("Creating Graph - {}".format(batch_graph_file_path))
    fig_batch = px.area(df_batch, x="datetime", y=y_upgrade, labels=l, width=cliargs.width, height=cliargs.height)
    fig_batch.update_layout(title=title_upgrade, legend_orientation="v")
    fig_batch.write_image(batch_graph_file_path)

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
