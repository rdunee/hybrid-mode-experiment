# Development validation — 2026-10-02

**7 tests passed. No privileged network-emulation experiment was run.**

- XOR reconstruction for every single-erasure position; original timestamp preserved.
- Receiver integration: erased packet reconstructed, duplicate suppressed, reordering detected.
- Flow affinity, Pareto ties/dominated points, bootstrap and sign-flip sanity checks.
- Deterministic240-run matrix: unique IDs and four randomized modes per block.
- Eight loopback workload runs: two repetitions each of single/striping/replication/FEC;20 originals per run and expected wire counts20/20/40/24. Temporary correctness fixtures, not research measurements.
- Full fixture analysis generated summaries,42 paired comparisons, Pareto, objective oracle, held-out comparisons and PDF heatmap.
- Python compilation and bash syntax checks passed.
- Screening440-run and loss×RTT1800-run matrices generated.

`ip netns add hme-capability-check` failed: `Cannot open netlink socket: Operation not permitted`. No namespace was created. Netem rate/delay/burst calibration, event orchestration, collector rejection gates and privileged-host cleanup still require the README acceptance protocol. Correctness tests do not prove scientific conclusions. Native workload baselines were not run against remote servers.

Tests used preinstalled runtime versions below. A fresh pinned installation requires target-host validation. psutil was unavailable in the development runtime; it is explicitly included in requirements.txt and must be installed for host telemetry. The privileged telemetry collector was not exercised here.

Python: 3.12.14

- PyYAML: 6.0.3
- numpy: 2.3.5
- pandas: 2.2.3
- scipy: 1.17.0
- matplotlib: 3.10.8
