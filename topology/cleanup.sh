#!/usr/bin/env bash
set -euo pipefail
# Reserved experiment namespaces only. Never touches a host management NIC.
for ns in hme-edge hme-gateway; do
  if ip netns list | awk '{print $1}' | grep -qx "$ns"; then
    mapfile -t pids < <(ip netns pids "$ns")
    for pid in "${pids[@]}"; do kill -TERM "$pid" 2>/dev/null || true; done
    ip netns del "$ns"
  fi
done
