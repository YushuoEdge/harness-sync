"""Opt-in installed ZCode check; localhost errors and fake keys, no inference.

Run from the repository: PYTHONPATH=.:src python harnesses/zcode/tests/smoke_native.py
"""

from __future__ import annotations

import importlib
import json
import os
import signal
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from harness_sync.contracts import DetectionContext, RenderContext
from harness_sync.paths import Paths
from harness_sync.schema import HarnessSettings, Provider
from harness_sync.secrets import SecretStore

native = importlib.import_module("harnesses.zcode.adapter")


def main():
    received = []
    event = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            received.append(
                {
                    "path": self.path,
                    "model": body.get("model"),
                    "key": self.headers.get("authorization") or self.headers.get("x-api-key"),
                    "header": self.headers.get("x-harness-probe"),
                    "budget": body.get("max_tokens")
                    or body.get("max_completion_tokens")
                    or body.get("max_output_tokens"),
                }
            )
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"local smoke complete"}}')
            event.set()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    adapter = native.create_adapter()
    try:
        with tempfile.TemporaryDirectory(prefix="hs-zcode-smoke-") as directory:
            root = Path(directory)
            settings = HarnessSettings()
            detection = adapter.detect(DetectionContext(settings, dict(os.environ)))
            assert detection.status == "installed", detection
            context = RenderContext(
                Paths(root / "config.yaml", root / "state"),
                detection,
                settings,
                lambda p: p.read_bytes() if p.exists() else None,
                lambda _: None,
            )
            for protocol in native.APIS:
                for name in ("one", "two"):
                    provider = Provider.model_validate(
                        {
                            "name": name,
                            "type": protocol,
                            "base_url": f"http://127.0.0.1:{server.server_port}"
                            + ("" if protocol == "anthropic" else "/v1"),
                            "api_key": {"secret": name},
                            "headers": {"x-harness-probe": {"secret": "header"}},
                            "models": [
                                {
                                    "name": "same label",
                                    "id": "unused-display-route",
                                    "role": role,
                                    "context_window": 64000,
                                    "max_output_tokens": 1024,
                                    "overrides": {"zcode": {"id": f"vendor/{name}${role}"}},
                                }
                                for role in ("simple", "daily", "complex")
                            ],
                        }
                    )
                    adapter.validate(provider, context)
                    for rotated in (False, True):
                        key = f"fake-{name}-{'rotated' if rotated else 'initial'}"
                        secrets = SecretStore({name: key, "header": "fake-header"})
                        for artifact in adapter.profiles(provider, context):
                            content = artifact.render(secrets)
                            artifact.verify(content)
                            artifact.path.parent.mkdir(parents=True, exist_ok=True)
                            artifact.path.write_bytes(content)
                            artifact.path.chmod(artifact.mode)
                        roles = ("daily",) if rotated else ("simple", "daily", "complex")
                        for role in roles:
                            received.clear()
                            event.clear()
                            spec = adapter.launch(
                                provider,
                                role,
                                ("--prompt", "Say hello", "--mode", "plan"),
                                context,
                                secrets,
                            )
                            environment = dict(
                                os.environ,
                                OPENAI_API_KEY="stale-key",
                                ANTHROPIC_API_KEY="stale-key",
                                ZCODE_PERSONAL_PROVIDER_CONFIG_FILE="/missing/stale.json",
                                ZCODE_BUILTIN_PROVIDER_BUNDLED_CONFIG_FILE="/missing/stale.json",
                            )
                            for variable in spec.unset:
                                environment.pop(variable, None)
                            environment.update(spec.environment)
                            child = subprocess.Popen(
                                [str(detection.executable), *spec.argv],
                                env=environment,
                                cwd=root,
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                start_new_session=True,
                            )
                            try:
                                assert event.wait(15), "No localhost model request"
                            finally:
                                try:
                                    os.killpg(child.pid, signal.SIGTERM)
                                except ProcessLookupError:
                                    pass
                                try:
                                    child.communicate(timeout=5)
                                except subprocess.TimeoutExpired:
                                    os.killpg(child.pid, signal.SIGKILL)
                                    child.communicate()
                            expected = {
                                "path": {
                                    "anthropic": "/v1/messages",
                                    "openai-chat": "/v1/chat/completions",
                                    "openai-responses": "/v1/responses",
                                }[protocol],
                                "model": f"vendor/{name}${role}",
                                "key": f"Bearer {key}",
                                "header": "fake-header",
                                "budget": 1024,
                            }
                            assert received and all(row == expected for row in received), received
                            print(protocol, name, role, "rotated" if rotated else "initial", "PASS")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
