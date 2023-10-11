#!/usr/bin/env python3
#
# Tool to load a managed cluster with a number of namespaces, deployments, configmaps, secrets, and pods.
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

import argparse
from datetime import datetime
from jinja2 import Template
import logging
import os
import sys
import time

# TODO:
# * Option to preload image via daemonset
# * Apply manifests
# * Option to clean up manifests
# * Separate option to remove workload (cleanup)

namespace_template = """---
apiVersion: v1
kind: Namespace
metadata:
  name: {{ name }}
"""

deployment_template = """---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ name }}
  namespace: {{ namespace }}
spec:
  replicas: {{ replicas }}
  selector:
    matchLabels:
      app: mc-workload-{{ name }}
  strategy:
    resources: {}
  template:
    metadata:
      labels:
        app: mc-workload-{{ name }}
    spec:
      containers:
      - name: mc-workload
        image: {{ image }}
      {%- if (configmaps|length > 0) or (secrets|length > 0) %}
        volumeMounts:
        {%- for cm in configmaps %}
        - name: {{ cm['v_name'] }}
          mountPath: /etc/{{ cm['v_name'] }}
        {%- endfor %}
        {%- for secret in secrets %}
        - name: {{ secret['v_name'] }}
          mountPath: /etc/{{ secret['v_name'] }}
        {%- endfor %}
      volumes:
      {%- for cm in configmaps %}
      - name: {{ cm['v_name'] }}
        configMap:
          name: {{ cm['name'] }}
      {%- endfor %}
      {%- for secret in secrets %}
      - name: {{ secret['v_name'] }}
        secret:
          secretName: {{ secret['name'] }}
      {%- endfor %}
      {%- endif %}
"""

configmap_template = """---
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ name }}
  namespace: {{ namespace }}
data:
  mc_load: "{{ name }} - Random data"
"""

secret_template = """---
apiVersion: v1
kind: Secret
metadata:
  name: {{ name }}
  namespace: {{ namespace }}
data:
  mc_load: UmFuZG9tIGRhdGEK
"""


logging.basicConfig(level=logging.INFO, format="%(asctime)s : %(levelname)s : %(threadName)s : %(message)s")
logger = logging.getLogger("acm-deploy-load")
logging.Formatter.converter = time.gmtime


def main():
  start_time = time.time()

  parser = argparse.ArgumentParser(
      description="Tool to load a managedcluster with namespaces, deployments, pods, and configmaps",
      prog="mc-workload.py", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  parser.add_argument("-n", "--namespaces", type=int, default=1, help="Number of namespaces to create")
  parser.add_argument("-d", "--deployments", type=int, default=1, help="Number of deployments per namespace to create")
  parser.add_argument("-p", "--pods", type=int, default=1, help="Number of pod replicas per deployment to create")

  # Per Pod config
  parser.add_argument("-c", "--configmaps", type=int, default=1, help="Number of configmaps per deployment")
  parser.add_argument("-s", "--secrets", type=int, default=1, help="Number of secrets per deployment")

  parser.add_argument("-i", "--container-image", type=str,
                      # default="quay.io/redhat-performance/test-gohttp-probe:v0.0.2", help="The container image to use")
                      default="e38-h01-000-r650.rdu2.scalelab.redhat.com:5000/redhat-performance/test-gohttp-probe:v0.0.2", help="The container image to use")

  parser.add_argument("-m", "--manifests-directory", type=str, help="The location to place mc-workload manifests")

  cliargs = parser.parse_args()

  # logger.info("Args: {}".format(cliargs))

  manifests_dir = ""
  if cliargs.manifests_directory:
    # Check if directory exists
    if os.path.exists(cliargs.manifests_directory):
      logger.info("Using directory: {}".format(cliargs.manifests_directory))
      manifests_dir = cliargs.manifests_directory
    else:
      logger.error("Manifests directory specified does not exist: {}".format(cliargs.manifests_directory))
      sys.exit(1)
  else:
    base_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
    base_dir_down = os.path.dirname(base_dir)
    base_dir_manifests = os.path.join(base_dir_down, "manifests")
    manifests_dir_name = "mc-workload-{}".format(datetime.utcfromtimestamp(start_time).strftime("%Y%m%d-%H%M%S"))
    manifests_dir = os.path.join(base_dir_manifests, manifests_dir_name)
    os.mkdir(manifests_dir)
    logger.info("Using generated manifests directory: {}".format(manifests_dir))

  logger.info("Creating {} namespaces with {} deployments with {} pod replicas".format(cliargs.namespaces, cliargs.deployments, cliargs.pods))

  # Generate Manifests
  for ns in range(0, cliargs.namespaces):
    ns_name = "mc-workload-{:04d}".format(ns)
    ns_fname = "01-ns-{}.yml".format(ns_name)
    logger.info("Templating Namespace: {}".format(ns_name))
    t = Template(namespace_template)
    ns_template_rendered = t.render(name=ns_name)
    with open("{}/{}".format(manifests_dir, ns_fname), "w") as file1:
      file1.writelines(ns_template_rendered)
    for deploy in range(0, cliargs.deployments):
      configmaps = []
      secrets = []
      deploy_name = "deploy-{:04d}".format(deploy)
      deploy_fname = "04-{}-deploy-{}.yml".format(ns_name, deploy_name)

      # Template the Configmaps
      for cm in range(0, cliargs.configmaps):
        cm_name = "cm-{:04d}-{:04d}-{:04d}".format(ns, deploy, cm)
        cm_fname = "02-{}-{}.yml".format(ns_name, cm_name)
        configmaps.append({"name": cm_name, "v_name": "cm-{}".format(cm)})
        logger.info("Templating Configmap: {}".format(cm_name))
        t = Template(configmap_template)
        cm_template_rendered = t.render(namespace=ns_name, name=cm_name)
        with open("{}/{}".format(manifests_dir, cm_fname), "w") as file1:
          file1.writelines(cm_template_rendered)

      # Template the Secrets
      for secret in range(0, cliargs.secrets):
        secret_name = "s-{:04d}-{:04d}-{:04d}".format(ns, deploy, secret)
        secret_fname = "03-{}-{}.yml".format(ns_name, secret_name)
        secrets.append({"name": secret_name, "v_name": "s-{}".format(secret)})
        logger.info("Templating Secret: {}".format(secret_name))
        t = Template(secret_template)
        secret_template_rendered = t.render(namespace=ns_name, name=secret_name)
        with open("{}/{}".format(manifests_dir, secret_fname), "w") as file1:
          file1.writelines(secret_template_rendered)

      logger.info("Templating Deployment: {}".format(deploy_name))
      t = Template(deployment_template)
      deploy_template_rendered = t.render(
          namespace=ns_name,
          name=deploy_name,
          replicas=cliargs.pods,
          image=cliargs.container_image,
          configmaps=configmaps,
          secrets=secrets)
      with open("{}/{}".format(manifests_dir, deploy_fname), "w") as file1:
        file1.writelines(deploy_template_rendered)

  # Apply manifests?

  end_time = time.time()
  logger.info("Took {}s".format(round(end_time - start_time, 1)))

if __name__ == "__main__":
  sys.exit(main())
