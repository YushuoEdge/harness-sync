# Claude Code adapter specification

Status: **Draft; awaiting approval.** Adapter ID: `claude-code`. Native command: `claude`.

The [overall specification](../../SPEC.md) governs secrets, ownership, transactions, selection and default-write permission. Native facts below were checked against linked public sources on 2026-09-14 (America/New_York); no installed release has been validated yet. Proposed behavior is not an implementation claim.

## Native interface and evidence

Claude uses JSON user settings at `~/.claude/settings.json`, with `CLAUDE_CONFIG_DIR` relocation. `--settings PATH` adds a session layer; managed settings remain authoritative. [Settings and precedence](https://code.claude.com/docs/en/settings).

Its Anthropic tier variables include `ANTHROPIC_DEFAULT_HAIKU_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL`, and `ANTHROPIC_DEFAULT_OPUS_MODEL`. [Model configuration](https://code.claude.com/docs/en/model-config).

## Adapter design

- Detect `claude`, supported settings flags and configured native directory. Protocol: `anthropic` only in v1; an OpenAI gateway needs an explicit Anthropic endpoint override.
- Render managed `settings.json` for each provider, mapping simple → Haiku, daily → Sonnet, complex → Opus. Pin the active model to the requested role; daily is the wrapper default.
- Launch `claude-<alias>` through the common runner with `--settings <managed-file>` and child-scoped endpoint/key/model variables. The file records tier mappings and non-secret model settings; the runner supplies `ANTHROPIC_BASE_URL` and `ANTHROPIC_API_KEY` from the secret store.
- Clear known conflicting Anthropic token/base/model variables and incompatible provider toggles only in the child. Native precedence and OAuth interactions must be tested; never delete login data to force API authentication.
- Shared native state and unrelated settings are retained; this is an overlay, not a separate session home. Organizational constraints remain effective. Reject extra `--settings` and config-directory changes through the wrapper; explicit model selection is allowed within the selected provider.

## Authorized default writes

Merge only `model` and managed provider/tier entries in `env`; native settings require resolved literal values for these environment assignments unless a verified version offers a suitable credential helper. A key written there makes the file secret-bearing. Profile-only sync must not touch it. Existing conflicting authentication settings become explicit owned-field changes in the plan; preserve all other fields and login stores.

## Verification and limitations

Test tier mapping, native CLI/env precedence, two simultaneous keys/endpoints, existing OAuth, settings collisions, managed restrictions, and unchanged default-file hashes after profile launch. Verify native auth selection in isolated fixtures before enabling wrappers. File sync takes effect for new launches; do not promise active-session provider switching. No arbitrary protocol translation or automatic task classification beyond Claude's native behavior.

## Planned directory ownership

After approval, this directory will contain `adapter.py`, versioned native fixtures and adapter tests. Harness-specific detection, rendering, merge paths, launch rules and compatibility checks stay here; shared I/O and secret handling remain in the core.
