#!/usr/bin/env python3
#
# Query and graph prometheus data in an OpenShift Cluster
#
#  Copyright 2023 Red Hat
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

# import prometheus_api_client
import argparse
from datetime import datetime
from utils.common_ocp import get_ocp_version
from utils.common_ocp import get_prometheus_token
from utils.common_ocp import get_thanos_querier_route
import json
import logging
import pandas as pd
import plotly.express as px
import requests
import sys
import time


# TODO:
# * proper timestamp argparse implementation
# * Graph cluster cpu and Memory
# * Graph cluster disk and network
# * OCP CPU, Memory, other?
# * Total pod count??, total object count?
# * etcd metrics?
# * ACM CPU, Memory, Disk?, Network?

logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def calculate_query_offset(end_ts):
  cur_utc_unix_time = time.mktime(datetime.utcnow().timetuple())
  offset_minutes = (int(cur_utc_unix_time) - end_ts) / 60
  return "{}m".format(int(offset_minutes))


def query_thanos(route, query, series_label, token, end_ts, duration, directory, fname, g_title, y_title, resolution="1m"):
  logger.info("Querying data")

  # Determine query offset from end timestamp
  offset = calculate_query_offset(end_ts)

  query_complete = query + "[" + duration + ":" + resolution + "] offset " + offset
  logger.debug("Query: {}".format(query_complete))
  query_endpoint = "{}/api/v1/query?query={}".format(route, query_complete)
  headers = {"Authorization": "Bearer {}".format(token)}
  # logger.debug("Query Endpoint: {}".format(query_endpoint))
  query_data = requests.post(query_endpoint, headers=headers, verify=False).json()
  # print("query_data: {}".format(json.dumps(query_data, indent=4)))
  logger.debug("Length of returned result data: {}".format(len(query_data["data"]["result"])))

  if len(query_data["data"]["result"]) == 0:
    logger.warn("Empty data returned from query")
  else:
    frame = {}
    series = []
    for metric in query_data["data"]["result"]:
      if len(frame) == 0:
        frame["datetime"] = pd.Series([datetime.utcfromtimestamp(x[0]) for x in metric["values"]], name="datetime")
      if series_label not in metric["metric"]:
        logger.debug("Num of values: {}".format(len(metric["values"])))
        frame[series_label] = pd.Series([float(x[1]) for x in metric["values"]], name=series_label)
        series.append(series_label)
      else:
        logger.debug("{}: {}, Num of values: {}".format(series_label, metric["metric"][series_label], len(metric["values"])))
        frame[metric["metric"][series_label]] = pd.Series([float(x[1]) for x in metric["values"]], name=metric["metric"][series_label])
        series.append(metric["metric"][series_label])

    df = pd.DataFrame(frame)

    # Write graph and stats file
    l = {"value" : y_title, "date" : ""}
    fig_cluster_node = px.line(df, x="datetime", y=series, labels=l, width=1000, height=700)
    fig_cluster_node.update_layout(title=g_title, legend_orientation="v")
    fig_cluster_node.write_image("{}/{}.png".format(directory, fname))
    with open("{}/{}.stats".format(directory, fname), "a") as stats_file:
      stats_file.write(str(df.describe()))
    df.to_csv("{}/{}.csv".format(directory, fname))

  logger.info("Completed querying and graphing data")


