#!/usr/bin/env python3
"""Trusted central controller. No private source checkout or producer code execution."""

import argparse, hashlib, importlib.util, json, os, pathlib, re, stat, subprocess, sys, tempfile, urllib.error, urllib.parse, urllib.request, zipfile

REPO = "chhaukas/boreion-app-releases"
BOT = 41898282
MAX_ZIP = 250 * 1024 * 1024
VERSION = r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-beta\.(?:0|[1-9]\d*))?"
APP = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"


class Rejected(Exception):
    pass


def require(ok, message="Publication request rejected"):
    if not ok:
        raise Rejected(message)


def positive(n):
    return type(n) is int and n > 0


def load_policy(value):
    p = json.loads(value)
    require(
        p.get("schemaVersion") == 1 and isinstance(p.get("sources"), dict),
        "Central policy is not configured",
    )
    require(
        isinstance(p.get("centralActorIds"), list)
        and all(positive(i) and i != BOT for i in p["centralActorIds"])
    )
    for app, s in p["sources"].items():
        require(re.fullmatch(APP, app) and len(app) <= 80)
        require(re.fullmatch(r"chhaukas/[A-Za-z0-9_.-]+", s.get("repository", "")))
        require(
            all(positive(s.get(k)) for k in ["repositoryId", "ownerId", "workflowId"])
        )
        require(
            s.get("workflowPath") == ".github/workflows/boreion-build.yml"
            and s.get("branch") == "main"
        )
        require(
            isinstance(s.get("actorIds"), list)
            and s["actorIds"]
            and all(positive(i) for i in s["actorIds"])
        )
        require(re.fullmatch(r"[a-f0-9]{64}", s.get("certificateSha256", "")))
        require(
            re.fullmatch(r"[A-Za-z]\w*(?:\.[A-Za-z]\w*)+", s.get("androidPackage", ""))
        )
        require(type(s.get("productionApproved")) is bool)
    require(
        len({s["repositoryId"] for s in p["sources"].values()}) == len(p["sources"]),
        "One registered app per source repository",
    )
    return p


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class API:
    def __init__(self, token):
        self.token = token

    def request(self, path, method="GET", data=None):
        require(path.startswith("/") and not path.startswith("//"))
        headers = {
            "Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Boreion-central-publisher",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(data).encode()
        try:
            with urllib.request.build_opener(NoRedirect).open(
                urllib.request.Request(
                    "https://api.github.com" + path,
                    data=data,
                    method=method,
                    headers=headers,
                ),
                timeout=30,
            ) as r:
                return json.load(r) if r.status != 204 else None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise Rejected(
                "GitHub API operation failed (HTTP " + str(e.code) + ")"
            ) from None
        except Exception:
            raise Rejected("GitHub API connection failed") from None

    def download(self, path, output, digest):
        require(re.fullmatch(r"sha256:[a-f0-9]{64}", digest or ""))
        req = urllib.request.Request(
            "https://api.github.com" + path,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "User-Agent": "Boreion-central-publisher",
            },
        )
        try:
            urllib.request.build_opener(NoRedirect).open(req, timeout=30)
            raise Rejected("Artifact endpoint did not redirect")
        except urllib.error.HTTPError as e:
            require(e.code == 302, "Artifact download unavailable")
            location = e.headers.get("Location", "")
        url = urllib.parse.urlparse(location)
        require(
            url.scheme == "https"
            and not url.username
            and not url.password
            and url.port in [None, 443]
            and url.hostname
            and url.hostname.endswith(".blob.core.windows.net"),
            "Unexpected artifact storage destination",
        )
        # Storage receives the signed URL, never the GitHub Authorization header.
        try:
            total = 0
            sha = hashlib.sha256()
            with urllib.request.build_opener(NoRedirect).open(
                location, timeout=60
            ) as response, open(output, "wb") as f:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    require(total <= MAX_ZIP, "Artifact exceeds size limit")
                    sha.update(chunk)
                    f.write(chunk)
            require(
                "sha256:" + sha.hexdigest() == digest,
                "Artifact archive digest mismatch",
            )
        except Rejected:
            raise
        except Exception:
            raise Rejected("Artifact storage download failed") from None


