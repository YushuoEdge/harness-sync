# Qoder CLI adapter specification

Status: **Selected harness; design only, blocked on noninteractive BYOK provisioning.** Proposed adapter ID: `qoder`. Native command: `qodercli` (the installed distribution).

Selection adds a documentation target outside the original eight-adapter v1 set. Implementation was authorized on 2026-10-02; native default writes remain unauthorized. Official sources were checked on 2026-10-01 (America/New_York). Qoder CLI was updated from 0.1.44 to 1.1.65 on 2026-10-02; isolated version/help probes are captured in `fixtures/`. No manifest is included because provisioning remains blocked.

## Native interface and evidence

Qoder documents `--model` / `-m` for a model identifier or BYOK key, `--list-models`, `--config-dir`, and noninteractive `--print`. These are discovery and selection interfaces, not a documented provider provisioning API. [CLI reference](https://docs.qoder.com/cli/cli-reference).

The current BYOK guide requires the interactive `/model` Custom wizard. Its provider/model catalog and credential fields depend on the current account. It says not to configure BYOK manually in `settings.json`; it publishes no stable import schema for arbitrary endpoint, protocol, credential and exact upstream ID. [Custom models](https://docs.qoder.com/cli/custom-models).

Ordinary settings live at user, project and local levels. `QODER_CONFIG_DIR` relocates the default user directory, and command-line `--settings` has the highest documented settings precedence. These controls do not establish that BYOK credentials are stored or isolated there. [Configuration files and application order](https://docs.qoder.com/cli/settings).

The settings reference describes `model.name`, aliases and overrides. Do not reinterpret these as a supported custom-provider registry. [Settings reference](https://docs.qoder.com/cli/settings-reference).

## Compatibility decision

All four canonical protocols remain blocked for automated synchronization until Qoder exposes a complete supported provider interface. BYOK availability does not prove arbitrary provider provisioning or distinguish OpenAI Chat from Responses. Do not infer protocol support from a provider brand, local alias or an older announcement.

The current framework cannot synchronize this target. Keep the directory documentation-only and keep `qoder` out of the packaged registry. Do not automate the wizard, reverse-engineer credential databases, launch authentication or install Qoder during detection.

## Proposed managed launch after the blocker is resolved

- Consume the canonical protocol, `provider.endpoint_for("qoder")`, scoped secret and `model.upstream_id("qoder")` without changing the upstream ID. Reject unsupported protocols, headers and metadata.
- Prefer a supported child-scoped provider overlay. If an isolated native configuration directory is required, use a managed provider directory without changing OS `HOME` or copying sessions, credentials, skills or plugins. Document the verified state boundary before implementation.
- Generate one role selection per provider; `qoder-<alias>` would select daily. A BYOK key may be a local selector only if it provably resolves to the exact endpoint/model tuple.
- Deliver credentials through verified native environment references or private generated files. Never place secrets in argv, plans or logs; do not assume generic settings interpolation works for BYOK.
- Reject extra model, settings and config-directory overrides that escape the managed tuple, including split and equals forms. Verify project/local settings, resumed sessions, subagents and automatic routing; reject modes that cannot retain the tuple.
- Preserve unrelated permissions and enforced policy. Never temporarily swap global files to route concurrent providers.

## Default writes

No native default changes are proposed for this introduction. A future adapter must reject default-write requests until provider storage, merge ownership and credential handling are verified and specified. Ordinary synchronization remains profile-only.

## Release gates

1. Obtain an official noninteractive provider schema or API; pin a supported Qoder release and account/edition requirements. Capture sanitized help, version and configuration fixtures.
2. Prove protocol, endpoint, credential and exact upstream ID routing with a local stub endpoint, including slash-containing IDs and two providers sharing a display label. Fail without fallback when a tuple is invalid.
3. Verify credential precedence, key rotation, inherited environment, role selection, project overrides, session resume and subagent routing.
4. Prove concurrent provider isolation, state preservation, idempotence, rollback and no native default writes during normal sync.
5. Obtain implementation approval, then add the manifest, adapter and native tests. Recheck official sources before advertising support.

## 2026-10-02 installation and compatibility check

The local `qodercli` was updated to **1.1.65** with its native `update` command.
Isolated `QODER_CONFIG_DIR` probes confirm model selection, settings overlays and config-root
flags, but no provider import/provisioning command. The [current official BYOK guide](https://docs.qoder.com/cli/custom-models)
still requires the interactive Custom wizard and explicitly warns against manual BYOK entries
in `settings.json`. Implementation approval does not supply the missing native interface.
This target remains documentation-only: no guessed credential schema or nonfunctional adapter
is advertised. No account login, credential database edit or native-default write was performed.
