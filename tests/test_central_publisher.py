import copy, hashlib, importlib.util, io, json, os, pathlib, stat, subprocess, sys, tempfile, unittest, urllib.error, zipfile
from unittest.mock import patch

ROOT = pathlib.Path(
    os.environ.get(
        "BOREION_CENTRAL_TEMPLATE_ROOT",
        pathlib.Path(__file__).resolve().parents[2] / "templates/central-publisher",
    )
)
spec = importlib.util.spec_from_file_location("central", ROOT / "scripts/central.py")
c = importlib.util.module_from_spec(spec)
sys.modules["central"] = c
spec.loader.exec_module(c)
spec = importlib.util.spec_from_file_location(
    "central_publish", ROOT / "scripts/publish.py"
)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
SHA = "a" * 40
CERT = "b" * 64
SOURCE = {
    "repository": "chhaukas/private-test",
    "repositoryId": 12,
    "ownerId": 10,
    "workflowId": 34,
    "workflowPath": ".github/workflows/boreion-build.yml",
    "branch": "main",
    "actorIds": [10],
    "certificateSha256": CERT,
    "androidPackage": "com.boreion.test",
    "productionApproved": True,
}
POLICY = {"schemaVersion": 1, "centralActorIds": [10], "sources": {"test-app": SOURCE}}
RUN = {
    "id": 56,
    "repository": {"id": 12},
    "head_repository": {"id": 12},
    "workflow_id": 34,
    "path": SOURCE["workflowPath"],
    "status": "completed",
    "conclusion": "success",
    "event": "workflow_dispatch",
    "head_branch": "main",
    "head_sha": SHA,
    "head_commit": {"id": SHA},
    "run_attempt": 1,
    "actor": {"id": 10},
    "triggering_actor": {"id": 10},
    "pull_requests": [],
}
ARTIFACT = {
    "id": 78,
    "name": "boreion--test-app--1.0.0--production",
    "expired": False,
    "size_in_bytes": 100,
    "digest": "sha256:" + "c" * 64,
    "workflow_run": {
        "id": 56,
        "repository_id": 12,
        "head_repository_id": 12,
        "head_sha": SHA,
        "head_branch": "main",
    },
}


class FakeAPI:
    def __init__(self, run=None, artifact=None):
        self.run = copy.deepcopy(RUN if run is None else run)
        self.artifact = copy.deepcopy(ARTIFACT if artifact is None else artifact)
        self.calls = []

    def request(self, path, *args):
        self.calls.append((path, args))
        if path == "/repos/chhaukas/private-test":
            return {
                "id": 12,
                "full_name": SOURCE["repository"],
                "owner": {"id": 10},
                "private": True,
                "fork": False,
            }
        if path.endswith("/workflows/34"):
            return {"path": SOURCE["workflowPath"], "state": "active"}
        if path.endswith("/runs/56"):
            return self.run
        if "/artifacts?" in path:
            return {"total_count": 1, "artifacts": [self.artifact]}
        if path.endswith("/branches/main"):
            return {"protected": True}
        if "/environments/" in path:
            return {
                "protection_rules": [
                    {
                        "type": "required_reviewers",
                        "reviewers": [{"reviewer": {"id": 10}}],
                    }
                ],
                "deployment_branch_policy": {
                    "protected_branches": True,
                    "custom_branch_policies": False,
                },
            }
        raise AssertionError("Unexpected mock endpoint")


