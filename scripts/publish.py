#!/usr/bin/env python3
"""Publishing-key job: trusted central code and canonical data only, never APK execution."""

import hashlib, json, os, pathlib, re, sys, urllib.parse, urllib.request
from central import (
    API,
    REPO,
    VERSION,
    Rejected,
    require,
    load_policy,
    context,
    require_production_gate,
    safe_extract,
)


def validate_bundle(root, app, channel, certificate):
    root = pathlib.Path(root)
    m = json.loads((root / "boreion-app.json").read_text())
    v = m.get("version", "")
    require(
        m.get("schemaVersion") == 1
        and m.get("appId") == app
        and re.fullmatch(VERSION, v)
        and len(v) <= 80
    )
    require(("-beta." in v) == (channel == "beta"))
    meta = m.get("metadata", {})
    require(
        meta.get("sourceVisible") is False
        and meta.get("distribution", {}).get("public") is True
        and meta["distribution"].get("signingCertificateSha256") == certificate
    )
    name = m.get("apk", {}).get("assetName", "")
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.apk", name))
    images = meta.get("screenshots", []) + ([meta["icon"]] if meta.get("icon") else [])
    require(
        all(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.(png|jpg|jpeg|webp)", i)
            for i in images
        )
    )
    files = {"boreion-app.json", name} | set(images)
    require(
        {p.name for p in root.iterdir()} == files | {"release-notes.txt", "tag.txt"}
    )
    digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
    require(digest == m["apk"].get("sha256"))
    tag = f"{app}/v{v}"
    require((root / "tag.txt").read_text().strip() == tag)
    # Regenerate notes from parsed manifest; never execute or interpolate producer notes.
    notes = (
        "[boreion-app]\n"
        + json.dumps(m, ensure_ascii=False, indent=2)
        + "\n[/boreion-app]\n"
    )
    return tag, digest, name, notes, sorted(files)


def publish(api, root, app, channel, certificate):
    tag, digest, name, notes, files = validate_bundle(root, app, channel, certificate)
    central_sha = os.environ["GITHUB_SHA"]
    require(re.fullmatch(r"[a-f0-9]{40}", central_sha))
    # Atomic reservation: duplicate versions fail; no clobber/delete/force retry.
    reservation = api.request(
        f"/repos/{REPO}/git/refs",
        "POST",
        {"ref": "refs/tags/" + tag, "sha": central_sha},
    )
    require(
        reservation is not None
        and reservation.get("ref") == "refs/tags/" + tag
        and reservation.get("object", {}).get("sha") == central_sha,
        "Tag reservation failed",
    )
    release = api.request(
        f"/repos/{REPO}/releases",
        "POST",
        {
            "tag_name": tag,
            "name": tag,
            "body": notes,
            "draft": True,
            "prerelease": channel == "beta",
        },
    )
    require(
        release is not None
        and type(release.get("id")) is int
        and release.get("draft") is True
        and release.get("tag_name") == tag
    )
    release_id = release["id"]
    for filename in files:
        path = pathlib.Path(root) / filename
        # Fixed upload host/repo/release ID; credentials never follow a redirect.
        url = (
            f"https://uploads.github.com/repos/{REPO}/releases/{release_id}/assets?name="
            + urllib.parse.quote(filename, safe="")
        )
        request = urllib.request.Request(
            url,
            data=path.read_bytes(),
            method="POST",
            headers={
                "Authorization": "Bearer " + api.token,
                "Content-Type": "application/octet-stream",
                "Accept": "application/vnd.github+json",
                "User-Agent": "Boreion-central-publisher",
            },
        )
        from central import NoRedirect

        try:
            with urllib.request.build_opener(NoRedirect).open(
                request, timeout=120
            ) as response:
                asset = json.load(response)
        except Exception:
            raise Rejected("Public upload failed; draft retained") from None
        require(
            asset.get("name") == filename
            and asset.get("state") == "uploaded"
            and asset.get("size") == path.stat().st_size
            and asset.get("digest")
            == "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
            "GitHub asset integrity mismatch; draft retained",
        )
    published = api.request(
        f"/repos/{REPO}/releases/{release_id}", "PATCH", {"draft": False}
    )
    require(
        published is not None
        and published.get("draft") is False
        and published.get("tag_name") == tag,
        "Release publication not confirmed",
    )
    print("Public release published for approved app/version.")


def main():
    policy = load_policy(os.environ["BOREION_SOURCE_POLICY"])
    api = API(os.environ["GH_TOKEN"])
    context(policy, api)
    app = os.environ["APP_ID"]
    channel = os.environ["CHANNEL"]
    require(app in policy["sources"] and channel in ["beta", "production"])
    source = policy["sources"][app]
    require(channel != "production" or source["productionApproved"])
    require_production_gate(api, channel)
    run_id = int(os.environ["GITHUB_RUN_ID"])
    d = api.request(f"/repos/{REPO}/actions/runs/{run_id}/artifacts?per_page=100") or {}
    matches = [
        a
        for a in d.get("artifacts", [])
        if a.get("name") == "verified-public-bundle" and not a.get("expired")
    ]
    require(len(matches) == 1)
    a = matches[0]
    binding = a.get("workflow_run", {})
    require(
        binding.get("id") == run_id
        and binding.get("repository_id") == int(os.environ["GITHUB_REPOSITORY_ID"])
        and binding.get("head_sha") == os.environ["GITHUB_SHA"]
    )
    api.download(
        f'/repos/{REPO}/actions/artifacts/{a["id"]}/zip',
        "verified.zip",
        a.get("digest"),
    )
    safe_extract("verified.zip", "verified")
    publish(api, "verified", app, channel, source["certificateSha256"])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Central publication stopped; no automatic overwrite or draft cleanup.",
            file=sys.stderr,
        )
        sys.exit(1)
