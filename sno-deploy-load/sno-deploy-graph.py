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
from datetime import datetime
import logging
import pandas as pd
import pathlib
import plotly as py
import plotly.figure_factory as ff
import plotly.graph_objects as go
import plotly.express as px
import sys
import time

# TODO:
# Produce concurrency workload graph


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("sno-deploy-graph")
logging.Formatter.converter = time.gmtime


def main():
  parser = argparse.ArgumentParser(
      description="Produce graphs from sno-deploy-load monitor data",
      prog="sno-deploy-graph.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  # Graph Title Data
  parser.add_argument("--acm-version", type=str, default="2.5.0", help="Sets ACM version for graph title")
  parser.add_argument("--test-version", type=str, default="ZTP Scale Run 1", help="Sets test version for graph title")
  parser.add_argument("--hub-version", type=str, default="4.10.8", help="Sets OCP Hub version for graph title")
  parser.add_argument("--sno-version", type=str, default="4.10.8", help="Sets OCP SNO version for graph title")
  parser.add_argument("--wan-emulation", type=str, default="(50ms/0.02)", help="Sets WAN emulation for graph title")

  # Name of csv file found in results directory
  parser.add_argument("--monitor-data-file-name", type=str, default="monitor_data.csv",
      help="The name of the monitor data csv file.")

  # Graph size
  parser.add_argument("-w", "--width", type=int, default=1000, help="Sets width of all graphs")
  parser.add_argument("-t", "--height", type=int, default=700, help="Sets height of all graphs")

  # Directory to find the csv file for graphing
  parser.add_argument("results_directory", type=str, help="The location of a sno-deploy-load results")

  cliargs = parser.parse_args()

  logger.info("SNO Deploy Graph")
  # logger.info("CLI Args: {}".format(cliargs))
  md_csv_file = "{}/{}".format(cliargs.results_directory, cliargs.monitor_data_file_name)
  if not pathlib.Path(md_csv_file).is_file():
    logger.error("File not found: {}".format(md_csv_file))
    sys.exit(1)

  df = pd.read_csv(md_csv_file)

  sno_inited = df["sno_init"].values[-1]
  sno_completed = df["sno_install_completed"].values[-1]
  managed = df["managed"].values[-1]
  policy_inited = df["policy_init"].values[-1]
  policy_compliant = df["policy_compliant"].values[-1]

  title_sno = "ACM {} {} ({}/{} clusters)<br>OCP {}, SNO {}, W/E {}".format(cliargs.acm_version, cliargs.test_version,
      sno_completed, sno_inited, cliargs.hub_version, cliargs.sno_version, cliargs.wan_emulation)
  title_managed = "ACM {} {} ({}/{} clusters)<br>OCP {}, SNO {}, W/E {}".format(cliargs.acm_version,
      cliargs.test_version, managed, sno_inited, cliargs.hub_version, cliargs.sno_version, cliargs.wan_emulation)
  title_policy = "ACM {} {} ({}/{} policy)<br>OCP {}, SNO {}, W/E {}".format(cliargs.acm_version, cliargs.test_version,
      policy_compliant, policy_inited, cliargs.hub_version, cliargs.sno_version, cliargs.wan_emulation)

  y_sno = ["sno_init", "sno_booted", "sno_discovered", "sno_installing", "sno_install_failed", "sno_install_completed"]
  y_sno2 = ["sno_applied", "sno_init", "sno_booted", "sno_discovered", "sno_installing", "sno_install_failed",
      "sno_install_completed"]
  y_managed = ["sno_init", "sno_install_failed", "sno_install_completed", "managed"]
  y_policy = ["sno_init", "sno_install_completed", "managed", "policy_init", "policy_applying", "policy_timedout",
      "policy_compliant"]
  y_share = ["sno_init", "sno_booted", "sno_discovered", "sno_installing", "sno_install_failed",
      "sno_install_completed", "managed", "policy_applying", "policy_timedout", "policy_compliant"]
  y_share2 = ["sno_applied", "sno_init", "sno_booted", "sno_discovered", "sno_installing", "sno_install_failed",
      "sno_install_completed", "managed", "policy_applying", "policy_timedout", "policy_compliant"]

  l = {"value" : "# clusters", "date" : ""}

  ts = datetime.utcfromtimestamp(time.time()).strftime("%Y%m%d-%H%M%S")

  logger.info("Creating Graph - {}/sno-{}.png".format(cliargs.results_directory, ts))
  fig_sno = px.line(df, x="date", y=y_sno, labels=l, width=cliargs.width, height=cliargs.height)
  fig_sno.update_layout(title=title_sno, legend_orientation="v")
  fig_sno.write_image("{}/sno-{}.png".format(cliargs.results_directory, ts))

  logger.info("Creating Graph - {}/sno2-{}.png".format(cliargs.results_directory, ts))
  fig_sno = px.line(df, x="date", y=y_sno2, labels=l, width=cliargs.width, height=cliargs.height)
  fig_sno.update_layout(title=title_sno, legend_orientation="v")
  fig_sno.write_image("{}/sno2-{}.png".format(cliargs.results_directory, ts))

  logger.info("Creating Graph - {}/managed-{}.png".format(cliargs.results_directory, ts))
  fig_managed = px.line(df, x="date", y=y_managed, labels=l, width=cliargs.width, height=cliargs.height)
  fig_managed.update_layout(title=title_managed, legend_orientation="v")
  fig_managed.write_image("{}/managed-{}.png".format(cliargs.results_directory, ts))

  logger.info("Creating Graph - {}/policy-{}.png".format(cliargs.results_directory, ts))
  fig_policy = px.line(df, x="date", y=y_policy, labels=l, width=cliargs.width, height=cliargs.height)
  fig_policy.update_layout(title=title_policy, legend_orientation="v")
  fig_policy.write_image("{}/policy-{}.png".format(cliargs.results_directory, ts))

  logger.info("Creating Graph - {}/share-{}.png".format(cliargs.results_directory, ts))
  fig_share = px.line(df, x="date", y=y_share, labels=l, width=cliargs.width, height=cliargs.height)
  fig_share.update_layout(title=title_sno, legend_orientation="v")
  fig_share.write_image("{}/share-{}.png".format(cliargs.results_directory, ts))

  logger.info("Creating Graph - {}/share2-{}.png".format(cliargs.results_directory, ts))
  fig_share = px.line(df, x="date", y=y_share2, labels=l, width=cliargs.width, height=cliargs.height)
  fig_share.update_layout(title=title_sno, legend_orientation="v")
  fig_share.write_image("{}/share2-{}.png".format(cliargs.results_directory, ts))

  logger.info("Complete")

if __name__ == "__main__":
  sys.exit(main())
