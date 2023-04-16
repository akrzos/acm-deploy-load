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
import os
import pandas as pd
import plotly.express as px
import urllib3
import requests
import sys
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# TODO:
# * Graph cluster disk and network
# * OCP CPU, Memory, split on pods?
# * Total pod count??, total object count?
# * ACM Disk?, Network?

logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def calculate_query_offset(end_ts):
  cur_utc_unix_time = time.mktime(datetime.utcnow().timetuple())
  offset_minutes = (int(cur_utc_unix_time) - end_ts) / 60
  return "{}m".format(int(offset_minutes))


def acm_queries(report_dir, route, token, end_ts, duration, w, h):
  # ACM CPU/Memory
  sub_report_dir = os.path.join(report_dir, "acm")
  q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace=~'open-cluster-management.*|multicluster-engine'})"
  query_thanos(route, q, "ACM", token, end_ts, duration, sub_report_dir, "cpu-acm", "ACM CPU Cores Usage", "CPU", w, h)
  q = "sum(container_memory_working_set_bytes{cluster='',namespace!='minio', container!='',namespace=~'open-cluster-management.*|multicluster-engine'})"
  query_thanos(route, q, "ACM", token, end_ts, duration, sub_report_dir, "mem-acm", "ACM Memory Usage", "MEM", w, h)

  # ACM Open-cluster-management namespace CPU/Memory
  q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace='open-cluster-management'})"
  query_thanos(route, q, "ACM - open-cluster-management", token, end_ts, duration, sub_report_dir, "cpu-acm-ocm", "ACM open-cluster-management CPU Cores Usage", "CPU", w, h)
  q = "sum(container_memory_working_set_bytes{cluster='',namespace!='minio', container!='',namespace='open-cluster-management'})"
  query_thanos(route, q, "ACM - open-cluster-management", token, end_ts, duration, sub_report_dir, "mem-acm-ocm", "ACM open-cluster-management Memory Usage", "MEM", w, h)

  # ACM MCE CPU/Memory
  q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace='multicluster-engine'})"
  query_thanos(route, q, "ACM - MCE", token, end_ts, duration, sub_report_dir, "cpu-acm-mce", "ACM MCE CPU Cores Usage", "CPU", w, h)
  q = "sum(container_memory_working_set_bytes{cluster='',namespace!='minio', container!='',namespace='multicluster-engine'})"
  query_thanos(route, q, "ACM - MCE", token, end_ts, duration, sub_report_dir, "mem-acm-mce", "ACM MCE Memory Usage", "MEM", w, h)

  # ACM MCE Assisted-installer CPU/Memory
  q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace='multicluster-engine',pod=~'assisted-service.*'})"
  query_thanos(route, q, "ACM - MCE Assisted-Installer", token, end_ts, duration, sub_report_dir, "cpu-acm-mce-ai", "ACM Assisted-Installer CPU Cores Usage", "CPU", w, h)
  q = "sum(container_memory_working_set_bytes{cluster='', container!='',namespace='multicluster-engine',pod=~'assisted-service.*'})"
  query_thanos(route, q, "ACM - MCE Assisted-Installer", token, end_ts, duration, sub_report_dir, "mem-acm-mce-ai", "ACM MCE Memory Usage", "MEM", w, h)

  # ACM Observability CPU/Memory
  q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace='open-cluster-management-observability'})"
  query_thanos(route, q, "ACM - Observability", token, end_ts, duration, sub_report_dir, "cpu-acm-obs", "ACM Observability CPU Cores Usage", "CPU", w, h)
  q = "sum(container_memory_working_set_bytes{cluster='', container!='',namespace='open-cluster-management-observability'})"
  query_thanos(route, q, "ACM - Observability", token, end_ts, duration, sub_report_dir, "mem-acm-obs", "ACM Observability Memory Usage", "MEM", w, h)

  q = "sum(container_memory_working_set_bytes{cluster='',namespace='open-cluster-management-observability', pod=~'observability-thanos-receive-default.*', container!=''})"
  query_thanos(route, q, "ACM - Observability Receiver", token, end_ts, duration, sub_report_dir, "mem-acm-obs-rcv-total", "ACM Observability Receiver Memory Usage", "MEM", w, h)
  q = "sum by (pod) (container_memory_working_set_bytes{cluster='',namespace='open-cluster-management-observability', pod=~'observability-thanos-receive-default.*', container!=''})"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "mem-acm-obs-rcv-pod", "ACM Observability Receiver Memory Usage", "MEM", w, h)

  # ACM Search CPU/Memory
  q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace='open-cluster-management',pod=~'search.*'})"
  query_thanos(route, q, "ACM - Search", token, end_ts, duration, sub_report_dir, "cpu-acm-search", "ACM Search CPU Cores Usage", "CPU", w, h)
  q = "sum(container_memory_working_set_bytes{cluster='', container!='',namespace='open-cluster-management',pod=~'search.*'})"
  query_thanos(route, q, "ACM - Search", token, end_ts, duration, sub_report_dir, "mem-acm-search", "ACM Search Memory Usage", "MEM", w, h)

  # Managedcluster objects
  q = "apiserver_storage_objects{resource=~'managedclusters.cluster.open-cluster-management.io'}"
  query_thanos(route, q, "instance", token, end_ts, duration, sub_report_dir, "acm-mc", "Managedcluster Objects", "Count", w, h)


