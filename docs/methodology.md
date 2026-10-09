# Experimental methodology and implementation boundaries

This is an executable **low-rate UDP Stage-1 reference**, plus the design for subsequent experiments. It is not a complete production SD-WAN system or evidence that the hypothesis is true. Namespace impairment experiments could not run in the development environment because netlink privileges were denied. Loopback tests do not validate network emulation.

## Part 1 — Rationale

Ask whether network state interacts with mode in practically meaningful ways. A changing Pareto set motivates investigating adaptation; a deployable controller also needs learnable measured-state features, held-out benefit over strong static baselines, and switching costs. H1 tests for counterexamples to universal dominance within the tested domain. H2 tests mode×state interactions. H3 measures resource costs. H4 requires multiple application classes and is **not tested by this RTC-only pilot**. H5 requires prediction from measured rather than configured state on held-out data.

A Pareto-dominates B if all cost dimensions are no greater and at least one is strictly smaller. RTC dimensions: delivered-packet p95, deadline-miss fraction, and overhead. Delay must accompany loss/miss because undelivered packets are absent from latency quantiles. Missing/infinite dimensions are not silently assigned a winning rank. Point-estimate frontiers are exploratory. The code also flags conservatively separated marginal CIs, which are not simultaneous confidence regions; use joint/multiplicity-adjusted dominance and equivalence inference for confirmation.

Optional J=sum(weight_i×metric_i/scale_i). Physical scales and application preferences must be explicit and frozen before final data. The example JSON is illustrative, not a research finding. Sweep plausible weights; keep Pareto results primary. Monetary cost is not inferred from bytes.

## Part 2 — Architecture

Sender/application runs in `hme-edge`; gateway/receiver runs in `hme-gateway`. Two independent veth pairs carry UDP. RTC application and transport roles are fused for this pilot. No default route, host forwarding change or host management qdisc is required. Addresses10.201.1.0/30 and10.201.2.0/30 exist only in the reserved namespaces.

Full system extension: separate client/server namespaces; add a transport abstraction/TUN tunnel with MTU, per-flow sequencing, bounded reorder buffers and congestion control. Native HTTP/TCP through the mode engine is **not implemented**. Additional paths require sockets, address configuration and generalized schedulers; this version supports exactly two. The path manager must separate health/flow affinity/weights from mechanism selection. No adaptive controller is included.

## Part 3 — Linux topology

`topology/namespaces.sh` is the exact executable configuration. It recreates two namespaces, enables loopback, creates two veth pairs, assigns .1 to edge and .2 to gateway, brings interfaces up and disables GRO/GSO/TSO. Representative commands:

```bash
ip netns add hme-edge
ip netns add hme-gateway
ip link add hme-e1 type veth peer name hme-g1
ip link set hme-e1 netns hme-edge
ip link set hme-g1 netns hme-gateway
ip -n hme-edge addr add 10.201.1.1/30 dev hme-e1
ip -n hme-gateway addr add 10.201.1.2/30 dev hme-g1
ip -n hme-edge link set hme-e1 up
ip -n hme-gateway link set hme-g1 up
```

Use the script for complete two-path/offload setup. Reserved names must not contain unrelated work. Cleanup kills processes only inside those namespaces and removes them, including qdiscs. It is idempotent. Do not run concurrent campaigns on the same host. SIGKILL requires manual emergency cleanup.

## Part 4 — Impairments

`netem.py` logs argv, verifies netem kind and saves actual qdisc state. RTT is split as half-delay in each direction. Forward loss applies only to edge egress, so configured loss is a forward packet percentage rather than a round-trip loss rate. Example:

```bash
ip netns exec hme-edge tc qdisc replace dev hme-e1 root handle 10: netem limit 1000 delay 15ms loss random 1% 0% rate 100mbit seed 20271002
ip netns exec hme-gateway tc qdisc replace dev hme-g1 root handle 10: netem limit 1000 delay 15ms rate 100mbit seed 20271102
```

Independent loss uses correlation0. Optional correlation is a phenomenological netem parameter, not a Gilbert–Elliott transition probability. Burst model: all-drop bad state, mean bad length b gives r=1/b; stationary loss ell gives p=ell*r/(1-ell). Parameters are `gemodel 100p% 100r% 100% 0%`. For2% mean7, entry≈.291545%, exit≈14.2857%. Burst lengths are geometric, not exactly5–10 packets. Coding/probes also advance loss state. Same seeds do not guarantee identical packet losses across modes because packet counts/timing change.

Optional path fields: `jitter_ms`, `correlation_pct`, `reorder_pct`, `duplicate_pct`, `queue_packets`, `burst.mean_length`. Outages use interface down/up events. Seed support is required; unsupported kernels fail rather than silently ignoring seeds. Rate via netem is a pilot shaper: timer resolution/offloads can distort capacity/delay. Validate achieved throughput before use; high-rate follow-up should validate HTB/TBF+netem placement. Configured capacity is **not measured available bandwidth**.

