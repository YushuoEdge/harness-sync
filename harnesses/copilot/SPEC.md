# GitHub Copilot CLI adapter specification

Status: **Native design pending implementation; shared framework ready.** Proposed adapter ID: `copilot`. Native command: `copilot`.

This is an additional candidate outside the currently approved eight-adapter v1 implementation set. The [overall specification](../../SPEC.md) governs secrets, ownership, transactions, selection and default-write permission, but implementation still requires separate approval. Native facts below were checked against official GitHub documentation on 2026-09-15 (America/New_York); no installed release has been validated. This directory deliberately contains no manifest or adapter code, so the packaged registry does not advertise this harness.

## Native interface and evidence

GitHub Copilot CLI supports a documented BYOK mode configured through environment variables. The required routing inputs are `COPILOT_PROVIDER_BASE_URL` and `COPILOT_MODEL`; supported provider types are `openai`, `azure` and `anthropic`. `openai` means an OpenAI Chat Completions-compatible endpoint. Optional variables include API-key or bearer-token authentication, wire protocol/model overrides, Azure API version and prompt/output token limits. Models must support streaming and tool calling. [Using your own LLM models in GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-byok-models).

The executable is `copilot`; `--model` selects a model for one invocation. A persistent hosted-model selection can be stored in `~/.copilot/settings.json` or `$COPILOT_HOME/settings.json`, but environment and command-line model choices take precedence. A custom agent can itself specify a model and has higher precedence than `--model`. [Programmatic reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-programmatic-reference). Installation is available through npm or Homebrew. [CLI quickstart](https://docs.github.com/en/copilot/get-started/cli-quickstart).

BYOK can run without GitHub authentication. GitHub-hosted features still require it, and `COPILOT_OFFLINE=true` suppresses GitHub communication only when explicitly requested; a remote configured provider still receives prompts and code. [Authenticating GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/authenticate-copilot-cli).

## Adapter design

- Detect `copilot`, obtain its version through a bounded noninteractive probe, and inspect `copilot help providers` for the exact BYOK capability. Finding the executable alone is not support. Unknown or pre-BYOK interfaces are `unsupported-version`; detection must not log in, update the CLI, initialize settings or invoke a model.
- Implement launch-time profiles without a native provider file. For the selected provider and role, set a complete child-scoped environment: `COPILOT_PROVIDER_BASE_URL`, `COPILOT_PROVIDER_TYPE`, `COPILOT_PROVIDER_API_KEY` or `COPILOT_PROVIDER_BEARER_TOKEN`, and `COPILOT_MODEL`. Set optional wire/model/token variables only from validated canonical fields or typed adapter options.
- Before applying the selected overlay, unset every adapter-owned `COPILOT_PROVIDER_*` routing or credential variable and `COPILOT_MODEL` from the inherited child environment. Do not clear GitHub authentication variables unless a documented conflict is proven. Never place a provider key in argv.
- Map canonical `anthropic` to native provider type `anthropic`. Map canonical `openai-chat` to `openai`. Treat `openai-responses` as incompatible until a tested release proves the exact `COPILOT_PROVIDER_WIRE_API` value and request behavior. There is no direct v1 `google-genai` mapping.
- Support Azure only through an explicit per-harness override with typed options for API version, well-known model ID and wire deployment name. Do not infer Azure from a hostname or treat a deployment name as a universal model ID.
- Use the core's resolved provider-local model ID for `COPILOT_MODEL`. If wire-model remapping is explicitly configured, keep the canonical capability ID and provider-facing wire ID distinct. Preserve punctuation, slashes, case and dated IDs.
- Keep Copilot's normal home, sessions, settings, GitHub login, plugins, skills, custom agents and MCP configuration shared. Do not set `COPILOT_HOME` or create a substitute home merely to route a provider.
- Reject native arguments that can replace the selected provider/model or escape the managed profile. In particular, reject `--model` and initially reject `--agent`, because a custom agent's model can outrank the managed selection. This restriction may be relaxed only after versioned tests prove safe inheritance for agents without their own model.
- Do not enable `COPILOT_OFFLINE` implicitly. A typed harness option may request it, but the plan must explain that remote provider traffic remains network traffic and GitHub-hosted features become unavailable.

No profile artifact is required beyond the common managed wrapper and environment export machinery. The adapter's `profiles()` may therefore return no native files; `launch()` is the authoritative routing boundary. Tests must prove that a provider/role change takes effect on every fresh managed launch.

## Authorized default writes

The initial adapter must return no default artifacts and reject `default.write: true` or `--write-defaults` with an explicit unsupported diagnostic. `~/.copilot/settings.json` can persist a model choice, but the documented custom-provider endpoint and credential interface is environment-based. Writing only `model` would risk pairing it with stale or unrelated inherited provider variables.

The bare `copilot` command remains untouched and uses the user's native environment and settings. A future default design needs a reviewed, atomic way to activate the full endpoint/type/credential/model tuple; approval to edit `settings.json` alone is insufficient.

## Verification and release gates

- Pin supported CLI versions or capability signatures and sanitized outputs for `--version` and `help providers`; verify probes have no native write side effects.
- Use local stub servers to assert the selected provider type, endpoint path, authentication form, wire API, exact model ID, streaming requests and tool-call exchange. No paid inference is required.
- Test all three roles, key rotation, keyless local endpoints, API-key versus bearer-token exclusivity, old conflicting environment variables, two concurrent providers and provider/model IDs containing spaces-forbidden characters, punctuation and slashes as applicable.
- Require or warn on canonical `context_window` below GitHub's documented 128k recommendation, but do not fabricate capacity. Validate optional prompt/output limits and ensure output does not exceed the canonical context window.
- Verify that malformed endpoints, unsupported protocols, missing model IDs, a model without streaming/tool calling, Azure fields on a non-Azure provider and conflicting wire options fail before any write or launch.
- Prove that `--model`, custom-agent model precedence and settings-file model precedence cannot silently defeat role selection. Never claim support for `--agent` until this is demonstrated.
- Confirm that normal Copilot state and GitHub authentication are unchanged, plans/logs/argv contain no secret, and provider secrets exist only in the child environment and the tool's private secret store.

## Command-triggered sync and model identity

Every generated provider command will use the common pre-launch sync contract: refresh this harness/provider, then launch with a complete child-scoped BYOK tuple. There is no background watcher or harness enablement flag. A bare original executable remains unchanged and does not invoke the sync tool.

Consume the core's resolved provider-local model `id` (falling back to `name`), never infer an ID from the display label. Test two providers using the same label but different API IDs, explicit per-harness ID overrides, slash-containing IDs, repeated IDs and wire-model remapping. Model selection must never change endpoint or credentials independently.

## Planned directory ownership

After approval, this directory may add `adapter.json`, `adapter.py`, versioned native fixtures and adapter tests. Harness-specific detection, environment mapping, argument rejection and compatibility checks stay here; shared I/O, wrapper creation and secret handling remain in the core.