def make_bundle(root):
    root.mkdir()
    data = b"local test data, never a production Android artifact"
    (root / "test-app-1.0.0.apk").write_bytes(data)
    manifest = {
        "schemaVersion": 1,
        "appId": "test-app",
        "version": "1.0.0",
        "metadata": {
            "name": "Test app",
            "sourceVisible": False,
            "privateSource": "do-not-export",
            "distribution": {"public": True, "signingCertificateSha256": CERT},
        },
        "apk": {
            "assetName": "test-app-1.0.0.apk",
            "sha256": hashlib.sha256(data).hexdigest(),
        },
    }
    (root / "boreion-app.json").write_text(json.dumps(manifest))
    (root / "tag.txt").write_text("test-app/v1.0.0")
    (root / "release-notes.txt").write_text("Untrusted notes ignored")
    request = {
        "schemaVersion": 1,
        "repositoryId": 12,
        "runId": 56,
        "runAttempt": 1,
        "commit": SHA,
        "actorId": 10,
        "appId": "test-app",
        "version": "1.0.0",
        "channel": "production",
    }
    (root / "request.json").write_text(json.dumps(request))
    return manifest, request


class CentralTests(unittest.TestCase):
    def test_policy_is_closed_and_stable_numeric_ids_required(self):
        self.assertEqual(
            c.load_policy(json.dumps(POLICY))["sources"]["test-app"]["repositoryId"], 12
        )
        for key, value in [
            ("repositoryId", 0),
            ("repository", "other/unknown"),
            ("workflowPath", ".github/workflows/evil.yml"),
            ("certificateSha256", "bad"),
        ]:
            policy = copy.deepcopy(POLICY)
            policy["sources"]["test-app"][key] = value
            with self.assertRaises(c.Rejected):
                c.load_policy(json.dumps(policy))

    def test_central_actor_event_ref_and_rerun_actor(self):
        c.verify_context(POLICY, 10, 10, "workflow_dispatch", "refs/heads/main", c.REPO)
        for args in [
            (11, 10, "workflow_dispatch", "refs/heads/main", c.REPO),
            (10, 11, "workflow_dispatch", "refs/heads/main", c.REPO),
            (10, 10, "pull_request_target", "refs/heads/main", c.REPO),
            (10, 10, "workflow_dispatch", "refs/heads/feature", c.REPO),
            (c.BOT, c.BOT, "schedule", "refs/heads/main", c.REPO),
        ]:
            with self.assertRaises(c.Rejected):
                c.verify_context(POLICY, *args)

    def test_source_run_binding_and_workflow_status(self):
        self.assertEqual(c.source_run(FakeAPI(), SOURCE, 56)["head_sha"], SHA)
        for key, value in [
            ("conclusion", "failure"),
            ("event", "pull_request"),
            ("head_branch", "feature"),
            ("workflow_id", 99),
            ("head_repository", {"id": 999}),
            ("actor", {"id": 999}),
            ("triggering_actor", {"id": 999}),
            ("head_commit", {"id": "f" * 40}),
        ]:
            run = copy.deepcopy(RUN)
            run[key] = value
            with self.assertRaises(c.Rejected):
                c.source_run(FakeAPI(run=run), SOURCE, 56)

    def test_artifact_identity_digest_and_source_binding(self):
        self.assertEqual(
            c.find_artifact(FakeAPI(), SOURCE, RUN, "test-app", "production")["id"], 78
        )
        for key, value in [
            ("expired", True),
            ("digest", None),
            ("workflow_run", {"id": 999}),
            ("name", "boreion--unknown--1.0.0--production"),
        ]:
            artifact = copy.deepcopy(ARTIFACT)
            artifact[key] = value
            with self.assertRaises(c.Rejected):
                c.find_artifact(
                    FakeAPI(artifact=artifact), SOURCE, RUN, "test-app", "production"
                )

    def test_production_gate_missing_reviewers_fails_closed(self):
        c.require_production_gate(FakeAPI(), "production")
        for env in [
            None,
            {},
            {"protection_rules": [{"type": "required_reviewers", "reviewers": []}]},
        ]:
            api = FakeAPI()
            api.request = lambda _: env
            with self.assertRaises(c.Rejected):
                c.require_production_gate(api, "production")

    def test_outer_zip_traversal_duplicates_symlinks_and_extra_code_rejected(self):
        for names in [["../escape"], ["/absolute"], ["ok", "ok"]]:
            with tempfile.TemporaryDirectory() as d:
                archive = pathlib.Path(d) / "in.zip"
                with zipfile.ZipFile(archive, "w") as z:
                    for name in names:
                        z.writestr(name, "test")
                with self.assertRaises(c.Rejected):
                    c.safe_extract(archive, pathlib.Path(d) / "out")
        with tempfile.TemporaryDirectory() as d:
            archive = pathlib.Path(d) / "in.zip"
            with zipfile.ZipFile(archive, "w") as z:
                i = zipfile.ZipInfo("link")
                i.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(i, "/etc/passwd")
            with self.assertRaises(c.Rejected):
                c.safe_extract(archive, pathlib.Path(d) / "out")

    def test_provenance_commit_attempt_actor_and_app_are_bound(self):
        with tempfile.TemporaryDirectory() as d:
            _, request = make_bundle(pathlib.Path(d) / "in")
            c.verify_provenance(request, SOURCE, RUN, "test-app", "1.0.0", "production")
            for key, value in [
                ("commit", "d" * 40),
                ("runAttempt", 2),
                ("repositoryId", 999),
                ("appId", "other"),
                ("actorId", 999),
            ]:
                changed = {**request, key: value}
                with self.assertRaises(c.Rejected):
                    c.verify_provenance(
                        changed, SOURCE, RUN, "test-app", "1.0.0", "production"
                    )

    def test_sandbox_has_no_network_or_secrets_and_signature_and_package_are_checked(
        self,
    ):
        image = (ROOT / "verifier-image.txt").read_text().strip()
        commands = []

        def execute(argv, **kwargs):
            commands.append(argv)
            output = (
                "Signer #1 certificate SHA-256 digest: " + CERT
                if "/tools/aapt" not in argv
                else "package: name='com.boreion.test' versionCode='1' versionName='1.0.0'"
            )
            return subprocess.CompletedProcess(argv, 0, output, "")

        c.verify_apk("/tmp/input.apk", SOURCE, "1.0.0", image, "/tmp/tools", execute)
        for argv in commands:
            self.assertIn("none", argv)
            self.assertIn("--read-only", argv)
            self.assertIn("--cap-drop=ALL", argv)
            self.assertGreater(
                int(
                    next(a for a in argv if a.startswith("--user="))
                    .split("=")[1]
                    .split(":")[0]
                ),
                0,
            )
            self.assertNotIn("GH_TOKEN", " ".join(argv))
            self.assertFalse(
                any(
                    "/var/run/docker.sock" in arg
                    for index, arg in enumerate(argv)
                    if index > 0 and argv[index - 1] == "--mount"
                )
            )
        with self.assertRaises(c.Rejected):
            c.verify_apk(
                "/tmp/input.apk",
                {**SOURCE, "certificateSha256": "c" * 64},
                "1.0.0",
                image,
                "/tmp/tools",
                execute,
            )
        with self.assertRaises(c.Rejected):
            c.verify_apk(
                "/tmp/input.apk", SOURCE, "2.0.0", image, "/tmp/tools", execute
            )

    def test_sanitization_preserves_release_format_but_never_private_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d) / "in"
            make_bundle(root)
            with patch.object(c, "verify_apk"):
                result = c.sanitize_bundle(
                    root,
                    pathlib.Path(d) / "out",
                    SOURCE,
                    RUN,
                    "test-app",
                    "production",
                    "image",
                    "tools",
                )
            self.assertEqual(result["version"], "1.0.0")
            out = pathlib.Path(d) / "out"
            self.assertFalse((out / "request.json").exists())
            self.assertNotIn("do-not-export", (out / "release-notes.txt").read_text())
            self.assertNotIn("Untrusted notes", (out / "release-notes.txt").read_text())
            m = json.loads((out / "boreion-app.json").read_text())
            self.assertEqual(m["schemaVersion"], 1)
            self.assertEqual(m["appId"], "test-app")
            self.assertEqual(m["apk"]["sha256"], result["sha256"])

    def test_unexpected_files_and_tampered_apk_are_rejected_before_signature_parser(
        self,
    ):
        for kind in ["extra", "hash"]:
            with tempfile.TemporaryDirectory() as d:
                root = pathlib.Path(d) / "in"
                make_bundle(root)
                if kind == "extra":
                    (root / "run-me.py").write_text("untrusted producer code")
                else:
                    (root / "test-app-1.0.0.apk").write_bytes(b"changed")
                with patch.object(c, "verify_apk") as verifier:
                    with self.assertRaises(c.Rejected):
                        c.sanitize_bundle(
                            root,
                            pathlib.Path(d) / "out",
                            SOURCE,
                            RUN,
                            "test-app",
                            "production",
                            "image",
                            "tools",
                        )
                    verifier.assert_not_called()

    def test_signed_storage_redirect_never_receives_github_authorization(self):
        payload = b"zip unit fixture"
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        calls = []

        class Opener:
            def open(self, request, timeout):
                calls.append(request)
                if isinstance(request, str):
                    return io.BytesIO(payload)
                raise urllib.error.HTTPError(
                    request.full_url,
                    302,
                    "redirect",
                    {
                        "Location": "https://production.blob.core.windows.net/file?sig=test"
                    },
                    None,
                )

        with tempfile.TemporaryDirectory() as d, patch.object(
            c.urllib.request, "build_opener", return_value=Opener()
        ):
            c.API("test-only-token").download(
                "/repos/test/source/actions/artifacts/1/zip",
                pathlib.Path(d) / "zip",
                digest,
            )
            self.assertEqual(
                calls[0].get_header("Authorization"), "Bearer test-only-token"
            )
            self.assertIsInstance(calls[1], str)
            with self.assertRaises(c.Rejected):
                c.API("test-only-token").download(
                    "/repos/test/source/actions/artifacts/1/zip",
                    pathlib.Path(d) / "bad",
                    "sha256:" + "f" * 64,
                )

    def test_no_app_credentials_or_publish_permissions_in_private_template(self):
        workflow = (
            (
                ROOT.parent / "private-android/.github/workflows/boreion-build.yml"
                if (ROOT.parent / "private-android").exists()
                else ROOT
                / "project-template/private-android/.github/workflows/boreion-build.yml"
            )
        ).read_text()
        for text in [
            "APP_PRIVATE_KEY",
            "READER_APP",
            "create-github-app-token",
            "contents: write",
            "secrets: inherit",
        ]:
            self.assertNotIn(text, workflow)
        self.assertRegex(workflow, r"actions/upload-artifact@[a-f0-9]{40}")
        self.assertIn("request.json", workflow)


