import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _seconds(value: str) -> int:
    match = re.fullmatch(r"(\d+)([sm]?)", value.strip())
    if not match:
        raise AssertionError(f"Unsupported timeout value: {value!r}")
    amount = int(match.group(1))
    return amount * 60 if match.group(2) == "m" else amount


class SyncServerTimeoutTests(unittest.TestCase):
    def test_gunicorn_allows_large_excel_sync_to_finish(self):
        service = (ROOT / "deploy" / "gunicorn.service").read_text(encoding="utf-8")
        worker_timeout = re.search(r"(?:^|\s)--timeout\s+(\d+)", service)
        graceful_timeout = re.search(r"(?:^|\s)--graceful-timeout\s+(\d+)", service)

        self.assertIsNotNone(worker_timeout)
        self.assertIsNotNone(graceful_timeout)
        self.assertGreaterEqual(int(worker_timeout.group(1)), 180)
        self.assertGreaterEqual(int(graceful_timeout.group(1)), 180)

    def test_nginx_waits_longer_than_gunicorn_for_sync_response(self):
        service = (ROOT / "deploy" / "gunicorn.service").read_text(encoding="utf-8")
        worker_timeout = int(re.search(r"(?:^|\s)--timeout\s+(\d+)", service).group(1))

        for filename in ("nginx-akvilon-peredacha.conf", "nginx.conf"):
            with self.subTest(filename=filename):
                config = (ROOT / "deploy" / filename).read_text(encoding="utf-8")
                read_timeout = re.search(r"proxy_read_timeout\s+([^;]+);", config)
                send_timeout = re.search(r"proxy_send_timeout\s+([^;]+);", config)

                self.assertIsNotNone(read_timeout)
                self.assertIsNotNone(send_timeout)
                self.assertGreater(_seconds(read_timeout.group(1)), worker_timeout)
                self.assertGreater(_seconds(send_timeout.group(1)), worker_timeout)


if __name__ == "__main__":
    unittest.main()
