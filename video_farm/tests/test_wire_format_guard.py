"""Offline regression for costly Flow wire-format mismatches."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from video_farm.models import Profile, Task
from video_farm.scheduler import classify_failure
from video_farm.worker import VideoWorker


class WireFormatGuardTests(TestCase):
    def test_wire_format_failure_is_terminal_not_quota_or_retry(self):
        for code, logs in (
            ("WIRE_FORMAT_MISMATCH", ""),
            ("EXIT_7", '"class": "WireFormatError"; expected interpolation; credits'),
        ):
            with self.subTest(code=code):
                category, _, cooldown, retry = classify_failure(code, "Process exited", logs)
                self.assertEqual(category, "WIRE_FORMAT_MISMATCH")
                self.assertEqual(cooldown, 0)
                self.assertFalse(retry)

    def test_quality_request_remains_quality_and_failure_is_terminal(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            start = root / "start.png"
            end = root / "end.png"
            start.write_bytes(b"test")
            end.write_bytes(b"test")
            task = Task(
                id="test-wire-guard", prompt="safe test", project_id="test-project",
                start_image_path=str(start), end_image_path=str(end), model="veo-quality",
            )
            profile = Profile(id="test-profile", name="test-profile")
            commands = []

            class FakeProcess:
                pid = 123
                returncode = 7
                def poll(self):
                    return self.returncode
                def cleanup(self):
                    return True
                def is_alive(self):
                    return False
                def wait(self, timeout=None):
                    return self.returncode

            def fake_popen(cmd, **kwargs):
                commands.append(cmd)
                kwargs["stdout"].write(b'{"error":{"class":"WireFormatError"}}')
                kwargs["stdout"].flush()
                return FakeProcess()

            worker = VideoWorker(gflow_dir=root, output_dir=root / "outputs")
            with patch.object(worker, "_ensure_profile_marker"), patch(
                "video_farm.worker.VideoWorker._launch_cli", side_effect=fake_popen
            ):
                result = worker.execute_task(task, profile)
            cmd = commands[0]
            self.assertEqual(cmd[cmd.index("--model") + 1], "veo-quality")
            self.assertEqual(cmd[cmd.index("--end-frame") + 1], str(end))
            self.assertEqual(result["error_code"], "WIRE_FORMAT_MISMATCH")
            self.assertFalse(result["success"])

    def test_status_4_classified_as_transient_server_error_without_consuming_retry(self):
        logs = '{"rpc": "jwpduf", "status": 4, "bytes": null, "event": "migrated.status"}\n{"error_message": "migrated host reported status 4", "generation_status": "MEDIA_GENERATION_STATUS_FAILED"}'
        category, msg, cooldown, retry = classify_failure("EXIT_1", "Process exited with code 1", logs)
        self.assertEqual(category, "TRANSIENT_SERVER_ERROR")
        self.assertEqual(cooldown, 20)
        self.assertFalse(retry)
