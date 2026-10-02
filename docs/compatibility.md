# Adapter compatibility and design review

Status: **Shared framework and nine native adapters implemented for pinned native releases.** Copilot is a documentation-only candidate awaiting separate approval; Cursor remains a documentation-only blocked design. Source links and detailed native boundaries are in each adapter README/spec. Unsupported releases fail closed. The table records verified capabilities, not provider-brand compatibility or successful inference.

| Adapter | Supported release | Native verification |
| --- | --- | --- |
| Claude Code | 2.1.287 | Isolated auth inspection and Anthropic localhost request |
| Codex | 0.160.0 | Native profile-v2 parsing and localhost Responses requests for all roles |
| Pi | 1.0.0 | Localhost requests for four protocols and three roles |
| DeepSeek Harness | 0.2.0-rc.2 | Native schema dump and localhost requests for three protocols/roles |
| Kimi Code | Successor CLI 2.1.1 | Localhost requests for four protocols and three roles |
| OpenCode | 1.18.34 | Localhost requests for four protocols and three roles |
| Hermes Agent | 0.21.5 / 5bba024d | Localhost requests for three protocols and three roles |
| OpenClaw | 2026.9.7 / c074824 | Four protocols/roles, key rotation, config validation and isolated authenticated gateway |
| ZCode | 3.14.3 / Agent 0.16.9 | Three protocols/roles, two providers, structured IDs, headers and key rotation |

All nine adapters were checked on 2026-10-02 with fake keys and temporary native config/state. HTTP error stubs prove the selected endpoint, wire protocol, exact upstream model and credential; they do not test complete model responses, remote gateways or messaging integrations. OpenClaw additionally passed isolated authenticated gateway health checks. ZCode is a local build from official source revision `29628c9acdb81b703bbd4080c207a0e7ce5e276e`, with a documented packaging workaround.

Qoder was updated to 1.1.65 and Cursor to 2026.10.01-e373342. Both remain documentation-only because no supported noninteractive interface has been verified for provisioning the complete custom-provider tuple. Copilot was not installed locally and remains a documentation-only candidate.

## Configuration strategy

| Adapter | Managed profile | Credential delivery | Role handling | Personal state |
| --- | --- | --- | --- | --- |
| [Claude Code](../harnesses/claude-code/SPEC.md) | Private role JSON settings overlay | Native literal environment settings | Native Haiku/Sonnet/Opus tiers plus selected role | Shared |
| [Codex](../harnesses/codex/SPEC.md) | Separate native TOML profile per role | Named environment key | Selected profile/model | Shared with current profile format |
| [Pi](../harnesses/pi/SPEC.md) | Isolated agent directory | Named environment key | CLI provider/model | Separate |
| [DeepSeek Harness](../harnesses/deepseek-harness/SPEC.md) | Isolated role home and profile Cordis patch | Native credential references | Role-specific default selection | Separate |
| [Kimi Code](../harnesses/kimi-code/SPEC.md) | Isolated native home/config | Literal key in private TOML | Native model alias | Separate |
| [OpenCode](../harnesses/opencode/SPEC.md) | Runtime provider overlay from managed JSON | Environment reference | Primary/small model; complex selectable | Shared |
| [Hermes Agent](../harnesses/hermes-agent/SPEC.md) | Isolated native home | Private native dotenv and child environment | Active model selection | Separate |
| [OpenClaw](../harnesses/openclaw/SPEC.md) | Isolated state/workspace per role | Native environment SecretRefs; literal authorized defaults | Aliases and primary selection | Separate |
| [GitHub Copilot CLI](../harnesses/copilot/SPEC.md) | Private per-provider/per-role `providers.json`, selected by child-scoped `COPILOT_PROVIDERS_CONFIG` | Verified environment reference or private derived registry | Verified registry selector bound to exact upstream ID | Shared |
| [Qoder CLI](../harnesses/qoder/SPEC.md) | Blocked: supported noninteractive BYOK provisioning not documented | Wizard-managed; automated delivery unverified | BYOK key selection does not provision the canonical provider tuple | Unverified |
| [ZCode CLI](../harnesses/zcode/SPEC.md) | Private per-provider/per-role provider file via `ZCODE_PERSONAL_PROVIDER_CONFIG_FILE` | Literal key in private JSON | Structured `defaultModelSelection`; explicit capacities, reasoning disabled | Separate via `ZCODE_DATA_BASE_DIR` |
| [Cursor Agent CLI](../harnesses/cursor/SPEC.md) | Blocked: no documented custom-provider profile | None | Cursor catalog selection cannot bind the canonical provider tuple | Shared, but unsupported |

“Separate” means the tool does not implicitly copy sessions, skills, plugins or OAuth into the provider profile. “Shared” means native personal state remains visible; the overlay only pins managed provider/model settings. These are configuration strategies, not sandbox boundaries.

## Protocol support

`Yes` means verified on the pinned release above. `Candidate` requires separate
implementation approval and native testing. `Conditional` remains unimplemented.
`Blocked` has no verified interface for the provider tuple. `No` has no enabled mapping.

