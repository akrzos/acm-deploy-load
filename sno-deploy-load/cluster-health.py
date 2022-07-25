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
import base64
from datetime import datetime
import json
from utils.command import command
import logging
import numpy as np
import requests
import sys
import time


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("cluster-health")
logging.Formatter.converter = time.gmtime

# Check if cluster is healthy/stable
# * Check if clusterversion is Available
# * Check if all clusteroperators Available
# * Check if all nodes are ready
# * Check for etcd leader elections in the last hour

# TODO: Future Enhancements:
# * parameters to enable/disable specific checks
# * parameter to increase length of time to check for etcd leader elections
# * Check if nodes flapped? (in last hour or larger period time)
# * Check critical ocp pods (Ex kube-apiserver) for restarts in last hour (or timeframe)
# * Abstract the prometheus query logic such that more queries can be completed easily
# * Create a test namespace, deployment, pod, service, route and check route for http 200, then tear down
# * Check MCP if they are upgraded/ready


def check_clusterversion(kubeconfig):
  logger.info("Checking clusterversion")
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "clusterversion", "version", "-o", "json"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("cluster-health, oc get clusterversion version rc: {}".format(rc))
    sys.exit(1)
  cv_data = json.loads(output)

  cv_available = [con for con in cv_data["status"]["conditions"] if con["type"] == "Available"][0]["status"]
  cv_failing = [con for con in cv_data["status"]["conditions"] if con["type"] == "Failing"][0]["status"]
  cv_progressing = [con for con in cv_data["status"]["conditions"] if con["type"] == "Progressing"][0]["status"]

  if cv_available == "True":
    logger.debug("Clusterversion is Available")
  else:
    logger.error("Clusterversion is not Available")
    sys.exit(1)

  if cv_failing == "True":
    logger.error("Clusterversion is Failing")
    sys.exit(1)
  else:
    logger.debug("Clusterversion is not Failing")

  if cv_progressing == "True":
    logger.error("Clusterversion is Progressing")
    sys.exit(1)
  else:
    logger.debug("Clusterversion is not Progressing")
  return True


def check_clusteroperators(kubeconfig):
  logger.info("Checking clusteroperators")
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "clusteroperators", "-o", "json"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("cluster-health, oc get clusteroperators rc: {}".format(rc))
    sys.exit(1)
  co_data = json.loads(output)

  for operator in co_data["items"]:
    operator_name = operator["metadata"]["name"]
    co_available = [con for con in operator["status"]["conditions"] if con["type"] == "Available"][0]["status"]
    co_degraded = [con for con in operator["status"]["conditions"] if con["type"] == "Degraded"][0]["status"]
    co_progressing = [con for con in operator["status"]["conditions"] if con["type"] == "Progressing"][0]["status"]
    logger.debug("Operator: {}, Available: {}, Progressing: {}, Degraded: {}".format(
        operator_name, co_available, co_progressing, co_degraded))
    if co_available != "True":
      logger.error("Clusteroperator {} is not Available".format(operator_name))
      sys.exit(1)

    if co_degraded == "True":
      logger.error("Clusteroperator {} is Degraded".format(operator_name))
      sys.exit(1)

    if co_progressing == "True":
      logger.error("Clusteroperator {} is Progressing".format(operator_name))
      sys.exit(1)
  return True


def check_nodes(kubeconfig):
  logger.info("Checking nodes")
  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "nodes", "-o", "json"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("cluster-health, oc get nodes rc: {}".format(rc))
    sys.exit(1)
  no_data = json.loads(output)

  for node in no_data["items"]:
    node_name = node["metadata"]["name"]
    no_ready = [con for con in node["status"]["conditions"] if con["type"] == "Ready"][0]["status"]
    no_memory = [con for con in node["status"]["conditions"] if con["type"] == "MemoryPressure"][0]["status"]
    no_disk = [con for con in node["status"]["conditions"] if con["type"] == "DiskPressure"][0]["status"]
    no_pid = [con for con in node["status"]["conditions"] if con["type"] == "PIDPressure"][0]["status"]
    logger.debug("Node: {}, Ready: {}, MemoryPressure: {}, DiskPressure: {}, PIDPressure: {}".format(
        node_name, no_ready, no_memory, no_disk, no_pid))
    if no_ready != "True":
      logger.error("Node {} is not Ready".format(node_name))
      sys.exit(1)

    if no_memory == "True":
      logger.error("Node {} is has MemoryPressure".format(node_name))
      sys.exit(1)

    if no_disk == "True":
      logger.error("Node {} is has DiskPressure".format(node_name))
      sys.exit(1)

    if no_pid == "True":
      logger.error("Node {} is has PIDPressure".format(node_name))
      sys.exit(1)
  return True

