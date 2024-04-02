#!/usr/bin/env bash
{% for cgu in range(((ztp_done_clusters.stdout_lines | length) / platform_ibu_upgrade_clusters_per_cgu) | round(0, 'ceil') | int) %}
date -u
oc apply -f {{ install_directory }}/rhacm-ztp/ibu/scripts/cgu-platform-ibu-upgrade-{{ ibu_seed_image_version | replace('.', '-') }}-{{ '%04d' | format(cgu) }}.yml
{% if not loop.last %}
sleep {{ (platform_ibu_upgrade_sleep + platform_ibu_upgrade_offset) * 60 }}
{% endif %}
{% endfor %}
