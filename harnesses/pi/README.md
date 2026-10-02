# Pi adapter

Implemented for **Pi coding agent 1.0.0**. Other versions and unrelated `pi` executables fail closed.
Supports Anthropic Messages, OpenAI Chat, OpenAI Responses and Google Generative AI.

```sh
harness-sync sync --harness pi
harness-sync run pi --provider <alias> --role complex -- -p "your prompt"
```

Profiles manage `models.json` and `settings.json` in a stable, isolated `PI_CODING_AGENT_DIR`.
Sessions persist there; personal sessions, skills, extensions and OAuth are not copied. Launch
pins provider and exact model, disables extensions that could replace routing, and loads fresh
namespaced credentials. Stored auth for the managed provider is rejected because Pi gives it
precedence over the catalog key. Extra provider/model/key and extension flags are rejected.

Model metadata is passed when supplied; omitted limits retain native defaults. Repeated IDs are
deduplicated and conflicting metadata fails. Custom headers support escaped static values and
secret environment references. Keyless auth is rejected; no dummy credentials are invented.
Default writes merge only managed catalogs/default selection and preserve unrelated providers
and auth stores. Bare Pi requires the generated environment exports for managed default keys.

Version/help fixtures, native-source review and tests verify the schema and protection rules.
On 2026-10-01 a localhost request stub verified all four protocols and all three roles with exact
IDs and fake credentials. Anthropic base URLs normally omit `/v1` because its SDK appends it;
Chat/Responses endpoints normally include `/v1`. Google appends `models/<id>:streamGenerateContent`.
See [spec](SPEC.md) and [native custom-model documentation](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/models.md).

## 2026-10-02 release validation

Updated the installed harness to **1.0.0** and refreshed the pinned version/help fixtures.
All supported protocols and all three roles passed localhost error-response routing checks
with slash-containing model IDs and fake API keys. These checks prove endpoint, outbound model
ID and credential routing; they do not exercise paid inference. Adapter unit tests passed.
Native user defaults and authentication files were untouched.