def cluster_node_queries(report_dir, route, token, end_ts, duration, w, h):
  # Cluster CPU/Memory
  sub_report_dir = os.path.join(report_dir, "cluster")
  q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='', namespace!='minio'})"
  query_thanos(route, q, "cluster", token, end_ts, duration, sub_report_dir, "cpu-cluster", "Cluster CPU Cores Usage", "CPU", w, h)
  q = "sum(container_memory_working_set_bytes{cluster='',namespace!='minio', container!=''})"
  query_thanos(route, q, "cluster", token, end_ts, duration, sub_report_dir, "mem-cluster", "Cluster Memory Usage", "MEM", w, h)
  # Node CPU/Memory
  sub_report_dir = os.path.join(report_dir, "node")
  q = "sum by(node) (node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace!='minio'})"
  query_thanos(route, q, "node", token, end_ts, duration, sub_report_dir, "cpu-node", "Node CPU Cores Usage", "CPU", w, h)
  q = "sum by(node) (container_memory_working_set_bytes{cluster='',namespace!='minio', container!=''})"
  query_thanos(route, q, "node", token, end_ts, duration, sub_report_dir, "mem-node", "Node Memory Usage", "MEM", w, h)


def etcd_queries(report_dir, route, token, end_ts, duration, w, h):
  sub_report_dir = os.path.join(report_dir, "etcd")
  q = "etcd_mvcc_db_total_size_in_bytes"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "db-size", "ETCD DB Size", "DISK", w, h)
  q = "etcd_mvcc_db_total_size_in_use_in_bytes"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "db-size-in-use", "ETCD DB Size In-use", "DISK", w, h)
  q = "histogram_quantile(0.99, sum(rate(etcd_disk_wal_fsync_duration_seconds_bucket{job='etcd'}[5m])) by (instance, pod, le))"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "fsync-duration", "ETCD Disk Sync Duration", "Seconds", w, h)
  q = "histogram_quantile(0.99, irate(etcd_disk_backend_commit_duration_seconds_bucket[5m]))"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "backend-commit-duration", "ETCD Backend Commit Duration", "Seconds", w, h)
  q = "changes(etcd_server_leader_changes_seen_total{job='etcd'}[1d])"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "total-leader-elections", "ETCD Leader Elections Per Day", "Count", w, h)
  q = "max by (pod) (etcd_server_leader_changes_seen_total)"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "leader-changes", "ETCD Max Leader Changes", "Count", w, h)
  q = "histogram_quantile(0.99, irate(etcd_network_peer_round_trip_time_seconds_bucket[1m]))"
  query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "peer-roundtrip-time", "ETCD Peer Roundtrip Time", "Seconds", w, h)


def ocp_queries(report_dir, route, token, end_ts, duration, w, h):
  ocp_namespaces = [
    "openshift-apiserver",
    "openshift-controller-manager",
    "openshift-etcd",
    "openshift-gitops",
    "openshift-ingress",
    "openshift-kni-infra",
    "openshift-kube-apiserver",
    "openshift-kube-controller-manager",
    "openshift-kube-scheduler",
    "openshift-local-storage",
    "openshift-monitoring"
  ]
  sub_report_dir = os.path.join(report_dir, "ocp")
  for ns in ocp_namespaces:
    q = "sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace='" + ns + "'})"
    query_thanos(route, q, ns, token, end_ts, duration, sub_report_dir, "cpu-{}".format(ns), "{} CPU Cores Usage".format(ns), "CPU", w, h)
    q = "sum(container_memory_working_set_bytes{cluster='',namespace!='minio', container!='',namespace='" + ns + "'})"
    query_thanos(route, q, ns, token, end_ts, duration, sub_report_dir, "mem-{}".format(ns), "{} CPU Cores Usage".format(ns), "MEM", w, h)

    # Needs work as pods don't always "survive" complete query time period
    # # split by pods in the namespaces
    # q = "sum by (pod) (node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{cluster='',namespace='" + ns + "'})"
    # query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "cpu-{}-pod".format(ns), "{} CPU Cores Usage".format(ns), "CPU", w, h)
    # q = "sum by (pod) (container_memory_working_set_bytes{cluster='',namespace!='minio', container!='',namespace='" + ns + "'})"
    # query_thanos(route, q, "pod", token, end_ts, duration, sub_report_dir, "mem-{}-pod".format(ns), "{} CPU Cores Usage".format(ns), "MEM", w, h)

  q = "(sum by (container) (kube_pod_container_status_restarts_total) > 3)"
  query_thanos(route, q, "container", token, end_ts, duration, sub_report_dir, "pod-restarts", "Pod Restarts > 3", "Count", w, h)