def check_etcd_leader_elections(kubeconfig):
  logger.info("Checking for etcd leader elections")
  prom_route = ""
  prom_token_name = ""
  prom_token_data = ""

  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "route", "thanos-querier", "-n", "openshift-monitoring", "-o", "jsonpath={.spec.host}"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("cluster-health, oc get route thanos-querier -n openshift-monitoring rc: {}".format(rc))
    sys.exit(1)

  if "thanos-querier" in output:
    prom_route = "https://{}".format(output)
  else:
    logger.error("Failed to find route for thanos-querier")
    sys.exit(1)

  logger.info("Route to Query: {}".format(prom_route))

  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "serviceaccount", "prometheus-k8s", "-n", "openshift-monitoring", "-o", "json"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("cluster-health, oc get serviceaccount prometheus-k8s -n openshift-monitoring rc: {}".format(rc))
    sys.exit(1)
  prom_sa_data = json.loads(output)

  for secret_name in prom_sa_data["secrets"]:
    if "token" in secret_name["name"]:
      prom_token_name = secret_name["name"]
      break

  if prom_token_name == "":
    logger.error("Unable to identify prometheus token name")
    sys.exit(1)

  oc_cmd = ["oc", "--kubeconfig", kubeconfig, "get", "secret", prom_token_name, "-n", "openshift-monitoring", "-o", "json"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("cluster-health, oc get secret {} -n openshift-monitoring rc: {}".format(prom_token_name, rc))
    sys.exit(1)
  prom_secret_data = json.loads(output)

  prom_token_data = (base64.b64decode(prom_secret_data["data"]["token"])).decode("utf-8")
  if prom_token_data == "":
    logger.error("Unable to identify prometheus token name")
    sys.exit(1)

  query = "increase(etcd_server_leader_changes_seen_total[1h])"
  query_endpoint = "{}/api/v1/query?query={}".format(prom_route, query)
  headers = {"Authorization": "Bearer {}".format(prom_token_data)}
  query_data = requests.post(query_endpoint, headers=headers, verify=False).json()

  logger.debug("Length of returned data: {}".format(len(query_data["data"]["result"])))

  for result in query_data["data"]["result"]:
    if float(result["value"][1]) > 0:
      logger.error("Pod: {}, Instance: {}, Result: {}".format(result["metric"]["pod"],result["metric"]["instance"], float(result["value"][1])))
      logger.error("etcd encountered leader election(s) in the last hour")
      sys.exit(1)
  return True


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Check that a cluster is healthy and stable",
      prog="cluster-health.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument("-k", "--kubeconfig", type=str, default="/root/bm/kubeconfig",
                      help="Changes which kubeconfig to connect to a cluster")

  parser.add_argument("-d", "--debug", action="store_true", default=False, help="Set log level debug")
  cliargs = parser.parse_args()

  if cliargs.debug:
    logger.setLevel(logging.DEBUG)

  logger.info("Checking cluster")
  ts = datetime.now().strftime("%Y%m%d-%H%M%S")

  if check_clusterversion(cliargs.kubeconfig):
    logger.info("Clusterversion is Available")
  if check_clusteroperators(cliargs.kubeconfig):
    logger.info("All clusteroperators are Available")
  if check_nodes(cliargs.kubeconfig):
    logger.info("All nodes are Ready")
  if check_etcd_leader_elections(cliargs.kubeconfig):
    logger.info("No detected etcd leader elections in the last hour")

  logger.info("Cluster appears healthy!!!")
  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