Exact C0–C10 states are in screening.yaml:30/30 healthy;30/60;30/150; RTT30/40 loss.1/1%; RTT30/40 loss5/.1%; cleanA and B2% loss mean7;100/20 Mbps; B20 Mbps with30 Mbps competing UDP load; A2% independent and B100 ms/2% mean7; B2/5/10-second outages; A permanent failure at40 s. C7's extra20 Mbps bottleneck is explicit. Queue limit1000 is a calibration/sensitivity parameter, not universal realism.

## Part 5 — Mechanisms

Single sends on configured A or B (`single_path: 0|1`). The exact pilot fixes A; repeat a clean-B baseline before an adaptation claim. A best-measured-path baseline must select from independent pre-run probes under a preregistered rule; this automatic selector is **not implemented**.

Steering uses deterministic weighted flow-ID buckets with fixed affinity. One-flow RTC cannot demonstrate multi-flow load balancing; use many flows later. Striping uses weighted sequence buckets;1,1 is round robin,5,1 is weighted, externally measured capacity can supply proportional weights. Receiver delivers out of order, counting a unique arrival below the highest observed sequence as reordered. A later bounded reorder-buffer ablation must charge its added delay.

Replication sends identical originals on both paths; receiver delivers first valid copy, logs duplicates and first-arrival path. XOR FEC is systematic on A with one parity after k originals. k5 gives20%, k10 gives10%, k3 gives33.3%; this code cannot provide arbitrary/exact30% redundancy or recover two erasures per block. Follow-up Reed–Solomon should hold block size/deadline semantics explicit. Original timestamps are part of coded bodies, so recovery preserves latency. At20 ms intervals, first packet may wait80 ms for parity emission; surviving systematics do not wait. Late reconstruction counts as a miss. Partial last blocks have no parity. State expires after5 s. Seen-sequence state grows with bounded run length; indefinite service needs bounded windows.

Header32 bytes `!4sQIIQBBBB`: magic4, experiment8, flow4, sequence4, tx timestamp8, mode/path/k/symbol1 each. Body contains original timestamp8+payload. Parity uses block-base sequence and symbol=k. Data timestamp duplication enables recovery/debugging. UDP checksum/trusted laboratory senders provide validity; no adversarial security claim. Max source payload1300 avoids typical fragmentation. Sequence wrap is unsupported. Encode duration and parity-emission time are logged in coding.csv; decode duration is logged per recovered packet.

## Part 6 — Workloads

Executable RTC:200-byte originals every20 ms =80 kbps source payload, deadline100 ms. Offered source schedule is equal across modes; redundant/coding traffic is additional capacity cost. This is a synthetic deadline workload, not a codec, MOS estimator or congestion-controlled WebRTC implementation. Maximum delivery gap is an interruption proxy, **not** video-freeze or event recovery time.

Python must pass pacing/CPU calibration at every rate: pilot thresholds p99 sender lag≤2 ms, hostCPU<85%, average process CPU<.8 core. Those are operational parameters, not discovered scientific thresholds. High-rate bottleneck/striping claims require a Go/Rust/C plane if Python biases results.

Transactional extension: persistent HTTP/1.1/2 requests with fixed sizes/arrival process, completion p50/p95/p99, timeouts and errors. Bulk: fixed-size TCP transfer/iperf3 with congestion control held constant, goodput/completion/TCP retransmissions/utilization. Optional QUIC must use comparable application demand. `native_baselines.py` records direct HTTP/TCP baselines only; it does not send them through the UDP mode engine. H4 remains untested until the transport abstraction exists.

## Part 7 — Telemetry

`tx.csv`: complete offered originals, phases, timestamps and pacing lag. `wire.csv`: successful socket writes including IPv4/UDP/experiment headers; subsequently qdisc-dropped bytes still count. `send_errors.csv`: local send failures. `rx.csv`: timestamp/path/duplicate/reordering/FEC/decode time. `path.csv`: separate-port echo RTT and misses, paced≈100 ms between iterations, slowed by timeouts. `host.json`:≈1 s CPU/processCPU/RSS/interface/qdisc snapshots. Probes share bottlenecks and advance impairment state.

CLOCK_MONOTONIC is common to same-host namespaces, permitting one-way estimates including userspace/scheduler costs. External hosts have different monotonic origins: do not deploy these timestamps unchanged across machines. Use PTP or monitored chrony plus realtime/TAI or explicit clock mapping; quantify offset uncertainty against effect sizes. Use RTT/completion when synchronization cannot support one-way claims.

