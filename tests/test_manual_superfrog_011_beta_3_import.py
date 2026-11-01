import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(os.environ.get('BOREION_CENTRAL_TEMPLATE_ROOT', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT/'scripts'))
from central import Rejected
spec=importlib.util.spec_from_file_location('manual_superfrog', ROOT/'scripts/import-superfrog-011-beta-3.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ManualSuperfrogBeta3Tests(unittest.TestCase):
    def fixture(self, root):
        apk=b'explicit local synthetic fixture, never published'
        manifest={'appId':'superfrog','version':'0.1.1-beta.3','metadata':{'sourceVisible':False,'distribution':{'public':True,'signingCertificateSha256':m.CERT}},'apk':{'sha256':hashlib.sha256(apk).hexdigest()}}
        data={'superfrog-0.1.1-beta.3.apk':apk,'boreion-app.json':json.dumps(manifest).encode()}
        for name,value in data.items():(root/name).write_bytes(value)
        return {name:{'size':len(value),'sha256':hashlib.sha256(value).hexdigest()} for name,value in data.items()}

    def test_exact_approved_file_set(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);approved=self.fixture(root)
            with patch.object(m,'APPROVED',approved):
                self.assertEqual(m.files_valid(root)['version'],'0.1.1-beta.3')

    def test_changed_apk_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);approved=self.fixture(root)
            (root/'superfrog-0.1.1-beta.3.apk').write_bytes(b'changed')
            with patch.object(m,'APPROVED',approved),self.assertRaises(Rejected):m.files_valid(root)

    def test_extra_executable_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);approved=self.fixture(root);(root/'producer.py').write_text('never execute')
            with patch.object(m,'APPROVED',approved),self.assertRaises(Rejected):m.files_valid(root)

    def test_only_owner_on_main_and_no_app_secret(self):
        workflow=(ROOT/'.github/workflows/import-superfrog-011-beta-3.yml').read_text()
        self.assertIn("github.actor_id == '338504245'",workflow)
        self.assertIn("github.ref == 'refs/heads/main'",workflow)
        self.assertIn('needs: verify',workflow)
        self.assertNotIn('secrets.',workflow)
        self.assertNotIn('pull_request_target',workflow)
