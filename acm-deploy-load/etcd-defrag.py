#!/usr/bin/env python3
#
# Used to manuall defrag etcd on an OCP cluster and remove nospace alarm
#
#  Copyright 2024 Red Hat
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
import json
import logging
import sys
import time
from utils.command import command


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Manually defrag an OCP etcd database", prog="etcd-defrag.py",
      formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument("-k", "--kubeconfig", type=str, default="/root/bm/kubeconfig",
                      help="Changes which kubeconfig to connect to a cluster")

  parser.add_argument("-a", "--disarm-alarms", action="store_true", default=False, help="Disarm alarms")
  parser.add_argument("-c", "--compact", action="store_true", default=False, help="Compact etcd keyspace")

  parser.add_argument("-d", "--debug", action="store_true", default=False, help="Set log level debug")
  cliargs = parser.parse_args()

  if cliargs.debug:
    logger.setLevel(logging.DEBUG)

  logger.info("Defrag ETCD")

  # Get etcd pods
  oc_cmd = ["oc", "--kubeconfig", cliargs.kubeconfig, "get", "po", "-n", "openshift-etcd", "-l", "k8s-app=etcd", "-o", "json"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("etcd-defrag, oc get po -n openshift-etcd -l k8s-app=etcd rc: {}".format(rc))
    sys.exit(1)
  pod_data = json.loads(output)

  pods = {}
  etcd_pod = ""
  leader_pod = ""

  for pod in pod_data["items"]:
    pod_name = pod["metadata"]["name"]
    pod_ip = pod["status"]["podIP"]
    if etcd_pod == "":
      etcd_pod = pod_name
    pods[pod_name] = {"ip": pod_ip, "revision": 0}
    logger.info("Etcd pod: {} has IP: {}".format(pod_name, pod_ip))

  # Get etcd endpoints
  oc_cmd = ["oc", "--kubeconfig", cliargs.kubeconfig, "rsh", "-n", "openshift-etcd", etcd_pod, "etcdctl", "endpoint", "status", "--cluster", "-w", "json"]
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("etcd-defrag, oc rsh -n openshift-etcd {} etcdctl endpoint status rc: {}".format(etcd_pod, rc))
    sys.exit(1)
  etcd_ep_status = json.loads(output)

  # logger.info(etcd_ep_status)

  # Determine which pod is the etcd leader
  for etcd_ep in etcd_ep_status:
    endpoint = etcd_ep["Endpoint"]
    member_id = etcd_ep["Status"]["header"]["member_id"]
    revision = etcd_ep["Status"]["header"]["revision"]
    leader_id = etcd_ep["Status"]["leader"]
    logger.info("Etcd endpoint: {}, Member ID: {}, Leader ID: {}, Revision: {}".format(endpoint, member_id, leader_id, revision))
    for pod in pods:
      if pods[pod]["ip"] in endpoint:
        pods[pod]["revision"] = str(revision)
        if member_id == leader_id:
          logger.info("Leader endpoint is: {}".format(endpoint))
          leader_pod = pod
        break;
  if leader_pod != "":
    logger.info("Leader pod identified: {}".format(leader_pod))
  else:
    logger.error("No leader pod identified")
    sys.exit(1)

  # Compact the etcd keyspace on the leader
  compact_cmd = "env -u ETCDCTL_ENDPOINTS etcdctl --command-timeout 30s --endpoints=https://localhost:2379 compact".split(" ")
  if cliargs.compact:
    logger.info("Compacting etcd keyspace")
    # for pod in pods:
    logger.info("Compacting keyspace on pod: {}".format(leader_pod))
    oc_cmd = ["oc", "--kubeconfig", cliargs.kubeconfig, "rsh", "-n", "openshift-etcd", leader_pod] + compact_cmd + [pods[pod]["revision"]]
    rc, output = command(oc_cmd, False, no_log=True)
    if rc != 0:
      logger.error("etcd-defrag, oc rsh -n openshift-etcd {} etcdctl ... compact rc: {}".format(pod, rc))
      sys.exit(1)
    logger.info(output.rstrip())

  # Defrag etcd databases (Not leader)
  defrag_cmd = "env -u ETCDCTL_ENDPOINTS etcdctl --command-timeout 30s --endpoints=https://localhost:2379 defrag".split(" ")
  for pod in pods:
    if pod == leader_pod:
      logger.info("Skipping leader pod: {} to defrag last".format(pod))
      continue
    logger.info("Defrag pod: {}".format(pod))
    oc_cmd = ["oc", "--kubeconfig", cliargs.kubeconfig, "rsh", "-n", "openshift-etcd", pod] + defrag_cmd
    rc, output = command(oc_cmd, False, no_log=True)
    if rc != 0:
      logger.error("etcd-defrag, oc rsh -n openshift-etcd {} etcdctl ... defrag rc: {}".format(pod, rc))
      sys.exit(1)
    logger.info(output.rstrip())

  # Defrag the leader
  oc_cmd = ["oc", "--kubeconfig", cliargs.kubeconfig, "rsh", "-n", "openshift-etcd", leader_pod] + defrag_cmd
  logger.info("Defrag the leader pod: {}".format(leader_pod))
  rc, output = command(oc_cmd, False, no_log=True)
  if rc != 0:
    logger.error("etcd-defrag, oc rsh -n openshift-etcd {} etcdctl ... defrag rc: {}".format(leader_pod, rc))
    sys.exit(1)
  logger.info(output.rstrip())

  # Disarm alarms
  if cliargs.disarm_alarms:
    logger.info("Disarming alarms")
    oc_cmd = ["oc", "--kubeconfig", cliargs.kubeconfig, "rsh", "-n", "openshift-etcd", leader_pod, "etcdctl", "alarm", "disarm"]
    rc, output = command(oc_cmd, False, no_log=True)
    if rc != 0:
      logger.error("etcd-defrag, oc rsh -n openshift-etcd {} etcdctl ... alarm disarm rc: {}".format(leader_pod, rc))
      sys.exit(1)
    logger.info(output.rstrip())

  logger.info("Etcd defragged")


if __name__ == "__main__":
  sys.exit(main())
