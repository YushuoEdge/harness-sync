# DeepSeek Harness adapter

Implemented for **dsh 0.1.2-rc.1** and its bundled profiles. Protocols: OpenAI Chat,
OpenAI Responses and Anthropic Messages. Google is not supported by this native build.

```yaml
harnesses:
  deepseek-harness:
    options: {base_profile: headless}
```

```sh
harness-sync sync --harness deepseek-harness
harness-sync run deepseek-harness --provider <alias> --role complex -- "your task"
```

The default template is `web`; managed web launches require an explicit `--port`.
`headless`, `sdk` and `acp` use their native argument grammar. Plugin administration uses the
original `dsh` command. Sync/detection do not start servers, install dependencies or run YAML code.

Each provider/role has a persistent isolated `DSH_HOME`. The tool owns only its settings, bundle
manifest and empty profile patch; sessions and other runtime state persist. Native bundle resolution
uses the installation. Settings explicitly select the role, including the saved-selection namespace,
so roles cannot overwrite one another's active defaults. Auth, memories and plugins are not copied.
Fresh namespaced child credentials take precedence over native stored credentials and dotenv.
Custom headers may create private secret-bearing settings. Model reasoning metadata is rejected
until an explicit effort-map interface is added; supported capacity/input metadata passes through.

Authorized native-default writes merge settings namespaces, preserving YAML comments, unrelated
providers and fields. Executable YAML tags in settings are rejected as data; native bundle tags are
never evaluated by the sync tool. Unknown releases/schema capabilities fail closed.

Version/help and composed-bundle fixtures are included. On 2026-10-01 localhost headless checks
verified all three protocols and roles, exact upstream IDs and fake keys, without dependency
installation or paid inference. See [spec](SPEC.md) and
[native CLI reference](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/reference/README.md).
