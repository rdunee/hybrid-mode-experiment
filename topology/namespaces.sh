#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
./cleanup.sh
trap './cleanup.sh' ERR
for ns in hme-edge hme-gateway; do
  ip netns add "$ns"
  ip -n "$ns" link set lo up
done
for p in 1 2; do
  ip link add "hme-e$p" type veth peer name "hme-g$p"
  ip link set "hme-e$p" netns hme-edge
  ip link set "hme-g$p" netns hme-gateway
  ip -n hme-edge addr add "10.201.$p.1/30" dev "hme-e$p"
  ip -n hme-gateway addr add "10.201.$p.2/30" dev "hme-g$p"
  ip -n hme-edge link set "hme-e$p" up
  ip -n hme-gateway link set "hme-g$p" up
  for pair in "hme-edge hme-e$p" "hme-gateway hme-g$p"; do
    read -r ns dev <<< "$pair"
    ip netns exec "$ns" ethtool -K "$dev" gro off gso off tso off
  done
done