def verify_context(policy, actor, triggering, event, ref, repo):
    require(
        repo == REPO
        and ref == "refs/heads/main"
        and event in ["schedule", "workflow_dispatch"]
    )
    require(
        actor in policy["centralActorIds"]
        or (event == "workflow_dispatch" and actor == BOT),
        "Central actor is not approved",
    )
    require(
        triggering in policy["centralActorIds"]
        or (event == "workflow_dispatch" and actor == BOT and triggering == BOT),
        "Rerun actor is not approved",
    )


def source_run(api, source, run_id):
    repo = api.request("/repos/" + source["repository"])
    require(repo is not None)
    require(
        repo.get("id") == source["repositoryId"]
        and repo.get("full_name") == source["repository"]
        and repo.get("owner", {}).get("id") == source["ownerId"]
        and repo.get("private") is True
        and not repo.get("fork")
    )
    workflow = api.request(
        f"/repos/{source['repository']}/actions/workflows/{source['workflowId']}"
    )
    require(
        workflow is not None
        and workflow.get("path") == source["workflowPath"]
        and workflow.get("state") == "active"
    )
    run = api.request(f"/repos/{source['repository']}/actions/runs/{run_id}")
    require(run is not None)
    require(
        run.get("id") == run_id
        and run.get("repository", {}).get("id") == source["repositoryId"]
        and (run.get("head_repository") or {}).get("id") == source["repositoryId"]
    )
    require(
        run.get("workflow_id") == source["workflowId"]
        and run.get("path") == source["workflowPath"]
    )
    require(
        run.get("status") == "completed"
        and run.get("conclusion") == "success"
        and run.get("event") == "workflow_dispatch"
        and run.get("head_branch") == source["branch"]
        and not run.get("pull_requests")
    )
    require(
        run.get("actor", {}).get("id") in source["actorIds"]
        and run.get("triggering_actor", {}).get("id") in source["actorIds"]
    )
    require(
        re.fullmatch(r"[a-f0-9]{40}", run.get("head_sha", ""))
        and run.get("head_commit", {}).get("id") == run["head_sha"]
        and positive(run.get("run_attempt"))
    )
    return run


def artifact_identity(name):
    m = re.fullmatch(
        r"boreion--(" + APP + r")--(" + VERSION + r")--(beta|production)", name or ""
    )
    require(m is not None, "Artifact name is invalid")
    app, version, channel = m.groups()
    require((channel == "beta") == ("-beta." in version))
    return app, version, channel


def find_artifact(api, source, run, app, channel):
    d = api.request(
        f"/repos/{source['repository']}/actions/runs/{run['id']}/artifacts?per_page=100"
    )
    require(d is not None and d.get("total_count", 101) <= 100)
    matching = []
    for a in d.get("artifacts", []):
        try:
            aid, v, c = artifact_identity(a.get("name"))
        except Rejected:
            continue
        if aid == app and c == channel:
            matching.append(a)
    require(len(matching) == 1, "Exactly one candidate artifact is required")
    a = matching[0]
    require(
        positive(a.get("id"))
        and a.get("expired") is False
        and 0 < a.get("size_in_bytes", 0) <= MAX_ZIP
    )
    require(re.fullmatch(r"sha256:[a-f0-9]{64}", (a.get("digest") or "")))
    binding = a.get("workflow_run", {})
    require(
        binding.get("id") == run["id"]
        and binding.get("repository_id") == source["repositoryId"]
        and binding.get("head_repository_id") == source["repositoryId"]
        and binding.get("head_sha") == run["head_sha"]
        and binding.get("head_branch") == source["branch"]
    )
    return a


def require_production_gate(api, channel):
    if channel == "beta":
        return
    e = api.request("/repos/" + REPO + "/environments/publication-production")
    require(e is not None, "Production environment must be configured before use")
    rules = e.get("protection_rules", [])
    require(
        any(
            r.get("type") == "required_reviewers" and r.get("reviewers") for r in rules
        ),
        "Required production reviewers are missing",
    )
    require(
        e.get("can_admins_bypass") is not True,
        "Disable production administrator bypass",
    )
    main_branch = api.request("/repos/" + REPO + "/branches/main")
    require(
        main_branch is not None and main_branch.get("protected") is True,
        "Central main must be protected",
    )
    branches = e.get("deployment_branch_policy") or {}
    require(
        branches.get("protected_branches") is True
        and branches.get("custom_branch_policies") is False,
        "Production environment must require protected branches",
    )