class CentralAdditionalTests(unittest.TestCase):
    def test_plan_rejects_unknown_apps_and_unapproved_first_production(self):
        for app, approved in [("unknown", True), ("test-app", False)]:
            policy = copy.deepcopy(POLICY)
            policy["sources"]["test-app"]["productionApproved"] = approved
            with patch.dict(
                os.environ,
                {"BOREION_SOURCE_POLICY": json.dumps(policy), "GH_TOKEN": "unit-test"},
            ), patch.object(
                sys,
                "argv",
                [
                    "central.py",
                    "plan",
                    "--app",
                    app,
                    "--run",
                    "56",
                    "--channel",
                    "production",
                ],
            ), patch.object(
                c, "context"
            ), patch.object(
                c.API, "request"
            ) as requests:
                with self.assertRaises(c.Rejected):
                    c.main()
                requests.assert_not_called()

    def test_scanner_uses_reader_only_for_sources_and_deduplicates_dispatches(self):
        class Reader(FakeAPI):
            def request(self, path, *args):
                if "/workflows/34/runs?" in path:
                    return {"workflow_runs": [RUN]}
                return super().request(path, *args)

        class Control(FakeAPI):
            def __init__(self):
                super().__init__()
                self.history = []
                self.dispatches = 0

            def request(self, path, *args):
                self.assert_public(path)
                if "/central-publish.yml/runs?" in path:
                    return {"workflow_runs": self.history}
                if "/releases/tags/" in path:
                    return None
                if path.endswith("/dispatches"):
                    self.dispatches += 1
                    self.history = [{"display_title": "Publish test-app / run 56"}]
                    return None
                return super().request(path, *args)

            def assert_public(self, path):
                if "private-test" in path:
                    raise AssertionError("Central writer token used for private source")

        control = Control()
        reader = Reader()
        c.scan(control, reader, POLICY)
        c.scan(control, reader, POLICY)
        self.assertEqual(control.dispatches, 1)

    def test_existing_tag_cannot_be_overwritten_and_publish_job_only_uploads_verified_data(
        self,
    ):
        class Writer:
            token = "unit-test-only"

            def __init__(self):
                self.ref = None
                self.calls = []

            def request(self, path, method="GET", data=None):
                self.calls.append((path, method, data))
                if path.endswith("/git/refs"):
                    if self.ref:
                        raise c.Rejected("Duplicate tag")
                    self.ref = data["ref"]
                    return {"ref": self.ref, "object": {"sha": data["sha"]}}
                if path.endswith("/releases"):
                    return {"id": 123, "draft": True, "tag_name": "test-app/v1.0.0"}
                if path.endswith("/releases/123"):
                    return {"id": 123, "draft": False, "tag_name": "test-app/v1.0.0"}
                raise AssertionError("Unexpected write operation")

        class Upload:
            def open(self, request, timeout):
                self.assert_destination(request.full_url)
                name = c.urllib.parse.parse_qs(
                    c.urllib.parse.urlparse(request.full_url).query
                )["name"][0]
                return io.BytesIO(
                    json.dumps(
                        {
                            "name": name,
                            "size": len(request.data),
                            "state": "uploaded",
                            "digest": "sha256:"
                            + hashlib.sha256(request.data).hexdigest(),
                        }
                    ).encode()
                )

            def assert_destination(self, url):
                if not url.startswith(
                    "https://uploads.github.com/repos/"
                    + c.REPO
                    + "/releases/123/assets?"
                ):
                    raise AssertionError("Incorrect upload scope")

        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d) / "in"
            make_bundle(root)
            out = pathlib.Path(d) / "out"
            with patch.object(c, "verify_apk"):
                c.sanitize_bundle(
                    root, out, SOURCE, RUN, "test-app", "production", "image", "tools"
                )
            writer = Writer()
            with patch.dict(os.environ, {"GITHUB_SHA": SHA}), patch.object(
                c.urllib.request, "build_opener", return_value=Upload()
            ):
                p.publish(writer, out, "test-app", "production", CERT)
                self.assertEqual(writer.calls[-1][1], "PATCH")
                with self.assertRaises(c.Rejected):
                    p.publish(writer, out, "test-app", "production", CERT)
                self.assertEqual(
                    sum(path.endswith("/releases") for path, _, _ in writer.calls), 1
                )

    def test_unexpected_redirect_target_is_rejected_before_credentials_or_bytes_leave_github(
        self,
    ):
        class Opener:
            def open(self, request, timeout):
                raise urllib.error.HTTPError(
                    request.full_url,
                    302,
                    "redirect",
                    {"Location": "https://evil.example/artifact"},
                    None,
                )

        with tempfile.TemporaryDirectory() as d, patch.object(
            c.urllib.request, "build_opener", return_value=Opener()
        ):
            with self.assertRaises(c.Rejected):
                c.API("unit-test").download(
                    "/repos/x/y/actions/artifacts/1/zip",
                    pathlib.Path(d) / "out",
                    "sha256:" + "a" * 64,
                )


if __name__ == "__main__":
    unittest.main()
