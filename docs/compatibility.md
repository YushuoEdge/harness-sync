# Adapter compatibility and design review

Status: **Shared framework and Codex adapter implemented; seven original v1 adapters remain pending.** GitHub Copilot CLI is a documentation-only candidate awaiting separate approval, and Cursor Agent CLI is a documentation-only blocked design. Public sources for the original set were checked on 2026-09-14 (America/New_York); Cursor sources were checked on 2026-09-15; Copilot references were rechecked on 2026-09-16. Copilot 1.0.85 is an observed release candidate only; no Copilot executable was found on the current PATH. Codex CLI 0.154.0 was locally smoke-checked on 2026-09-15 without inference. Source links and detailed native mappings are in each adapter spec. Documentation can describe a newer release than the user's installed binary; detection selects only verified behavior.

## Configuration strategy

| Adapter | Proposed managed profile | Credential delivery | Role handling | Personal state |
| --- | --- | --- | --- | --- |
| [Claude Code](../harnesses/claude-code/SPEC.md) | JSON settings overlay | Child environment | Native Haiku/Sonnet/Opus tiers plus selected role | Shared |
| [Codex](../harnesses/codex/SPEC.md) | Separate native TOML profile per role | Named environment key | Selected profile/model | Shared with current profile format |
| [Pi](../harnesses/pi/SPEC.md) | Isolated agent directory | Named environment key | CLI provider/model | Separate |
| [DeepSeek Harness](../harnesses/deepseek-harness/SPEC.md) | Isolated home, settings and profile patches | Native credential references | Role-specific default selection | Separate |
| [Kimi Code](../harnesses/kimi-code/SPEC.md) | Isolated native home/config | Literal key in private TOML | Native model alias | Separate |
| [OpenCode](../harnesses/opencode/SPEC.md) | Runtime provider overlay from managed JSON | Environment reference | Primary/small model; complex selectable | Shared |
| [Hermes Agent](../harnesses/hermes-agent/SPEC.md) | Isolated native home | Private native dotenv and child environment | Active model selection | Separate |
| [OpenClaw](../harnesses/openclaw/SPEC.md) | Isolated state and role-specific config | Verified reference or private literal key | Aliases and primary selection | Separate |
| [GitHub Copilot CLI](../harnesses/copilot/SPEC.md) | Private per-provider/per-role `providers.json`, selected by child-scoped `COPILOT_PROVIDERS_CONFIG` | Verified environment reference or private derived registry | Verified registry selector bound to exact upstream ID | Shared |
| [Cursor Agent CLI](../harnesses/cursor/SPEC.md) | Blocked: no documented custom-provider profile | None | Cursor catalog selection cannot bind the canonical provider tuple | Shared, but unsupported |

“Separate” means the tool does not implicitly copy sessions, skills, plugins or OAuth into the provider profile. “Shared” means native personal state remains visible; the overlay only pins managed provider/model settings. These are configuration strategies, not sandbox boundaries.

## Protocol targets

`Target` means an approved v1 implementation target subject to native testing. `Candidate` means the mapping is designed but requires separate implementation approval and native testing. `Conditional` means enable only once a compatible native protocol/SDK has been verified. `Blocked` means the documented native interface cannot safely carry the canonical provider tuple. `No` means no direct mapping.

| Adapter | Anthropic Messages | OpenAI Chat | OpenAI Responses | Google GenAI |
| --- | --- | --- | --- | --- |
| Claude Code | Target | No | No | No |
| Codex | No | No | Implemented (0.154.0) | No |
| Pi | Target | Target | Target | Conditional |
| DeepSeek Harness | Conditional | Target | Conditional | Conditional |
| Kimi Code | Target | Target | Target | Target |
| OpenCode | Target | Target | Target | Target |
| Hermes Agent | Conditional | Target | Conditional | Conditional |
| OpenClaw | Target | Target | Target | Target |
| GitHub Copilot CLI | Candidate | Candidate | Conditional | No |
| Cursor Agent CLI | Blocked | Blocked | Blocked | Blocked |

Provider brand alone never establishes protocol compatibility. A multi-protocol gateway can use explicit per-harness overrides. The tool does not supply a proxy or convert requests.

## Specific implementation gates

- **Codex:** implemented for the 0.154.0 separate-file profile format; other versions fail closed. Inline profiles are never installed by changing the default file without permission.
- **Kimi:** distinguish current home/credential behavior from legacy CLI versions; require native model context metadata.
- **DeepSeek:** pin provider settings schema, saved-selection precedence, patch row IDs and profile bootstrap; treat tagged YAML as data, never execute it.
- **Hermes:** pin the custom-provider model/endpoint/auth schema and native dotenv semantics.
- **OpenCode:** verify SDK wire protocol and overlay precedence against project/managed settings.
- **OpenClaw:** verify secret references, alias keys, gateway/state isolation and distinct ports.
- **Claude/Pi:** verify auth precedence and role/model selection against the installed release.
- **GitHub Copilot CLI:** pending separate approval; pin the registry schema/version, credential representation and native selector grammar; prove registry precedence and failure without fallback; clear inherited legacy routing/credential commands and reject model-changing overrides. The reference documents `providers.json`, while the BYOK guide still describes legacy environment configuration. Responses remains conditional on registry wire evidence; internal/subagent routing and native defaults require explicit verification.
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
- All eight approved adapters required before claiming v1 support; Copilot remains an additional candidate and Cursor remains blocked; no placeholder adapter counts as finished.

## Revised launch and model contract (2026-09-15)

No watcher, daemon, polling or `enabled` settings. Sync targets detected harnesses (or explicit `--harness` selections); each managed launch refreshes its own configuration first. Original bare commands remain intact and require a prior sync or the explicit managed launcher.

`name` is a label; `id` is provider-local and defaults to `name`. Adapters consume the resolved ID and translate only native configuration/selector syntax. A per-harness `id` override supports an explicitly different gateway route. No universal model-name translation catalog is maintained. See the overall spec's model identity section for primary-source evidence and required request-level verification.

Adapter authors should follow the implemented [framework contract and handoff guide](adapter-development.md). Codex is implemented; the other seven v1 manifests remain discovery slots. Copilot and Cursor have documentation only and are not registry entries.