def safe_extract(archive, directory):
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        require(1 <= len(entries) <= 16, "Invalid artifact file count")
        require(
            sum(i.file_size for i in entries) <= 300 * 1024 * 1024,
            "Artifact expands beyond limit",
        )
        seen = set()
        for i in entries:
            require(
                re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}", i.filename)
                and i.filename not in seen
                and not i.is_dir(),
                "Unsafe artifact path",
            )
            require(
                not stat.S_ISLNK(i.external_attr >> 16)
                and not i.flag_bits & 1
                and i.file_size <= MAX_ZIP,
                "Unsafe artifact entry",
            )
            require(
                i.file_size <= max(1, i.compress_size) * 300,
                "Archive compression limit exceeded",
            )
            seen.add(i.filename)
        pathlib.Path(directory).mkdir(parents=True, exist_ok=False)
        for i in entries:
            with z.open(i) as src, open(
                pathlib.Path(directory) / i.filename, "wb"
            ) as dst:
                total = 0
                while chunk := src.read(1024 * 1024):
                    total += len(chunk)
                    require(total <= i.file_size)
                    dst.write(chunk)
    return seen


def verify_provenance(request, source, run, app, version, channel):
    require(
        request
        == {
            "schemaVersion": 1,
            "repositoryId": source["repositoryId"],
            "runId": run["id"],
            "runAttempt": run["run_attempt"],
            "commit": run["head_sha"],
            "actorId": run["actor"]["id"],
            "appId": app,
            "version": version,
            "channel": channel,
        },
        "Source provenance mismatch",
    )


def sandbox_command(image, tools, apk, tool):
    require(
        re.fullmatch(r"eclipse-temurin:17-jre@sha256:[a-f0-9]{64}", image),
        "Verifier image must be pinned",
    )
    require(os.getuid() > 0, "Verification requires a non-root hosted runner")
    prefix = [
        "docker",
        "--host=unix:///var/run/docker.sock",
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        f"--user={os.getuid()}:{os.getgid()}",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=128",
        "--memory=512m",
        "--cpus=1",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "--mount",
        f"type=bind,src={pathlib.Path(tools).resolve()},dst=/tools,readonly",
        "--mount",
        f"type=bind,src={pathlib.Path(apk).resolve()},dst=/input/app.apk,readonly",
        "--env",
        "LD_LIBRARY_PATH=/tools/lib64",
    ]
    if tool == "signature":
        return prefix + [
            "--entrypoint",
            "/opt/java/openjdk/bin/java",
            image,
            "-jar",
            "/tools/lib/apksigner.jar",
            "verify",
            "--verbose",
            "--print-certs",
            "/input/app.apk",
        ]
    require(tool == "manifest")
    return prefix + [
        "--entrypoint",
        "/tools/aapt",
        image,
        "dump",
        "badging",
        "/input/app.apk",
    ]


def verify_apk(apk, source, version, image, tools, execute=subprocess.run):
    outputs = []
    for tool in ["signature", "manifest"]:
        r = execute(
            sandbox_command(image, tools, apk, tool),
            capture_output=True,
            text=True,
            timeout=90,
        )
        require(r.returncode == 0, "APK verification failed")
        outputs.append(r.stdout)
    certs = re.findall(
        r"^Signer #\d+ certificate SHA-256 digest: ([a-fA-F0-9]{64})$", outputs[0], re.M
    )
    require(
        len(certs) == 1 and certs[0].lower() == source["certificateSha256"],
        "APK signing identity mismatch",
    )
    package = re.search(
        r"^package: name='([^']+)' .*?versionName='([^']+)'", outputs[1], re.M
    )
    require(
        package is not None
        and package.group(1) == source["androidPackage"]
        and package.group(2) == version,
        "APK package/version mismatch",
    )