def query_thanos(route, query, series_label, token, end_ts, duration, directory, fname, g_title, y_unit, g_width, g_height, resolution="1m"):
  logger.info("Querying data")

  if y_unit == "CPU":
    y_title = "CPU (Cores)"
  elif y_unit == "MEM":
    y_title = "Memory (GiB)"
  elif y_unit == "DISK":
    y_title = "Disk (GB)"
  else:
    y_title = y_unit

  # Determine query offset from end timestamp
  offset = calculate_query_offset(end_ts)

  query_complete = query + "[" + duration + ":" + resolution + "] offset " + offset
  logger.info("Query: {}".format(query_complete))
  query_endpoint = "{}/api/v1/query?query={}".format(route, query_complete)
  headers = {"Authorization": "Bearer {}".format(token)}
  # logger.debug("Query Endpoint: {}".format(query_endpoint))
  query_data = requests.post(query_endpoint, headers=headers, verify=False).json()
  # print("query_data: {}".format(json.dumps(query_data, indent=4)))
  logger.debug("Length of returned result data: {}".format(len(query_data["data"]["result"])))

  if len(query_data["data"]["result"]) == 0:
    logger.warning("Empty data returned from query")
  else:
    frame = {}
    series = []
    for metric in query_data["data"]["result"]:
      # Get/set the datetime series
      if len(frame) == 0:
        frame["datetime"] = pd.Series([datetime.utcfromtimestamp(x[0]) for x in metric["values"]], name="datetime")
      # Need to rework how datetime series is generated and how series are merged together.  Pods come and go and their
      # series of data is shorter and not paded, so we need some sort of "merge" method instead of picking the largest.
      # Also not all series start at the same datetime. ugh
      # else:
      #   logger.debug("length of metrics: {}, length of previous datetime: {}".format(len(metric["values"]), len(frame["datetime"])))
      #   if len(metric["values"]) > len(frame["datetime"]):
      #     frame["datetime"] = pd.Series([datetime.utcfromtimestamp(x[0]) for x in metric["values"]], name="datetime")
      # Get the metrics series
      if series_label not in metric["metric"]:
        logger.debug("Num of values: {}".format(len(metric["values"])))
        if y_unit == "MEM":
          bytes_to_gib = 1024 * 1024 * 1024
          frame[series_label] = pd.Series([float(x[1]) / bytes_to_gib for x in metric["values"]], name=series_label)
        elif y_unit == "DISK":
          bytes_to_gb = 1000 * 1000 * 1000
          frame[series_label] = pd.Series([float(x[1]) / bytes_to_gb for x in metric["values"]], name=series_label)
        else:
          frame[series_label] = pd.Series([float(x[1]) for x in metric["values"]], name=series_label)
        series.append(series_label)
      else:
        logger.debug("{}: {}, Num of values: {}".format(series_label, metric["metric"][series_label], len(metric["values"])))
        if y_unit == "MEM":
          bytes_to_gib = 1024 * 1024 * 1024
          frame[metric["metric"][series_label]] = pd.Series([float(x[1]) / bytes_to_gib for x in metric["values"]], name=metric["metric"][series_label])
        elif y_unit == "DISK":
          bytes_to_gb = 1000 * 1000 * 1000
          frame[metric["metric"][series_label]] = pd.Series([float(x[1]) / bytes_to_gb for x in metric["values"]], name=metric["metric"][series_label])
        else:
          frame[metric["metric"][series_label]] = pd.Series([float(x[1]) for x in metric["values"]], name=metric["metric"][series_label])
        series.append(metric["metric"][series_label])

    df = pd.DataFrame(frame)

    csv_dir = os.path.join(directory, "csv")
    stats_dir = os.path.join(directory, "stats")

    # Write graph and stats file
    with open("{}/{}.stats".format(stats_dir, fname), "a") as stats_file:
      stats_file.write(str(df.describe()))
    df.to_csv("{}/{}.csv".format(csv_dir, fname))

    l = {"value" : y_title, "date" : ""}
    fig_cluster_node = px.line(df, x="datetime", y=series, labels=l, width=g_width, height=g_height)
    fig_cluster_node.update_layout(title=g_title, legend_orientation="v")
    fig_cluster_node.write_image("{}/{}.png".format(directory, fname))

  logger.info("Completed querying and graphing data")


