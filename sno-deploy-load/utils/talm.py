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

import json
import logging
from utils.command import command


logger = logging.getLogger("acm-deploy-load")


def detect_talm_minor(default_talm_version, dry_run):
  talm_version = default_talm_version
  logger.info("Detecting TALM version by image tag")
  oc_cmd = ["oc", "get", "deploy", "-n", "openshift-cluster-group-upgrades", "cluster-group-upgrades-controller-manager", "-o", "json"]
  rc, output = command(oc_cmd, dry_run, retries=3, no_log=True)
  if rc != 0:
    logger.warn("talm, oc get deploy -n openshift-cluster-group-upgrades rc: {}".format(rc))
  else:
    if not dry_run:
      td_data = json.loads(output)
      talm_image_ver = ""
      if "spec" in td_data and "template" in td_data["spec"] and "spec" in td_data["spec"]["template"]:
        for container in td_data["spec"]["template"]["spec"]["containers"]:
          if container["name"] == "manager":
            talm_image_ver = container["image"].split(":")[-1]
            break
      if talm_image_ver != "":
        logger.info("Detected TALM Version: {}".format(talm_image_ver))
        talm_version = talm_image_ver
      else:
        logger.warn("Unable to detect TALM version, defaulting to: {}".format(talm_version))
  return talm_version.split(".")[1]
