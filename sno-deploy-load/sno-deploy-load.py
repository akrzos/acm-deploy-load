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
from collections import OrderedDict
# from datetime import datetime
import glob
from jinja2 import Template
import logging
import math
import os
import pathlib
import shutil
# import subprocess
import sys
import time


kustomization_template = """---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
generators:
{%- for sno in snos %}
- ./{{ sno }}-siteconfig.yml
{%- endfor %}

resources:
{%- for sno in snos %}
- ./{{ sno }}-resources.yml
{%- endfor %}

"""


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(message)s")
logger = logging.getLogger("sno-deploy-load")
logging.Formatter.converter = time.gmtime


def deploy_ztp_snos(snos, ztp_deploy_apps, start_index, end_index, snos_per_app, sno_siteconfigs, argocd_dir):
  git_files = []
  siteconfig_dir = "{}/siteconfigs".format(sno_siteconfigs)
  last_ztp_app_index = math.floor((start_index) / snos_per_app)
  for idx, sno in enumerate(snos[start_index:end_index]):
    ztp_app_index = math.floor((start_index + idx) / snos_per_app)

    # If number of snos batched rolls into the next application, render the kustomization file
    if last_ztp_app_index < ztp_app_index:
      logger.info("Rendering {}/kustomization.yml".format(ztp_deploy_apps[last_ztp_app_index]["location"]))
      t = Template(kustomization_template)
      kustomization_rendered = t.render(
          snos=ztp_deploy_apps[last_ztp_app_index]["snos"])
      with open("{}/kustomization.yaml".format(ztp_deploy_apps[last_ztp_app_index]["location"]), "w") as file1:
        file1.writelines(kustomization_rendered)
      git_files.append("{}/kustomization.yaml".format(ztp_deploy_apps[last_ztp_app_index]["location"]))
      last_ztp_app_index = ztp_app_index

    siteconfig_name = os.path.basename(sno)
    sno_name = siteconfig_name.replace("-siteconfig.yml", "")
    ztp_deploy_apps[ztp_app_index]["snos"].append(sno_name)
    logger.debug("SNOs: {}".format(ztp_deploy_apps[ztp_app_index]["snos"]))

    logger.debug("Copying {}-siteconfig.yml and {}-resources.yml from {} to {}".format(
        sno_name, sno_name, siteconfig_dir, ztp_deploy_apps[last_ztp_app_index]["location"]))
    shutil.copy2(
        "{}/{}-siteconfig.yml".format(siteconfig_dir, sno_name),
        "{}/{}-siteconfig.yml".format(ztp_deploy_apps[last_ztp_app_index]["location"], sno_name))
    shutil.copy2(
        "{}/{}-resources.yml".format(siteconfig_dir, sno_name),
        "{}/{}-resources.yml".format(ztp_deploy_apps[last_ztp_app_index]["location"], sno_name))
    git_files.append("{}/{}-siteconfig.yml".format(ztp_deploy_apps[last_ztp_app_index]["location"], sno_name))
    git_files.append("{}/{}-resources.yml".format(ztp_deploy_apps[last_ztp_app_index]["location"], sno_name))

  # Always render a kustomization.yaml file at conclusion of the enumeration
  logger.info("Rendering {}/kustomization.yaml".format(ztp_deploy_apps[ztp_app_index]["location"]))
  t = Template(kustomization_template)
  kustomization_rendered = t.render(
      snos=ztp_deploy_apps[ztp_app_index]["snos"])
  with open("{}/kustomization.yaml".format(ztp_deploy_apps[ztp_app_index]["location"]), "w") as file1:
    file1.writelines(kustomization_rendered)
  git_files.append("{}/kustomization.yaml".format(ztp_deploy_apps[ztp_app_index]["location"]))

  # Git Process:
  for file in git_files:
    logger.debug("git add {}".format(file))
  logger.info("Added {} files in git".format(len(git_files)))
  logger.info("git commit -m 'Deploying SNOs {} to {}'".format(start_index, end_index))
  logger.info("git push")