Not implemented: available-bandwidth estimator, Prometheus/Parquet exporter, hardware timestamps, cross-host clock mapping, sample-count-gated per-window p99 RTT. CPU is logged but not included in current Pareto axes. Queue delay may be estimated relative to an unloaded baseline with uncertainty, not inferred from raw RTT alone. Typed schema dictionaries are in telemetry/schemas.

## Part 8 — YAML

pilot.yaml defines six losses/four modes/ten reps; screening.yaml uses named paths/events and C7 cross traffic; stage2 configs contain45 loss×RTT states and13 burst/bandwidth states. Warmup boundary must align with FEC block size. Every run records expanded configuration, seed and exact commands. Example objective is separate optional JSON; no default weighted winner is imposed.

## Part 9 — Orchestration

Runner resets namespaces, configures/verifies netem, saves state, stabilizes20 s, verifies receiver readiness, starts probes/workload, triggers events, snapshots telemetry, drains, checks exits/count/timing/CPU, records failures and cleans up. Invalid logs are retained. Existing run directories are never overwritten. Metadata captures kernel/Python/source hashes and git commit if available. Container root alone does not grant namespace privileges. SIGTERM/interrupt invokes finally; SIGKILL/power failure requires cleanup and an incomplete-run audit. Expected event paths have relaxed probe-loss validation; manually check outside event windows.

## Part 10 — Matrix

6×4×10=240 unique runs;60(condition,repetition) blocks. Seed20271001 shuffles blocks then mode order within blocks. Independent repetitions use distinct netem seeds, modes within a block share seed without identical-loss guarantees. Run-level pairing is by block, not packet.

Each measurement120 s has6000 offered originals. Scheduled run≈165 s including20 s stabilization,10 s warmup,120 s measurement, collector/drain margin and10 s cooldown; pilot≈11 hours plus setup. Add single-B/best-measured-path and FEC placement/weighted striping ablations later. A clean slowerB may beat every redundancy mode; report it. Negative findings remain informative.

## Part 11 — Statistics

Pipeline joins offered originals to first arrivals and calculates run quantiles/loss/deadline/goodput/overhead. Bootstrap5000 **runs** for95% CIs of mean run statistics. Pooled delivered-packet CDF is descriptive only. Ten reps are exploratory, not automatically powered. Paired differences use exact sign-flip tests≤16 pairs, Monte Carlo beyond, physical effect sizes and paired-run bootstrap CIs. Sign-flip requires symmetry/exchangeability, not merely matched labels. Holm corrects all generated state/metric/pair tests. Final experiments should preregister a primary endpoint/minimum relevant effect and valid randomized-label or robust modeling assumptions.

Confirmatory model: metric~mode+measured_loss+measured_delta_RTT+mode:loss+mode:delta_RTT+(1|block), adding day/site/path pair with sufficient independent levels. Fraction endpoints may need binomial/beta-binomial mixed models, quantiles/completion robust or transformed fits. Mixed-effects fitting is specified, **not implemented** here. Account for autocorrelation/state measurement error.

Power approximation for paired difference: n≈[(z_(1-alpha/2)+z_(1-beta))×sigma_d/delta]^2. Estimate paired SD from pilot with uncertainty, use corrected alpha, inflate for clustering and simulate nonlinear/quantile endpoints. Freeze final n and endpoints before held-out confirmation;30 is a starting suggestion, not a rule. Never count packets as replicates.

## Part 12 — Oracle

Optional objective labels lowest observed mean per state: an empirical state oracle, not temporal clairvoyance. Sequential experiments lack every action's counterfactual future outcome. Taking per-run minima adds selection noise and is not realizable regret.

Code leaves one repetition out, selects per-state mode and global static mode from remaining repetitions, and compares both on held-out runs. `heldout_static_minus_selected` estimates exploratory state-selection benefit. Bootstrap by repetition and validate in a new dataset before a headline claim. `hindsight_min` and its gap are explicitly optimistic/noise-biased. A time-resolved oracle/regret R=sum(J(policy)-J(oracle)) requires validated repeatable trace replay, comparable outcomes, resource limits and switching costs. FEC fill/drain, state-estimation and mode-switch disruption reduce achievable benefits.

## Part 13 — Figures

Code generates vector PDF CDFs; latency/loss/deadline/goodput/overhead curves; Pareto scatter; reordering/FEC-recovered fraction/maximum-gap curves; replication first-arrival bars; optional objective winner heatmap and preferred-mode tables against loss/RTT. Width3.35 inches/font8, distinguishable markers/styles and grayscale. Generate only from valid observations.

Extensions still needed: event-aligned recovery time (gap is not recovery), explicit faceted preferred-mode-versus-RTT plots, success divided by genuinely recoverable FEC erasure events, uncertainty-annotated multidimensional maps. Default loss curves are for the single-dimensional pilot; do not collapse RTT/burst/bandwidth states into one curve. Heatmaps only make sense for loss×RTT with all other variables fixed. Lost packets are absent from CDFs, so pair with loss/miss plots. No measured results are supplied before experiments.