def sanitize_bundle(
    directory, output, source, run, app, channel, image, tools, execute=subprocess.run
):
    root = pathlib.Path(directory)
    manifest = json.loads((root / "boreion-app.json").read_text())
    require(manifest.get("schemaVersion") == 1 and manifest.get("appId") == app)
    version = manifest.get("version", "")
    require(
        re.fullmatch(VERSION, version)
        and len(version) <= 80
        and ("-beta." in version) == (channel == "beta")
    )
    metadata = manifest.get("metadata", {})
    require(
        metadata.get("distribution", {}).get("signingCertificateSha256")
        == source["certificateSha256"]
        and metadata.get("distribution", {}).get("public") is True
    )
    asset = manifest.get("apk", {})
    name = asset.get("assetName", "")
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.apk", name))
    expected = {
        "boreion-app.json",
        "request.json",
        "tag.txt",
        "release-notes.txt",
        name,
    } | set(metadata.get("screenshots", []))
    if metadata.get("icon"):
        expected.add(metadata["icon"])
    require(
        {p.name for p in root.iterdir()} == expected,
        "Unexpected files in producer artifact",
    )
    verify_provenance(
        json.loads((root / "request.json").read_text()),
        source,
        run,
        app,
        version,
        channel,
    )
    require((root / "tag.txt").read_text().strip() == f"{app}/v{version}")
    require(
        hashlib.sha256((root / name).read_bytes()).hexdigest() == asset.get("sha256"),
        "APK SHA-256 mismatch",
    )
    verify_apk(root / name, source, version, image, tools, execute)
    # Only this centrally reviewed helper is executed. Producer scripts/notes are never run/copied.
    spec = importlib.util.spec_from_file_location(
        "public_packager", pathlib.Path(__file__).with_name("prepare-release.py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.prepare(
        root / "boreion-app.json",
        root / name,
        version,
        source["certificateSha256"],
        root,
        output,
    )
    return {
        "appId": app,
        "version": version,
        "channel": channel,
        "sha256": asset["sha256"],
    }


def add_outputs(values):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            for key, value in values.items():
                require(re.fullmatch(r"[A-Za-z0-9_.@:/,-]*", str(value)) is not None)
                f.write(f"{key}={value}\n")


def context(policy, api):
    central = api.request("/repos/" + REPO)
    require(
        central is not None
        and central.get("private") is False
        and central.get("full_name") == REPO
        and central.get("default_branch") == "main",
        "Central repository must remain public on main",
    )
    triggering = (
        api.request(
            "/users/"
            + urllib.parse.quote(
                os.environ.get("CENTRAL_TRIGGERING_ACTOR", ""), safe=""
            )
        )
        or {}
    )
    verify_context(
        policy,
        int(os.environ["CENTRAL_ACTOR_ID"]),
        triggering.get("id"),
        os.environ["GITHUB_EVENT_NAME"],
        os.environ["GITHUB_REF"],
        os.environ["GITHUB_REPOSITORY"],
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=["plan", "preflight", "fetch", "verify", "scan", "scan-plan"]
    )
    parser.add_argument("--app")
    parser.add_argument("--run", type=int)
    parser.add_argument("--channel", choices=["beta", "production"])
    a = parser.parse_args()
    policy = load_policy(os.environ["BOREION_SOURCE_POLICY"])
    api = API(os.environ["GH_TOKEN"])
    context(policy, api)
    source_api = API(os.environ.get("SOURCE_TOKEN", ""))
    if a.mode == "scan-plan":
        names = [s["repository"].split("/")[1] for s in policy["sources"].values()]
        require(bool(names), "No source repositories are approved")
        if os.environ.get("GITHUB_ACTIONS") == "true":
            for name in names:
                print("::add-mask::" + name)
        add_outputs({"repositories": ",".join(names)})
        return
    if a.mode == "scan":
        scan(api, source_api, policy)
        return
    require(a.app in policy["sources"] and positive(a.run))
    source = policy["sources"][a.app]
    require(
        a.channel != "production" or source["productionApproved"],
        "App is not approved for production",
    )
    require_production_gate(api, a.channel)
    if a.mode == "plan":

        if os.environ.get("GITHUB_ACTIONS") == "true":
            print("::add-mask::" + source["repository"])
            print("::add-mask::" + source["repository"].split("/")[1])
        add_outputs(
            {"channel": a.channel, "repositories": source["repository"].split("/")[1]}
        )
        return
    if a.mode == "preflight":
        run = source_run(source_api, source, a.run)
        artifact = find_artifact(source_api, source, run, a.app, a.channel)
        _, version, _ = artifact_identity(artifact["name"])
        add_outputs(
            {"version": version, "archiveSha256": artifact["digest"].split(":")[1]}
        )
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a") as f:
                f.write(
                    f"Verified candidate **{a.app} {version}** ({a.channel}). Source identity, actor, main commit and successful workflow checked. Archive SHA-256: `{artifact['digest'].split(':')[1]}`. APK verification follows only after export approval.\n"
                )
        return
    if a.mode == "fetch":
        run = source_run(source_api, source, a.run)
        artifact = find_artifact(source_api, source, run, a.app, a.channel)
        source_api.download(
            f"/repos/{source['repository']}/actions/artifacts/{artifact['id']}/zip",
            "candidate.zip",
            artifact["digest"],
        )
        pathlib.Path("proof.json").write_text(
            json.dumps(
                {"app": a.app, "channel": a.channel, "run": run, "artifact": artifact}
            )
        )
        return
    proof = json.loads(pathlib.Path("proof.json").read_text())
    run = proof["run"]
    artifact = proof["artifact"]
    require(
        proof["app"] == a.app
        and proof["channel"] == a.channel
        and run["id"] == a.run
        and run["repository"]["id"] == source["repositoryId"]
    )
    require(
        "sha256:"
        + hashlib.sha256(pathlib.Path("candidate.zip").read_bytes()).hexdigest()
        == artifact["digest"],
        "Archive changed after fetch",
    )
    safe_extract("candidate.zip", "candidate")
    image = pathlib.Path("verifier-image.txt").read_text().strip()
    tools = pathlib.Path(os.environ["ANDROID_HOME"]) / "build-tools" / "35.0.0"
    result = sanitize_bundle(
        "candidate", "publish-bundle", source, run, a.app, a.channel, image, tools
    )
    require(
        artifact_identity(artifact["name"]) == (a.app, result["version"], a.channel)
    )
    add_outputs(result)
    print("Approved bundle verified; no private source identifiers exported.")


def scan(api, source_api, policy):
    from datetime import datetime, timedelta, timezone

    # History suppresses duplicate reviews. Atomic release tags are the durable idempotency boundary.
    seen = set()
    dispatched = 0
    for page in range(1, 11):
        d = (
            api.request(
                f"/repos/{REPO}/actions/workflows/central-publish.yml/runs?per_page=100&page={page}"
            )
            or {}
        )
        runs = d.get("workflow_runs", [])
        seen.update(r.get("display_title") for r in runs)
        if len(runs) < 100:
            break
    cutoff = urllib.parse.quote(
        ">=" + (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d"),
        safe="",
    )
    for app, source in policy["sources"].items():
        for page in range(1, 11):
            d = source_api.request(
                f"/repos/{source['repository']}/actions/workflows/{source['workflowId']}/runs?event=workflow_dispatch&status=success&branch=main&created={cutoff}&per_page=100&page={page}"
            )
            require(d is not None, "An approved source is unavailable")
            items = d.get("workflow_runs", [])
            for item in items:
                if not positive(item.get("id")):
                    continue
                title = f'Publish {app} / run {item["id"]}'
                if title in seen:
                    continue
                try:
                    run = source_run(source_api, source, item["id"])
                    for channel in ["beta", "production"]:
                        if channel == "production" and not source["productionApproved"]:
                            continue
                        try:
                            artifact = find_artifact(
                                source_api, source, run, app, channel
                            )
                        except Rejected:
                            continue
                        _, version, _ = artifact_identity(artifact["name"])
                        tag = urllib.parse.quote(f"{app}/v{version}", safe="")
                        if (
                            api.request(f"/repos/{REPO}/releases/tags/{tag}")
                            is not None
                        ):
                            continue
                        require_production_gate(api, channel)
                        api.request(
                            f"/repos/{REPO}/actions/workflows/central-publish.yml/dispatches",
                            "POST",
                            {
                                "ref": "main",
                                "inputs": {
                                    "app_id": app,
                                    "source_run_id": str(run["id"]),
                                    "channel": channel,
                                },
                            },
                        )
                        seen.add(title)
                        dispatched += 1
                except Rejected:
                    continue
            if len(items) < 100:
                break
            if page == 10:
                print(
                    "Source history scan bound reached; older builds may need manual review."
                )
    print(f"Approved build scan completed; central review requests: {dispatched}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Central publication stopped: policy, API or verification prerequisite failed.",
            file=sys.stderr,
        )
        sys.exit(1)
