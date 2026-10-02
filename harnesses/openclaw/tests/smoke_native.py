"""Opt-in native validation: temporary state, fake keys, localhost error responses.

Run from the repository root with uv run python <this file> --executable <path>.
Add --gateway to exercise an isolated foreground gateway and authenticated health.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import signal
import socket
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from harness_sync.contracts import DetectionContext, RenderContext
from harness_sync.paths import Paths
from harness_sync.schema import HarnessSettings, Provider
from harness_sync.secrets import SecretStore

native = importlib.import_module("harnesses.openclaw.adapter")


def environment(spec):
    env = {k: v for k, v in os.environ.items() if k not in spec.unset}
    env.update(spec.environment)
    return env


def stop(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        return process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        return process.communicate()


def request_check(executable, spec, root, observed, arrived, expected, key):
    observed.clear()
    arrived.clear()
    process = subprocess.Popen(
        [executable, *spec.argv],
        cwd=root,
        env=environment(spec),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        success = arrived.wait(15)
    finally:
        stdout, stderr = stop(process)
    assert success, (stdout.decode()[-1000:], stderr.decode()[-1000:])
    matching = [r for r in observed if r["model"] == expected or expected in r["path"]]
    assert matching, observed
    assert any(key in " ".join(r["auth"]) for r in matching), matching
    assert all(r["probe"] == "local-header-check" for r in matching), matching


def gateway_check(adapter, provider, context, keys, executable, root):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    data = provider.model_dump(exclude_none=True)
    data["overrides"] = {"openclaw": {"options": {"gateway_port_base": port - 1}}}
    provider = Provider.model_validate(data)
    for artifact in adapter.profiles(provider, context):
        artifact.path.write_bytes(artifact.render(keys))
    spec = adapter.launch(provider, "daily", ("gateway", "run"), context, keys)
    env = environment(spec)
    path = Path(env["OPENCLAW_CONFIG_PATH"])
    original = path.read_bytes()
    process = subprocess.Popen(
        [executable, *spec.argv],
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        for _ in range(30):
            if process.poll() is not None:
                raise AssertionError(process.communicate())
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.5)
        else:
            raise AssertionError("Temporary gateway did not listen")
        health = subprocess.run(
            [executable, "gateway", "health", "--json"],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert health.returncode == 0, (health.stdout, health.stderr)
        assert path.read_bytes() == original, "Native gateway changed managed config"
        print("isolated gateway authentication and unchanged config passed", flush=True)
    finally:
        stop(process)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--gateway", action="store_true")
    args = parser.parse_args()
    observed, arrived = [], threading.Event()
    expected = ""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
            observed.append(
                {
                    "path": self.path,
                    "model": body.get("model"),
                    "auth": [
                        self.headers.get(k, "")
                        for k in ("authorization", "x-api-key", "x-goog-api-key")
                    ],
                    "probe": self.headers.get("x-harness-probe"),
                }
            )
            if body.get("model") == expected or expected in self.path:
                arrived.set()
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                b'{"error":{"message":"local routing test complete",'
                b'"type":"invalid_request_error"}}'
            )

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    adapter = native.create_adapter()
    try:
        for protocol in sorted(adapter.protocols):
            with tempfile.TemporaryDirectory(
                prefix="hs-openclaw-smoke-", ignore_cleanup_errors=True
            ) as directory:
                root = Path(directory).resolve()
                settings = HarnessSettings(executable=str(Path(args.executable).resolve()))
                detected = adapter.detect(
                    DetectionContext(
                        settings,
                        {
                            **os.environ,
                            "OPENCLAW_CONFIG_PATH": str(root / "default.json"),
                            "OPENCLAW_STATE_DIR": str(root / "probe-state"),
                        },
                    )
                )
                assert detected.status == "installed", detected.status
                context = RenderContext(
                    Paths(root / "source.yaml", root / "state"),
                    detected,
                    settings,
                    lambda _: None,
                    lambda _: None,
                )
                provider = Provider.model_validate(
                    {
                        "name": "one",
                        "type": protocol,
                        "base_url": f"http://127.0.0.1:{server.server_port}/v1",
                        "api_key": {"secret": "one"},
                        "headers": {"x-harness-probe": {"secret": "probe"}},
                        "models": [
                            {
                                "name": "same",
                                "id": f"vendor/one-{r}",
                                "role": r,
                                "context_window": 128000,
                                "max_output_tokens": 1024,
                            }
                            for r in native.ROLES
                        ],
                    }
                )
                keys = SecretStore({"one": "local-stub-key", "probe": "local-header-check"})
                adapter.validate(provider, context)
                for artifact in adapter.profiles(provider, context):
                    artifact.path.parent.mkdir(parents=True, exist_ok=True)
                    artifact.path.write_bytes(artifact.render(keys))
                for role in native.ROLES:
                    expected = f"vendor/one-{role}"
                    spec = adapter.launch(
                        provider,
                        role,
                        (
                            "agent",
                            "--local",
                            "--agent",
                            "main",
                            "--message",
                            "say ok",
                        ),
                        context,
                        keys,
                    )
                    validated = subprocess.run(
                        [args.executable, "config", "validate"],
                        cwd=root,
                        env=environment(spec),
                        capture_output=True,
                        timeout=12,
                    )
                    assert validated.returncode == 0, validated.stderr.decode()
                    request_check(
                        args.executable, spec, root, observed, arrived, expected, "local-stub-key"
                    )
                    print(protocol, role, "config and request routing passed", flush=True)
                # Reuse native state/derived catalog after rotating only the source key.
                keys = SecretStore({"one": "rotated-stub-key", "probe": "local-header-check"})
                expected = "vendor/one-daily"
                spec = adapter.launch(
                    provider,
                    "daily",
                    (
                        "agent",
                        "--local",
                        "--agent",
                        "main",
                        "--message",
                        "say ok",
                    ),
                    context,
                    keys,
                )
                request_check(
                    args.executable, spec, root, observed, arrived, expected, "rotated-stub-key"
                )
                print(protocol, "reused state key rotation passed", flush=True)
                if args.gateway and protocol == "openai-chat":
                    gateway_check(adapter, provider, context, keys, args.executable, root)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


if __name__ == "__main__":
    main()