def phase_break():
  logger.info("###############################################################################")


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Run sno-deploy-load",
      prog="sno-deploy-load.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  # "Global" args
  parser.add_argument("-m", "--sno-manifests-siteconfigs", type=str, default="/home/akrzos/akrh/project-things/20220117-cloud13-acm-2.5/hv-sno",
                      help="The location of the SNO manifests, siteconfigs and resource files")
  parser.add_argument("-a", "--argocd-base-directory", type=str,
                      default="/home/akrzos/akrh/project-things/20220117-cloud13-acm-2.5/argocd",
                      help="The location of the ArgoCD SNO cluster and cluster applications directories")
  # parser.add_argument("-m", "--sno-manifests-siteconfigs", type=str, default="/root/hv-sno",
  #                     help="The location of the SNO manifests, siteconfigs and resource files")
  # parser.add_argument("-a", "--argocd-base-directory", type=str,
  #                     default="/root/rhacm-ztp/cnf-features-deploy/ztp/gitops-subscriptions/argocd/",
  #                     help="The location of the ArgoCD SNO cluster and cluster applications directories")-
  parser.add_argument("--snos-per-app", type=int, default=100,
                      help="Maximum number of SNO siteconfigs per cluster application")
  parser.add_argument("-w", "--wait-du-profile", action="store_true", default=False,
                      help="Waits for du profile to complete after all expected SNOs deployed")
  parser.add_argument("-d", "--debug", action="store_true", default=False, help="Set log level debug")
  parser.add_argument("--dry-run", action="store_true", default=False, help="Echos commands instead of executing them")

  subparsers = parser.add_subparsers(dest="rate")

  parser_interval = subparsers.add_parser("interval")
  parser_interval.add_argument("-b", "--batch", type=int, default=100, help="Number of SNOs to apply per interval")
  parser_interval.add_argument("-i", "--interval", type=int, default=7200,
                               help="Time in seconds between deploying SNOs")
  parser_interval.add_argument("-s", "--start", type=int, default=0,
                               help="SNO start index, follows array logic starting at 0 for 'sno00001'")
  parser_interval.add_argument("-e", "--end", type=int, default=0,
                               help="SNO end index (0 = total manifest count)")
  subparsers_interval = parser_interval.add_subparsers(dest="method")
  subparsers_interval.add_parser("manifests")
  subparsers_interval.add_parser("ztp")

  parser_status = subparsers.add_parser("status")
  parser_status.add_argument("-b", "--batch", type=int, default=100,
                             help="Number of SNOs to apply until all either complete/fail")
  parser_status.add_argument("-s", "--start", type=int, default=0,
                             help="SNO start index, follows array logic starting at 0 for 'sno00001'")
  parser_status.add_argument("-e", "--end", type=int, default=0,
                             help="SNO end index (0 = total manifest count)")
  subparsers_status = parser_status.add_subparsers(dest="method")
  subparsers_status.add_parser("manifests")
  subparsers_status.add_parser("ztp")

  parser_concurrent = subparsers.add_parser("concurrent")
  parser_concurrent.add_argument("-c", "--concurrency", type=int, default=100,
                                 help="Number of SNOs to maintain deploying/installing")
  parser_concurrent.add_argument("-s", "--start", type=int, default=0,
                                 help="SNO start index, follows array logic starting at 0 for 'sno00001'")
  parser_concurrent.add_argument("-e", "--end", type=int, default=0,
                                 help="SNO end index (0 = total manifest count)")
  subparsers_concurrent = parser_concurrent.add_subparsers(dest="method")
  subparsers_concurrent.add_parser("manifests")
  subparsers_concurrent.add_parser("ztp")

  parser_interval.set_defaults(method="ztp")
  parser_status.set_defaults(method="ztp")
  parser_concurrent.set_defaults(method="ztp")
  parser.set_defaults(rate="interval", method="ztp", batch=100, interval=7200, start=0, end=0)
  cliargs = parser.parse_args()

  if cliargs.debug:
    logger.setLevel(logging.DEBUG)

  phase_break()
  if cliargs.dry_run:
    logger.info("SNO Deploy Load - Dry Run")
  else:
    logger.info("SNO Deploy Load")
  phase_break()
  logger.debug("CLI Args: {}".format(cliargs))

  # Validate parameters and display rate and method plan
  logger.info("Deploying SNOs rate: {}".format(cliargs.rate))
  logger.info("Deploying SNOs method: {}".format(cliargs.method))
  if (cliargs.start < 0):
    logger.error("SNO start index must be equal to or greater than 0")
    sys.exit(1)
  if (cliargs.end < 0):
    logger.error("SNO end index must be equal to or greater than 0")
    sys.exit(1)
  if (cliargs.end > 0 and (cliargs.start >= cliargs.end)):
    logger.error("SNO start index must be greater than the end index, when end index is not 0")
    sys.exit(1)
  if cliargs.rate == "interval":
    if not (cliargs.batch >= 1):
      logger.error("Batch size must be equal to or greater than 1")
      sys.exit(1)
    if not (cliargs.interval >= 0):
      logger.error("Interval must be equal to or greater than 0")
      sys.exit(1)
    logger.info(" * {} SNO(s) per {}s interval".format(cliargs.batch, cliargs.interval))
  elif cliargs.rate == "status":
    if not (cliargs.batch >= 1):
      logger.error("Batch size must be equal to or greater than 1")
      sys.exit(1)
    logger.info(" * {} SNO(s) at a time until complete/fail status".format(cliargs.batch))
  elif cliargs.rate == "concurrent":
    if not (cliargs.concurrency >= 1):
      logger.error("Concurrency must be equal to or greater than 1")
      sys.exit(1)
    logger.info(" * {}  SNO(s) deploying concurrently".format(cliargs.batch))
  logger.info(" * Start Index: {}, End Index: {}".format(cliargs.start, cliargs.end))
  phase_break()

  # Get list of available manifests or siteconfigs and cluster applications
  available_snos = 0
  sno_list = []
  available_ztp_apps = 0
  ztp_deploy_apps = OrderedDict()
  if cliargs.method == "manifests":
    sno_list = glob.glob("{}/manifests/sno*".format(cliargs.sno_manifests_siteconfigs))
    sno_list.sort()
    for manifest_dir in sno_list:
      if pathlib.Path("{}/manifest.yml".format(manifest_dir)).is_file():
        logger.debug("Found {}".format("{}/manifest.yml".format(manifest_dir)))
      else:
        logger.error("Directory appears to be missing manifest.yml file: {}".format(manifest_dir))
        sys.exit(1)
  elif cliargs.method == "ztp":
    sno_list = glob.glob("{}/siteconfigs/sno*-siteconfig.yml".format(cliargs.sno_manifests_siteconfigs))
    sno_list.sort()
    siteconfig_dir = "{}/siteconfigs".format(cliargs.sno_manifests_siteconfigs)
    for siteconfig_file in sno_list:
      siteconfig_name = os.path.basename(siteconfig_file)
      resources_name = siteconfig_name.replace("-siteconfig", "-resources")
      if pathlib.Path("{}/{}".format(siteconfig_dir, resources_name)).is_file():
        logger.debug("Found {}".format("{}/{}".format(siteconfig_dir, resources_name)))
      else:
        logger.error("Directory appears to be missing {} file: {}".format(resources_name, siteconfig_dir))
        sys.exit(1)
    ztp_apps = glob.glob("{}/cluster/ztp-*".format(cliargs.argocd_base_directory))
    ztp_apps.sort()
    for idx, ztp_app in enumerate(ztp_apps):
      ztp_deploy_apps[idx] = {"location": ztp_app, "snos": []}

  available_snos = len(sno_list)
  available_ztp_apps = len(ztp_deploy_apps)
  logger.info("Discovered {} available SNOs for deployment".format(available_snos))

  if cliargs.method == "ztp":
    max_ztp_snos = available_ztp_apps * cliargs.snos_per_app
    logger.info("Discovered {} ztp cluster apps with capacity for {} * {} = {} SNOs".format(
        available_ztp_apps, available_ztp_apps, cliargs.snos_per_app, max_ztp_snos))
    if max_ztp_snos < available_snos:
      logger.error("There are more SNOs than expected capacity of SNOs per ZTP cluster application")
      sys.exit(1)

  total_deployed_snos = 0
  total_intervals = 0
  rate_start_time = time.time()
  if cliargs.rate == "interval":
    phase_break()
    logger.info("Starting interval based SNO deployment rate")
    phase_break()

    start_sno_index = cliargs.start
    while True:
      total_intervals += 1
      start_interval_time = time.time()
      end_sno_index = start_sno_index + cliargs.batch
      if cliargs.end > 0:
        if end_sno_index > cliargs.end:
          end_sno_index = cliargs.end
      logger.info("Deploying interval {} with {} SNO(s) - {}".format(
          total_intervals, end_sno_index - start_sno_index, int(start_interval_time * 1000)))

      # Apply the snos
      if cliargs.method == "manifests":
        for sno in sno_list[start_sno_index:end_sno_index]:
          total_deployed_snos += 1
          logger.info("oc apply -f {}".format(sno))
      elif cliargs.method == "ztp":
        total_deployed_snos += len(sno_list[start_sno_index:end_sno_index])
        deploy_ztp_snos(
            sno_list, ztp_deploy_apps, start_sno_index, end_sno_index, cliargs.snos_per_app,
            cliargs.sno_manifests_siteconfigs, cliargs.argocd_base_directory)

      start_sno_index += cliargs.batch
      if start_sno_index >= available_snos or end_sno_index == cliargs.end:
        logger.info("Finished deploying SNOs - {}".format(int(time.time() * 1000)))
        break

      # Interval wait logic
      expected_interval_end_time = start_interval_time + cliargs.interval
      current_time = time.time()
      wait_logger = 0
      logger.info("Sleep for {}s with {}s remaining".format(cliargs.interval, round(expected_interval_end_time - current_time, 1)))
      while current_time < expected_interval_end_time:
        time.sleep(.1)
        wait_logger += 1
        if wait_logger >= 1000:
          logger.info("Remaining interval time: {}".format(round(expected_interval_end_time - current_time, 1)))
          wait_logger = 0
        current_time = time.time()

  elif cliargs.rate == "status":
    logger.error("Status rate Not implemented yet")
    sys.exit(1)
  elif cliargs.rate == "concurrent":
    logger.error("Concurrent rate Not implemented yet")
    sys.exit(1)
  rate_end_time = time.time()

  # Potentially wait for all clusters to finish deploying (interval)
  # Potentially wait for du profile to apply to all clusters (All rates)

  end_time = time.time()
  total_rate_time = round(rate_end_time - rate_start_time, 1)
  total_time = round(end_time - start_time, 1)
  phase_break()
  logger.info("sno-deploy-load Stats")
  logger.info("Total available SNOs: {}".format(available_snos))
  logger.info("Total deployed SNOs: {}".format(total_deployed_snos))
  if cliargs.rate == "interval":
    logger.info("Total intervals: {}".format(total_intervals))
  logger.info("Time spent during rate deploying SNOs: {}".format(total_rate_time))
  # logger.info("Time spent waiting for du profile:")
  logger.info("Total time: {}".format(total_time))

if __name__ == "__main__":
  sys.exit(main())
