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

# Remove experimental veth pairs left in the host namespace.
for dev in hme-e1 hme-g1 hme-e2 hme-g2; do
  if ip link show dev "$dev" >/dev/null 2>&1; then
    ip link delete dev "$dev"
  fi
done