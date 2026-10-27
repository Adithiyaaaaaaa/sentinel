"""No host test execution: a fixed command in an explicitly configured local container."""

import os
import re
import shutil
import subprocess
import threading
import uuid


class SandboxError(ValueError):
    pass


class DockerSandbox:
    def __init__(self, settings):
        self.settings = settings

    def command(self):
        executable = shutil.which("docker")
        if not executable or not self.settings.sandbox_image:
            raise SandboxError(
                "Sandbox unavailable. Install Docker and configure a local pinned pytest image. No host tests were run."
            )
        endpoint = "npipe:////./pipe/docker_engine" if os.name == "nt" else "unix:///var/run/docker.sock"
        return [executable, "--host", endpoint]

    def availability(self):
        try:
            command = self.command()
            result = subprocess.run(
                command + ["image", "inspect", "--format", "{{.Os}}", self.settings.sandbox_image],
                capture_output=True,
                timeout=5,
                check=False,
            )
            if result.returncode or result.stdout.strip() != b"linux":
                raise SandboxError(
                    "The configured Linux sandbox image is not available in local Docker. No images are downloaded automatically."
                )
            return {"available": True, "image": self.settings.sandbox_image, "error": None}
        except (OSError, subprocess.TimeoutExpired, SandboxError) as exc:
            return {
                "available": False,
                "image": self.settings.sandbox_image,
                "error": str(exc) if isinstance(exc, SandboxError) else "Local Docker is unavailable.",
            }

    def run(self, repository, generated):
        status = self.availability()
        if not status["available"]:
            raise SandboxError(status["error"])
        base = self.command()
        name = "sentinel-test-" + uuid.uuid4().hex
        paths = ["/generated/sentinel_generated_test.py"]
        if (repository / "tests").is_dir():
            paths.append("/workspace/tests")
        args = base + [
            "run",
            "--rm",
            "--pull=never",
            "--name",
            name,
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user=65534:65534",
            "--pids-limit=64",
            "--memory=512m",
            "--memory-swap=512m",
            "--cpus=1",
            "--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=64m",
            "--workdir=/workspace",
            "--mount",
            f"type=bind,source={repository},target=/workspace,readonly",
            "--mount",
            f"type=bind,source={generated},target=/generated,readonly",
            "--env=PYTHONDONTWRITEBYTECODE=1",
            "--env=PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
            "--env=PYTHONPATH=/workspace",
            "--env=HOME=/tmp",
            "--env=PYTEST_ADDOPTS=",
            "--entrypoint=python",
            self.settings.sandbox_image,
            "-m",
            "pytest",
            "-c",
            "/dev/null",
            "-p",
            "no:cacheprovider",
            "--override-ini=addopts=",
            "-q",
            "--tb=no",
            *paths,
        ]
        output = bytearray()
        exceeded = threading.Event()
        process = None
        try:
            process = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL
            )

            def drain():
                while chunk := process.stdout.read(4096):
                    remaining = 128000 - len(output)
                    output.extend(chunk[: max(0, remaining)])
                    if len(chunk) > remaining:
                        exceeded.set()
                        process.kill()
                        break

            reader = threading.Thread(target=drain, daemon=True)
            reader.start()
            try:
                code = process.wait(timeout=self.settings.sandbox_timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                raise SandboxError(
                    "Sandbox timed out. The staged change was discarded; repository files were not modified."
                ) from None
            reader.join(timeout=5)
            if exceeded.is_set():
                raise SandboxError("Sandbox output exceeded its limit. Repository files were not modified.")
            summary = output.decode("utf-8", errors="replace")
            summary = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", summary)
            summary = "".join(c for c in summary if c in "\n\t" or ord(c) >= 32)
            counts = {
                key: sum(int(n) for n in re.findall(rf"\b(\d+) {key}\b", summary))
                for key in ("passed", "failed", "error", "skipped")
            }
            return {
                "exit_code": code,
                "passed": code == 0 and counts["passed"] > 0,
                "reported_counts": counts,
                "output": summary[-8000:],
                "output_truncated": len(summary) > 8000,
                "coverage_delta": None,
                "scope": "Generated pytest tests plus indexed tests/ directory. Counts are process-reported, not independent correctness proof.",
                "image": self.settings.sandbox_image,
            }
        except OSError:
            raise SandboxError("Unable to launch the local Docker sandbox. No host tests were run.") from None
        finally:
            if process and process.poll() is None:
                process.kill()
            try:
                subprocess.run(
                    base + ["rm", "--force", name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
