import importlib.util
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(os.environ.get("BOREION_CENTRAL_TEMPLATE_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("reader_probe", ROOT / "scripts/check-access.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

class ReaderProbeTests(unittest.TestCase):
    def api(self, source=True, owner=338504245, workflows=True):
        class Fake:
            def request(self, path):
                if path.startswith("/installation/repositories?"):
                    return {"repositories": [{"id": 12, "private": True, "full_name": "chhaukas/hidden", "owner": {"id": owner, "login": "chhaukas"}}] if source else []}
                if path == "/repos/chhaukas/hidden/actions/workflows":
                    return {"workflows": [{"path": ".github/workflows/boreion-build.yml", "state": "active"}] if workflows else []}
                raise AssertionError("Unexpected endpoint or mutation")
        return Fake()

    def test_read_only_probe(self):
        self.assertTrue(probe.check(self.api(), 12))

    def test_unknown_source_rejected(self):
        with self.assertRaises(probe.require.__globals__["Rejected"]):
            probe.check(self.api(source=False), 12)

    def test_foreign_owner_rejected(self):
        with self.assertRaises(probe.require.__globals__["Rejected"]):
            probe.check(self.api(owner=999), 12)

    def test_missing_workflow_reports_pending(self):
        self.assertFalse(probe.check(self.api(workflows=False), 12))
