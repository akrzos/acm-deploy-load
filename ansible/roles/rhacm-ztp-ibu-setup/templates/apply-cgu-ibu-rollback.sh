#!/usr/bin/env bash
{% for cgu in range(((ztp_done_clusters.stdout_lines | length) / ibu_rollback_clusters_per_cgu) | round(0, 'ceil') | int) %}
date -u
oc apply -f {{ install_directory }}/rhacm-ztp/ibu/scripts/cgu-ibu-rollback-{{ ibu_seed_image_version | replace('.', '-') }}-{{ '%04d' | format(cgu) }}.yml
{% if not loop.last %}
sleep {{ (ibu_rollback_sleep + ibu_rollback_offset) * 60 }}
{% endif %}
{% endfor %}