| Adapter | Anthropic Messages | OpenAI Chat | OpenAI Responses | Google GenAI |
| --- | --- | --- | --- | --- |
| Claude Code | Yes | No | No | No |
| Codex | No | No | Yes | No |
| Pi | Yes | Yes | Yes | Yes |
| DeepSeek Harness | Yes | Yes | Yes | No |
| Kimi Code | Yes | Yes | Yes | Yes |
| OpenCode | Yes | Yes | Yes | Yes |
| Hermes Agent | Yes | Yes | Yes | No |
| OpenClaw | Yes | Yes | Yes | Yes |
| GitHub Copilot CLI | Candidate | Candidate | Conditional | No |
| Qoder CLI | Blocked | Blocked | Blocked | Blocked |
| ZCode CLI | Yes | Yes | Yes | No |
| Cursor Agent CLI | Blocked | Blocked | Blocked | Blocked |

Provider brand alone never establishes protocol compatibility. A multi-protocol gateway can use explicit per-harness overrides. The tool does not supply a proxy or convert requests.

## Version boundaries and upgrade gates

- **Codex:** implemented for the 0.160.0 separate-file profile format; other versions fail closed. Inline profiles are never installed by changing the default file without permission.
- **Kimi:** only successor CLI 2.1.1 is enabled, with `KIMI_CODE_HOME`, static providers and native model aliases. Context metadata must exceed its configured reserved context. Output-limit and reasoning-effort mappings are rejected.
- **DeepSeek:** only bundled profiles in 0.2.0-rc.2 are enabled. Google GenAI and reasoning mappings are rejected. Custom executable YAML is never evaluated.
- **Hermes:** pin both version and revision; preserve native dotenv semantics and select the committed PM dependency generation. Missing optional SDKs need native installation; sync/launch do not install them. Google GenAI is rejected.
- **OpenCode:** fixed bundled SDKs plus inline per-model endpoint/key overrides defeat stale project routing. Managed launches use `--pure`; external plugins and routing flags are excluded. Reasoning effort is rejected.
- **OpenClaw:** native SecretRefs and independent role state are enabled. Gateways require explicit distinct port ranges; service control, no-auth, reasoning effort and include-based default edits are rejected.
- **Claude/Pi:** upgrades must recheck credential precedence and model selection. Claude only supports Anthropic and rejects custom headers. Pi uses a private catalog/home and rejects a conflicting stored managed-provider key.
- **GitHub Copilot CLI:** pending separate approval; pin the registry schema/version, credential representation and native selector grammar; prove registry precedence and failure without fallback; clear inherited legacy routing/credential commands and reject model-changing overrides. The reference documents `providers.json`, while the BYOK guide still describes legacy environment configuration. Responses remains conditional on registry wire evidence; internal/subagent routing and native defaults require explicit verification.
- **Qoder CLI:** selected documentation target; the current official guide requires the BYOK wizard and advises against manual BYOK settings. Require a supported provisioning schema/API, exact selector binding, safe credential delivery and native precedence tests before implementation.
- **ZCode CLI:** distribution 3.14.3 / Agent 0.16.9 uses schemaVersion-1 provider rules, explicit model capacities, private literal credentials and isolated data roots. An empty built-in catalog prevents account/catalog fallback. Reasoning metadata, native default writes, resumed startup, workflows and Web/server modes are rejected. Fresh-launch primary requests are verified; interactive session changes and delegation are outside the verified boundary.
- **Cursor Agent CLI:** do not implement while the CLI lacks a documented interface for endpoint, protocol, provider credential and exact model ID; re-check official sources before reconsidering.

Every claimed adapter must pass the shared default-protection, concurrent-provider, secret-rotation, preservation and failure-recovery tests in the overall spec. Tests against fixtures alone do not prove compatibility with an installed release; isolated native smoke checks are also required. No real credentials or paid inference are needed for schema/launch tests.

## Review decisions

The draft proposes:

- Python as the implementation language and macOS/Linux as the first platforms.
- Exactly three named model roles per provider; daily as wrapper default.
- Explicit role selection where the harness lacks native three-tier routing.
- Profile-only synchronization by default, with independent authorization for default writes.
- One private source of API keys, plus necessary generated copies.
- Command-triggered synchronization, documented manual shell setup and conservative handling of existing commands.
- The original eight adapters and ZCode are implemented for their pinned releases. Copilot remains a candidate; Cursor and Qoder remain blocked. Those three targets are documentation-only; no placeholder adapter counts as finished.

## Revised launch and model contract (2026-09-15)

No watcher, daemon, polling or `enabled` settings. Sync targets detected harnesses (or explicit `--harness` selections); each managed launch refreshes its own configuration first. Original bare commands remain intact and require a prior sync or the explicit managed launcher.

`name` is a label; `id` is provider-local and defaults to `name`. Adapters consume the resolved ID and translate only native configuration/selector syntax. A per-harness `id` override supports an explicitly different gateway route. No universal model-name translation catalog is maintained. See the overall spec's model identity section for primary-source evidence and required request-level verification.

Adapter authors should follow the implemented [framework contract and handoff guide](adapter-development.md). All nine registered manifests have functional native implementations for the pinned releases above. Copilot, Cursor and Qoder have documentation only and are not registry entries.
