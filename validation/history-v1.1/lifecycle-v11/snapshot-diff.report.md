# JEV snapshot change review

**No prior approvals, measurements, or deployment decisions were carried forward.**

Configuration changed: **True**. Analysis settings changed: **False**.
Coverage sufficient to interpret absence as removal: **True**.

| Candidate | Source | Change | Requires review | Reasons |
|---|---|---|---|---|
| JEV-0B40C24F3988 | agent.py::retain_history | unchanged | True | repository_configuration_changed |
| JEV-1ED0191AB058 | agent.py::dispatch_once | unchanged | True | repository_configuration_changed |
| JEV-1EDC6846A754 | agent.py::run_steps | unchanged | True | repository_configuration_changed |
| JEV-35AB38B3026C | agent.py::publish_proposal | unchanged | True | repository_configuration_changed |
| JEV-3AB7E6831523 | agent.py::run_steps | unchanged | True | repository_configuration_changed |
| JEV-47C500E9A193 | agent.py::review_change | unchanged | True | repository_configuration_changed |
| JEV-80B425907A5D | agent.py::run_steps | unchanged | True | repository_configuration_changed |
| JEV-950F0C5EFE45 | agent.py::run_steps | unchanged | True | repository_configuration_changed |
| JEV-B4B5BF2FD219 | agent.py::run_steps | unchanged | True | repository_configuration_changed |
| JEV-BC69C74DF3CA | agent.py::publish_proposal | unchanged | True | repository_configuration_changed |
| JEV-BD68119011F6 | agent.py::distribute | unchanged | True | repository_configuration_changed |
| JEV-BF71FD853BBC | agent.py::run_steps | unchanged | True | repository_configuration_changed |
| JEV-C25AE1A294B1 | agent.py::dispatch_once | unchanged | True | repository_configuration_changed |
| JEV-D83B745FC7BF | agent.py::dispatch_once | unchanged | True | repository_configuration_changed |
| JEV-E44ED530B27A | agent.py::retain_history | unchanged | True | repository_configuration_changed |
| JEV-E69F0ED1FC49 | agent.py::dispatch_once | unchanged | True | repository_configuration_changed |
| JEV-EC417BD414AB | agent.py::distribute | unchanged | True | repository_configuration_changed |
| JEV-F60068063D8D | agent.py::run_steps | unchanged | True | repository_configuration_changed |

## Interpretation

A matching body or candidate ID is not permission to reuse old measurements. Review source, surrounding configuration and affected callers before a new experiment.

This is a comparison of full fresh scans, not incremental parsing. Missing results under partial coverage remain “not observed,” not proven removals.

Report digest: `86b286aade8d7c28e9fc1ec8a8fcbf20ea5ec7af5dfad125a2b0d7bb2cb7a82b`.
