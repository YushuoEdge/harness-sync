# Qoder CLI harness

**Selected harness; design only, blocked on a supported noninteractive BYOK interface.**

Read the [adapter specification](SPEC.md) and [overall specification](../../SPEC.md).

| Item | Selection and integration boundary |
| --- | --- |
| Proposed adapter ID | `qoder` |
| Native executable | `qoder` |
| Provider command | Proposed `qoder-<alias>` after the integration gates pass |
| Role selection | Proposed simple/daily/complex selection; native `--model` selects a model or BYOK key |
| Native configuration | `~/.qoder/settings.json`; configuration directory can be overridden |
| Credentials | BYOK wizard today; safe automated delivery remains unverified |
| Personal state | Sharing or isolation remains undecided pending BYOK storage verification |
| Verified releases | None; no executable found on the research checkout's PATH |

Qoder's official [custom-model guide](https://docs.qoder.com/cli/custom-models) directs users to the Custom tab in `/model` and advises against configuring BYOK manually in `settings.json`. An existing BYOK selection is insufficient to synchronize a new canonical provider, endpoint, credential and exact upstream model ID.

Selection records Qoder as a research target alongside the original v1 set. This directory contains documentation only: no manifest, adapter implementation, installed wrapper or native configuration change. `harness-sync plan --harness qoder` is not yet a supported selection. Implementation needs a supported provisioning interface, pinned native behavior and separate implementation approval; see the spec's release gates.
