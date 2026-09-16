# Adapter compatibility and design review

Status: **Shared framework implemented; no native adapter has been implemented or passed native tests.** Public sources checked on 2026-09-14 (America/New_York). Source links and detailed native mappings are in each adapter spec. Documentation can describe a newer release than the user's installed binary; detection must select verified behavior.

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

“Separate” means the tool does not implicitly copy sessions, skills, plugins or OAuth into the provider profile. “Shared” means native personal state remains visible; the overlay only pins managed provider/model settings. These are configuration strategies, not sandbox boundaries.

## Protocol targets

`Target` means required implementation target subject to native testing. `Conditional` means enable only once a compatible native protocol/SDK has been verified. `No` means no direct v1 mapping.

| Adapter | Anthropic Messages | OpenAI Chat | OpenAI Responses | Google GenAI |
| --- | --- | --- | --- | --- |
| Claude Code | Target | No | No | No |
| Codex | No | Conditional | Target | No |
| Pi | Target | Target | Target | Conditional |
| DeepSeek Harness | Conditional | Target | Conditional | Conditional |
| Kimi Code | Target | Target | Target | Target |
| OpenCode | Target | Target | Target | Target |
| Hermes Agent | Conditional | Target | Conditional | Conditional |
| OpenClaw | Target | Target | Target | Target |

Provider brand alone never establishes protocol compatibility. A multi-protocol gateway can use explicit per-harness overrides. The tool does not supply a proxy or convert requests.

## Specific implementation gates

- **Codex:** recognize separate-file versus legacy inline profiles; never install inline profiles by changing the default file without permission.
- **Kimi:** distinguish current home/credential behavior from legacy CLI versions; require native model context metadata.
- **DeepSeek:** pin provider settings schema, saved-selection precedence, patch row IDs and profile bootstrap; treat tagged YAML as data, never execute it.
- **Hermes:** pin the custom-provider model/endpoint/auth schema and native dotenv semantics.
- **OpenCode:** verify SDK wire protocol and overlay precedence against project/managed settings.
- **OpenClaw:** verify secret references, alias keys, gateway/state isolation and distinct ports.
- **Claude/Pi:** verify auth precedence and role/model selection against the installed release.

Every claimed adapter must pass the shared default-protection, concurrent-provider, secret-rotation, preservation and failure-recovery tests in the overall spec. Tests against fixtures alone do not prove compatibility with an installed release; isolated native smoke checks are also required. No real credentials or paid inference are needed for schema/launch tests.

## Review decisions

The draft proposes:

- Python as the implementation language and macOS/Linux as the first platforms.
- Exactly three named model roles per provider; daily as wrapper default.
- Explicit role selection where the harness lacks native three-tier routing.
- Profile-only synchronization by default, with independent authorization for default writes.
- One private source of API keys, plus necessary generated copies.
- Command-triggered synchronization, documented manual shell setup and conservative handling of existing commands.
- All eight adapters required before claiming v1 support; no placeholder adapters counted as finished.

## Revised launch and model contract (2026-09-15)

No watcher, daemon, polling or `enabled` settings. Sync targets detected harnesses (or explicit `--harness` selections); each managed launch refreshes its own configuration first. Original bare commands remain intact and require a prior sync or the explicit managed launcher.

`name` is a label; `id` is provider-local and defaults to `name`. Adapters consume the resolved ID and translate only native configuration/selector syntax. A per-harness `id` override supports an explicitly different gateway route. No universal model-name translation catalog is maintained. See the overall spec's model identity section for primary-source evidence and required request-level verification.

Adapter authors should follow the implemented [framework contract and handoff guide](adapter-development.md). The eight manifests are discovery slots, not native implementations.
