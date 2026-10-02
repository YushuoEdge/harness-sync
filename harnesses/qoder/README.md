# Qoder CLI harness

**Selected harness; design only, blocked on a supported noninteractive BYOK interface.**

Read the [adapter specification](SPEC.md) and [overall specification](../../SPEC.md).

| Item | Selection and integration boundary |
| --- | --- |
| Proposed adapter ID | `qoder` |
| Native executable | `qodercli` |
| Provider command | Proposed `qoder-<alias>` after the integration gates pass |
| Role selection | Proposed simple/daily/complex selection; native `--model` selects a model or BYOK key |
| Native configuration | `~/.qoder/settings.json`; configuration directory can be overridden |
| Credentials | BYOK wizard today; safe automated delivery remains unverified |
| Personal state | Sharing or isolation remains undecided pending BYOK storage verification |
| Inspected release | `1.1.65`; isolated version/help checked on 2026-10-02; custom-provider provisioning remains blocked |

Qoder's official [custom-model guide](https://docs.qoder.com/cli/custom-models) directs users to the Custom tab in `/model` and advises against configuring BYOK manually in `settings.json`. An existing BYOK selection is insufficient to synchronize a new canonical provider, endpoint, credential and exact upstream model ID.

This directory contains documentation only: no manifest, adapter implementation, installed wrapper or native configuration change. `harness-sync plan --harness qoder` is not yet a supported selection. Implementation was authorized on 2026-10-02, but still needs a supported provisioning interface and verified native behavior; see the spec's release gates.

## 2026-10-02 installation and compatibility check

The local `qodercli` was updated to **1.1.65** with its native `update` command.
Isolated `QODER_CONFIG_DIR` probes confirm model selection, settings overlays and config-root
flags, but no provider import/provisioning command. The [current official BYOK guide](https://docs.qoder.com/cli/custom-models)
still requires the interactive Custom wizard and explicitly warns against manual BYOK entries
in `settings.json`. Implementation approval does not supply the missing native interface.
This target remains documentation-only: no guessed credential schema or nonfunctional adapter
is advertised. No account login, credential database edit or native-default write was performed.
