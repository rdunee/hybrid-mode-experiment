# Hybrid transmission-mode experiment — Stage-1 reference

Executable vendor-independent **low-rate UDP pilot**: single, weighted flow steering, weighted striping, replication and XOR FEC. Requested pilot:6 losses×4 modes×10 reps=240 runs. Includes C0–C10 screening, boundary configurations, raw telemetry, run-level statistics, Pareto and optional observed-state oracle analysis.

Read [methodology](docs/methodology.md): all18 requested sections, scientific safeguards and implementation boundaries. Native HTTP/TCP through the mode engine, arbitrary/multi-erasure FEC, multi-host timing, high-rate processing and adaptive control are **not implemented**. This is an experimental foundation, not a complete publication-ready system. No research measurements are fabricated.

## Install

Dedicated Ubuntu/Debian host; Python3.11+, namespace privileges and recent netem seed support. Restricted-container root is insufficient. Names `hme-edge`/`hme-gateway` are reserved and deleted by setup/cleanup.

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv iproute2 ethtool iperf3
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m orchestrator.run_experiment --matrix-only --output configs/stage1
```

No Internet/default route/host-interface qdisc is needed during experiments. Install dependencies first.

## Smoke and calibration

```bash
.venv/bin/python - <<'PY'
import yaml
from pathlib import Path
cfg=yaml.safe_load(Path('configs/stage1/pilot.yaml').read_text())
cfg.update(warmup_s=2,measurement_s=10,stabilization_s=2,cooldown_s=1)
Path('configs/stage1/smoke.yaml').write_text(yaml.safe_dump(cfg))
PY
sudo "$(pwd)/.venv/bin/python" -m orchestrator.run_experiment --config configs/stage1/smoke.yaml --limit 1 --output data/smoke
```

Complete methodology Part14 before research collection; automated gates do not replace calibration. Smoke every mode, including failure cleanup.

## Pilot

```bash
sudo "$(pwd)/.venv/bin/python" -m orchestrator.run_experiment --config configs/stage1/pilot.yaml --output data/raw/pilot-01
```

Roughly11 hours plus setup. Use a fresh output for reruns; protected existing run directories. Invalid runs retain logs/reasons. No concurrent campaigns on one host; never impair customer production links.

## Analysis

```bash
.venv/bin/python -m analysis.pipeline --raw data/raw/pilot-01 --output data/results/pilot-01
# Illustrative objective only; preregister your actual weights:
.venv/bin/python -m analysis.pipeline --raw data/raw/pilot-01 --output data/results/pilot-objective --weights configs/stage1/objective-example.json
```

Produces runs/summary/paired-comparison/Pareto CSVs, invalid ledger, joined packet metrics and vector PDF plots. Optional weights produce state winners, cross-validated comparisons to static selection and a heatmap. No valid runs means no invented output. Offered originals are the loss denominator. Deadline-useful bytes exclude late arrivals. Wire overhead includes IPv4/UDP/experiment headers, excludes Ethernet/probes/cross traffic; use interface counters for aggregate traffic.

## Follow-up

```bash
sudo "$(pwd)/.venv/bin/python" -m orchestrator.run_experiment --config configs/stage1/screening.yaml --output data/raw/screening-01
# Targeted/coarse subsets first; full boundary configuration has1800 runs:
sudo "$(pwd)/.venv/bin/python" -m orchestrator.run_experiment --config configs/stage2/loss-delay.yaml --output data/raw/boundary-01
```

Default loss plots are for the one-dimensional pilot; mixed-state figures require facets. Add cleanB/best-measured-path baselines and multiple applications before claiming adaptation.

## Emergency cleanup

```bash
sudo ./topology/cleanup.sh
```

Actual development checks and remaining privileged-host acceptance gates are in [validation-report](docs/validation-report.md).