def valid_datetime(datetime_arg):
    try:
        return datetime.strptime(datetime_arg, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise argparse.ArgumentTypeError("Datetime ({}) not valid! Expected format, 'YYYY-MM-DDTHH:mm:SSZ'!".format(datetime_arg))


def main():
  # Start time of script (Now)
  start_time = time.time()
  # Default end time for analysis is the start time of the script
  # Default start time for analysis is start time of script minus one hour (Default analyzes one hour from now)
  default_ap_end_time = datetime.utcfromtimestamp(start_time)
  default_ap_start_time = datetime.utcfromtimestamp(start_time - (60 * 60))

  parser = argparse.ArgumentParser(
      description="Query and Graph Prometheus data off a live OpenShift cluster",
      prog="graph-acm-deploy.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument("-k", "--kubeconfig", type=str, default="/root/bm/kubeconfig",
                      help="Changes which kubeconfig to connect to a cluster")

  parser.add_argument("-s", "--start-ts", type=valid_datetime, default=default_ap_start_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
                      help="Sets start utc timestamp")
  parser.add_argument("-e", "--end-ts", type=valid_datetime, default=default_ap_end_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
                      help="Sets end utc timestamp")

  # Quick way to add small amount of time to front and end of test period
  parser.add_argument("-b", "--buffer-minutes", type=int, default=5,
                      help="Buffers start/end time stamps of data selected in minutes")

  parser.add_argument("-p", "--prefix", type=str, default="pa", help="Sets directory name prefix for files")

  # Graph size
  parser.add_argument("-w", "--width", type=int, default=1400, help="Sets width of all graphs")
  parser.add_argument("-t", "--height", type=int, default=1000, help="Sets height of all graphs")

  # Directory to place graphs
  parser.add_argument("results_directory", type=str, help="The location to place graphs and stats files")

  parser.add_argument("-d", "--debug", action="store_true", default=False, help="Set log level debug")
  cliargs = parser.parse_args()

  if cliargs.debug:
    logger.setLevel(logging.DEBUG)
  logger.debug("CLI Args: {}".format(cliargs))

  logger.info("Analyze Prometheus")

  w = cliargs.width
  h = cliargs.height

  # Set/Validate start and end timestamps for queries
  buffer_time = (cliargs.buffer_minutes * 60)
  logger.info("Buffer time set to: {} seconds".format(buffer_time))

  logger.info("Start timestamp set: {}".format(cliargs.start_ts))
  q_start_ts = int(time.mktime(cliargs.start_ts.timetuple())) - buffer_time
  logger.info("Start timestamp Unix: {}".format(q_start_ts))

  logger.info("End timestamp set: {}".format(cliargs.end_ts))
  q_end_ts = int(time.mktime(cliargs.end_ts.timetuple())) + buffer_time
  logger.info("End timestamp Unix: {}".format(q_end_ts))

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

  # Create the results directories to store data into
  directories = [
    "acm",
    "cluster",
    "etcd",
    "node",
    "ocp",
  ]
  report_dir = os.path.join(cliargs.results_directory, "{}-{}".format(cliargs.prefix,
      datetime.utcfromtimestamp(start_time).strftime("%Y%m%d-%H%M%S")))
  logger.debug("Creating report directory: {}".format(report_dir))
  os.mkdir(report_dir)
  for dir in directories:
    sub_report_dir = os.path.join(report_dir, dir)
    csv_dir = os.path.join(sub_report_dir, "csv")
    stats_dir = os.path.join(sub_report_dir, "stats")
    os.mkdir(sub_report_dir)
    os.mkdir(csv_dir)
    os.mkdir(stats_dir)

  cluster_node_queries(report_dir, route, token, q_end_ts, q_duration, w, h)

  etcd_queries(report_dir, route, token, q_end_ts, q_duration, w, h)

  ocp_queries(report_dir, route, token, q_end_ts, q_duration, w, h)

  acm_queries(report_dir, route, token, q_end_ts, q_duration, w, h)

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