def main():
  start_time = time.time()
  # Timestamp for files generated
  ts = datetime.utcfromtimestamp(start_time).strftime("%Y%m%d-%H%M%S")

  parser = argparse.ArgumentParser(
      description="Query and Graph Prometheus data off a live OpenShift cluster",
      prog="graph-acm-deploy.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument("-k", "--kubeconfig", type=str, default="/root/bm/kubeconfig",
                      help="Changes which kubeconfig to connect to a cluster")

  # parser.add_argument("-s", "--start-ts", type=str, default="2023-04-04T22:56:54Z",
  #                     help="Sets start utc timestamp (Ex '2023-04-04T22:56:54Z')")
  # parser.add_argument("-e", "--end-ts", type=str, default="2023-04-05T09:02:57Z",
  #                     help="Sets end utc timestamp (Ex '2023-04-05T09:02:57Z')")

  parser.add_argument("-s", "--start-ts", type=str, default="2023-04-04T22:56:54Z",
                      help="Sets start utc timestamp (Ex '2023-04-04T22:56:54Z')")
  parser.add_argument("-e", "--end-ts", type=str, default="2023-04-05T09:02:57Z",
                      help="Sets end utc timestamp (Ex '2023-04-05T09:02:57Z')")

  # Quick way to add small amount of time to front and end of test period
  parser.add_argument("-b", "--buffer-minutes", type=int, default=5,
                      help="Buffers start/end time stamps of data selected in minutes")

  # Graph size
  # parser.add_argument("-w", "--width", type=int, default=1000, help="Sets width of all graphs")
  # parser.add_argument("-t", "--height", type=int, default=700, help="Sets height of all graphs")

  # Directory to place graphs
  parser.add_argument("results_directory", type=str, help="The location to place graphs and stats files")

  parser.add_argument("-d", "--debug", action="store_true", default=False, help="Set log level debug")
  cliargs = parser.parse_args()

  if cliargs.debug:
    logger.setLevel(logging.DEBUG)
  logger.debug("CLI Args: {}".format(cliargs))

  logger.info("Analyze Prometheus")

  # Set/Validate start and end timestamps for queries
  q_end_ts = ""
  q_start_ts = ""
  buffer_time = (cliargs.buffer_minutes * 60)
  if cliargs.end_ts:
    logger.info("End timestamp set: {}".format(cliargs.end_ts))
    q_end_ts = int(time.mktime(datetime.strptime(cliargs.end_ts, "%Y-%m-%dT%H:%M:%SZ").timetuple())) + buffer_time
    logger.info("End timestamp Unix: {}".format(q_end_ts))
  else:
    q_end_ts = int(start_time)
    logger.info("End timestamp not set, defaulting to now: {}".format(q_end_ts))
  if cliargs.start_ts:
    logger.info("Start timestamp set: {}".format(cliargs.start_ts))
    q_start_ts = int(time.mktime(datetime.strptime(cliargs.start_ts, "%Y-%m-%dT%H:%M:%SZ").timetuple())) - buffer_time
    logger.info("Start timestamp Unix: {}".format(q_start_ts))
  else:
    q_start_ts = q_end_ts - (60 * 60)
    logger.info("Start timestamp not set, defaulting end timestamp - 1 hour: {}".format(q_start_ts))
  analyze_duration = q_end_ts - q_start_ts
  # Ensure start/end are at least 5 minutes apart
  if analyze_duration <= (60 * 5):
    logger.error("Start/End timestamps are too close")
    sys.exit(1)
  q_duration = "{}m".format(int(analyze_duration / 60))
  logger.info("Examining duration {}s : {}".format(analyze_duration, q_duration))
  # Finished with start/end time

  version = get_ocp_version(cliargs.kubeconfig)
  logger.info("oc version reports cluster is {}.{}.{}".format(version["major"], version["minor"], version["patch"]))

  route = get_thanos_querier_route(cliargs.kubeconfig)
  if route == "":
    logger.error("Could not obtain the thanos querier route")
    sys.exit(1)
  logger.info("Route to Query: {}".format(route))

  token = get_prometheus_token(cliargs.kubeconfig, version)
  if token == "":
    logger.error("Could not obtain the prometheus token")
    sys.exit(1)

  ############################################################################
  # Cluster / Node Queries
  ############################################################################
  # Cluster CPU graph
  q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='', namespace!='minio'})"
  query_thanos(route, q, "Cluster", token, q_end_ts, q_duration, cliargs.results_directory, "cpu-cluster-{}".format(ts), "Cluster CPU Cores Usage", "CPU (Cores)")
  # Node CPU graphs
  q = "sum by(node) (node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace!='minio'})"
  query_thanos(route, q, "node", token, q_end_ts, q_duration, cliargs.results_directory, "cpu-node-{}".format(ts), "Node CPU Cores Usage", "CPU (Cores)")


  ############################################################################
  # ACM Queries
  ############################################################################
  # ACM CPU graphs
  q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace!='minio',namespace=~'open-cluster-management.*|multicluster-engine'})"
  query_thanos(route, q, "ACM", token, q_end_ts, q_duration, cliargs.results_directory, "cpu-acm-{}".format(ts), "ACM CPU Cores Usage", "CPU (Cores)")


  # Managedcluster objects
  query = "apiserver_storage_objects{resource=~'managedclusters.cluster.open-cluster-management.io'}"
  query_thanos(route, query, "instance", token, q_end_ts, q_duration, cliargs.results_directory, "acm-mc-{}".format(ts), "Managedcluster Objects", "Count")



  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