## Part 14 — Acceptance checks

1. Run tests, then smoke each mode. Verify receiver readiness, exits, packet counts, all metadata/logs and cleanup.
2. No impairment: unique originals match offered count; replication delivers once/records second arrival; FEC sends1 parity per5 originals. Erase each possible single symbol, verify bytes/timestamps; two erasures must remain unrecovered.
3. Verify echo RTT≈30/50 ms and ordinary one-way≈15/25 ms plus overhead. Deliberately delay/drop originals to check misses, including late FEC recovery.
4. Long independent tagged-packet calibration for measured Bernoulli loss/confidence and geometric burst distribution/P(loss|prior loss). Sparse idle probes do not establish0.1% loss accurately.
5. iperf calibration for actual shaping/queue/drop counts at each size/rate. Verify offloads disabled, no shared CPU/native-rate bottleneck, no unexpected socket errors.
6. Validate pacing/CPU at every offered load. Audit shorter-window per-process utilization and receiver socket drops (`/proc/net/udp`/SNMP); those are not yet comprehensive automated rejection gates.
7. Verify event schedule, unaffected path and actual recovery separately. Expected-event paths are broadly exempted from probe-loss threshold, so inspect outside outage windows manually.
8. Ctrl-C/emergency cleanup must leave management interface unchanged. Save tc/kernel versions and qdisc attributes.
9. Audit missing metadata, truncated logs, entire expected matrix and all exclusions. Automated kind check does not numerically prove all configured qdisc parameters. Manual calibration remains required.

## Part 15 — Boundary design

Start coarse/corners/center, then refine where frontiers/objective winners are uncertain. Full45-cell grid×4×10=1800 runs should follow targeted exploration, not immediately exhaust time. Match mean loss while varying burst means2/7/15, then ratios1/2/5/10 at comparable offered load. Fractional-factorial screening ranks interactions; D-optimal/response-surface refinement and replicated center points reduce cost. Categorical modes need interaction terms; outages need separate treatment. Confirmation points/data remain separate from adaptive exploration. Report empirical tested regions, never universal thresholds. Application-class tests must vary real workload semantics, not just packet sizes.

## Part 16 — Real-network validation

Dedicated authorized test circuits only. Separate local controlled-edge impairment from observational external variation. FiberA+fiberB, fiber+LEO, LEO+LEO and3-path validation needs generalized sockets/addresses, reachable gateway, NAT/MTU/security and cross-host timestamp support absent from this pilot. Fix gateway placement and record route changes/provider shared risks. Commercially distinct links may share upstreams/gateways/constellation failures.

Collect days/weeks of external RTT/loss runs/outages/throughput/routes; randomize short matched blocks by time/day/site/terminal pair. Authorized Starlink obstruction/link-state/uptime telemetry is supplementary when legitimately exposed; external measurements remain primary. No unofficial/private API dependency. Freeze emulation-derived decisions and assess held-out qualitative transfer. Observational validation alone does not establish causality.

## Part 17 — Reproducibility

README contains exact install/test/matrix/smoke/pilot/analysis/cleanup commands. Save raw denominators, invalid-run ledger, calibration, endpoints/weights and code together. Metadata source SHA256 supports archive traceability when git is absent. At campaign start capture pip freeze, uname, ip/tc versions, ethtool version, CPU/hardware and timer settings. CSV first; Parquet/Prometheus are future exports. Never publish summaries without complete run audits.

## Part 18 — Reviewer critique and responses

A — Systems: Python/no congestion control, XOR and no reorder buffer can bias results; shared-host paths are not physical independent WANs. Addressed through low-rate scope/pacing gates, common packet engine, explicit FEC/reordering semantics and timestamp correctness tests. Compiled high-rate engine, stronger FEC/reorder ablations and physical validation remain required before broad claims.

B — Methodology: cleanB may defeat adaptation;10 reps may lack power; shared seeds are not identical outcomes; configured state differs from observed state; packet pseudo-replication is invalid. Addressed through cleanB/best-path follow-up requirement, run-level randomized-block analysis, CIs/power plan, measured calibration and held-out confirmation. Do not advertise exploratory winner maps as final evidence.

C — SIGCOMM/NSDI: synthetic mode crossings alone are motivation, not a sufficient systems contribution. Require held-out benefit over strong static policies, multi-app/path transfer, online feasibility, switching cost and ablations before controller work. Publish honest negative outcomes if benefits disappear. This package does not promise venue acceptance.

Primary command reference: upstream iproute2 tc-netem manual, https://kernel.googlesource.com/pub/scm/network/iproute2/iproute2-next/+/refs/heads/main/man/man8/tc-netem.8 . Verify against installed kernel/iproute2 versions.
