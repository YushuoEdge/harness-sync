# Cursor Agent CLI adapter specification

Status: **Design only; blocked on a documented CLI custom-provider interface.** Proposed adapter ID: `cursor`. Current primary native command: `agent`; `cursor-agent` remains a compatibility alias.

This research-only design is outside the currently approved eight-adapter v1 implementation set. The [overall specification](../../SPEC.md) requires every adapter to route a complete canonical provider tuple—protocol, base URL, credential and exact model ID—without guessing or silently dropping fields. Native facts below were checked against official Cursor documentation on 2026-09-15 (America/New_York); no installed release has been validated. This directory deliberately contains no manifest or adapter code, so the packaged registry does not advertise Cursor support.

## Native interface and evidence

Cursor identifies `agent` as the current primary CLI entry point and retains `cursor-agent` as a backward-compatible alias. Model discovery and selection use `agent models`, `--list-models`, `/models` and `--model`. [Cursor CLI changelog, 2026-01-08](https://cursor.com/changelog/cli-jan-08-2026). The CLI can also be installed and invoked as `cursor-agent`. [Installation](https://docs.cursor.com/en/cli/installation) and [parameters](https://docs.cursor.com/en/cli/reference/parameters).

Global CLI configuration is pure JSON at `~/.cursor/cli-config.json`, or below `CURSOR_CONFIG_DIR` / `XDG_CONFIG_HOME`. Its documented schema includes a CLI-managed model object, permissions and UI/network preferences. Project configuration supports permissions only. The documentation warns that some fields are CLI-managed and may be overwritten. It publishes no custom LLM provider endpoint, protocol or credential fields for Agent CLI. [CLI configuration](https://prod.cursor.com/docs/cli/reference/configuration).

CLI authentication is browser-based or uses `CURSOR_API_KEY`, generated from the Cursor dashboard. `--api-key` also exists, but secrets on argv violate this project's contract. The documented `--endpoint` troubleshooting option is not described as an OpenAI-, Anthropic- or Google-compatible model-provider endpoint and must not be reinterpreted as one. [CLI authentication](https://docs.cursor.com/en/cli/reference/authentication).

Cursor's desktop editor separately supports provider API keys entered and verified through **Cursor Settings > Models** for OpenAI, Anthropic, Google, Azure OpenAI and AWS Bedrock. That page describes a UI workflow, not a stable file format or CLI configuration surface; specialized features still use Cursor models. [Cursor API keys](https://docs.cursor.com/settings/api-keys).

## Compatibility decision

There is no safe v1 mapping from any canonical protocol to the currently documented Cursor Agent CLI:

- `--model` selects from Cursor's available model catalog but does not bind the canonical `base_url` or provider credential.
- `CURSOR_API_KEY` is Cursor-service authentication, not the canonical LLM provider key.
- `--endpoint` is insufficiently specified and may target Cursor infrastructure; using it for an arbitrary LLM endpoint would be guesswork and could send a credential to the wrong service.
- The desktop editor's BYOK UI has no documented, format-stable configuration file for transactional editing and is not the Agent CLI interface.

An adapter that merely passes `--model` while discarding endpoint/protocol/key would violate provider isolation, key rotation and model-identity guarantees. An adapter that writes Cursor's private application database or credential store would rely on reverse-engineered state and is explicitly out of scope. Therefore the proposed protocol set is empty and implementation is blocked.

## Future adapter design, conditional on an official interface

Re-evaluate this design only when Cursor publishes a noninteractive interface that accepts an arbitrary provider endpoint, protocol, credential reference and exact model ID for Agent CLI. If such an interface appears:

- Detect both `agent` and `cursor-agent`, resolve which executable belongs to Cursor, and pin supported versions/capabilities. Do not accept an unrelated executable named `agent` based on filename alone.
- Prefer child-scoped environment or explicit provider-profile selection. Never pass credentials through `--api-key`, write a secret into project configuration, or mutate the OS `HOME`.
- Keep normal Cursor sessions, rules, MCP configuration, permissions and login shared unless the official interface requires an isolated `CURSOR_CONFIG_DIR`. If isolation is required, document exactly which personal state becomes separate and never copy it implicitly.
- Map every supported canonical protocol from official wire-level evidence and verify exact requests with a local stub. Preserve the upstream model ID exactly and use `--model` only if it selects that same provider-facing ID.
- Reject inherited routing variables and CLI flags that can independently replace the endpoint, credential or model. Treat Cursor subscription models and user-supplied providers as distinct; never infer equivalence from a display name.
- Generate `agent-<alias>` versus `cursor-agent-<alias>` wrappers only after reviewing collision risk and the detected installation. The generic `agent` command name makes wrapper identity a design decision, not a harmless default.

## Authorized default writes

None are proposed. `default.write: true` or `--write-defaults` must fail explicitly if a future incomplete adapter is present. The documented `model` object in `cli-config.json` does not encode the canonical endpoint/key tuple, is partly CLI-managed and cannot establish a safe provider default by itself.

Even after a BYOK launch interface appears, native default writes need a separate review of schema ownership, merge behavior, credential storage and precedence. Ordinary synchronization must never alter `~/.cursor/cli-config.json`, editor settings, application databases or keychain entries.

## Verification and release gates

- Re-check official CLI configuration, authentication, parameters and changelog documentation; documentation absence today is not proof of permanent impossibility.
- Capture versioned, sanitized `--version`, help and model-list fixtures without login, updates or inference. Verify probes do not create or repair real configuration files.
- Prove all three roles route exact endpoint/protocol/key/model tuples through local request stubs. Model selection alone is not sufficient evidence.
- Test Cursor-service auth and third-party provider auth as separate concepts; no key may be reused across an inferred endpoint.
- Verify conflicting inherited environment, native model flags, resumed sessions and CLI-managed configuration cannot override the selected provider tuple.
- Confirm no editor database, keychain, login, rules, permissions, sessions, MCP settings or shell startup files change.
- Keep the adapter unregistered until these gates pass. A detection-only or model-only placeholder must report `not-implemented`, not installed support.

## Command-triggered sync and model identity

If the blocker is resolved, each generated provider command must use the common pre-launch sync contract and a complete child-scoped provider tuple. There must be no background watcher or implicit change to the bare `agent` / `cursor-agent` commands.

Consume the core's resolved provider-local model `id` (falling back to `name`), never infer an ID from a Cursor display label. Test two providers using the same label but different API IDs, explicit per-harness ID overrides, slash-containing IDs and repeated IDs. Cursor-hosted catalog names are not evidence that an external endpoint uses the same identifier.

## Planned directory ownership

No implementation files are authorized by this specification alone. After the native blocker is resolved and the revised design is approved, this directory may add `adapter.json`, `adapter.py`, versioned fixtures and adapter tests. Shared I/O, wrapper creation and secret handling remain in the core.
