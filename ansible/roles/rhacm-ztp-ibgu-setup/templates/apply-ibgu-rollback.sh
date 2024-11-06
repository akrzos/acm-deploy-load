#!/usr/bin/env bash
{% for ibgu in range(((ztp_done_clusters.stdout_lines | length) / clusters_per_prep_ibgu) | round(0, 'ceil') | int) %}
date -u
oc patch ibgu ibgu-{{ seed_image_version | replace('.', '-') }}-{{ '%04d' | format(ibgu) }} -n ztp-platform-upgrade --type=json -p '[{"op": "add", "path": "/spec/plan/-", "value": {"actions": ["Rollback"], "rolloutStrategy": {"maxConcurrency": {{ ibgu_rollback_concurrency }}, "timeout": {{ ibgu_rollback_timeout }} }}}]'
{% if not loop.last %}
sleep {{ ibgu_rollback_sleep * 60 }}
{% endif %}
{% endfor %}
