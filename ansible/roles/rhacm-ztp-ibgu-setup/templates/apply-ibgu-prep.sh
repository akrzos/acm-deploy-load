#!/usr/bin/env bash
{% for ibgu in range(((ztp_done_clusters.stdout_lines | length) / clusters_per_prep_ibgu) | round(0, 'ceil') | int) %}
date -u
oc apply -f {{ install_directory }}/rhacm-ztp/ibgu/scripts-{{ seed_image_version | replace('.', '-') }}/ibgu-{{ seed_image_version | replace('.', '-') }}-{{ '%04d' | format(ibgu) }}.yml
{% if not loop.last %}
sleep {{ ibgu_prep_sleep * 60 }}
{% endif %}
{% endfor %}
