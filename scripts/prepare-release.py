#!/usr/bin/env python3
"""Build an allowlisted public bundle. Never copy private source paths or run URLs."""

import argparse, hashlib, json, pathlib, re, shutil


def prepare(config, apk, version, certificate, assets, output):
    config = json.loads(pathlib.Path(config).read_text())
    if config.get("schemaVersion") != 1:
        raise ValueError("Unsupported metadata schema")
    app = config.get("appId", "")
    if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", app) or len(app) > 80:
        raise ValueError("Invalid appId")
    if len(version) > 80 or not re.fullmatch(
        r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-beta\.(0|[1-9]\d*))?", version
    ):
        raise ValueError("Invalid version")
    if not re.fullmatch(r"[a-f0-9]{64}", certificate):
        raise ValueError("Invalid signing certificate")
    source = config.get("metadata", {})
    if source.get("distribution", {}).get("public") is not True:
        raise ValueError("Explicit public opt-in required")
    if source["distribution"].get("signingCertificateSha256") != certificate:
        raise ValueError("Metadata signing certificate mismatch")
    if not isinstance(source.get("name"), str) or not 1 <= len(source["name"]) <= 80:
        raise ValueError("App name required")
    limits = {
        "description": 10000,
        "summary": 240,
        "category": 40,
        "publisher": 80,
        "minAndroid": 40,
    }
    metadata = {
        "name": source["name"],
        "sourceVisible": False,
        "distribution": {"public": True, "signingCertificateSha256": certificate},
    }
    for key, limit in limits.items():
        if key in source:
            if not isinstance(source[key], str) or len(source[key]) > limit:
                raise ValueError("Invalid " + key)
            metadata[key] = source[key]
    for key in ["indexable", "featured"]:
        if key in source:
            if type(source[key]) is not bool:
                raise ValueError("Invalid " + key)
            metadata[key] = source[key]
    output = pathlib.Path(output)
    output.mkdir(parents=True, exist_ok=False)
    asset_root = pathlib.Path(assets).resolve()
    screenshots = source.get("screenshots", [])
    if not isinstance(screenshots, list) or len(screenshots) > 8:
        raise ValueError("Invalid screenshots")
    names = ([source["icon"]] if source.get("icon") else []) + screenshots
    for name in names:
        if not isinstance(name, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]*\.(png|jpg|jpeg|webp)", name
        ):
            raise ValueError("Invalid image name")
        path = (asset_root / name).resolve()
        if (
            path.parent != asset_root
            or not path.is_file()
            or path.stat().st_size > 10 * 1024 * 1024
        ):
            raise ValueError("Invalid image file")
        shutil.copyfile(path, output / name)
    if source.get("icon"):
        metadata["icon"] = source["icon"]
    metadata["screenshots"] = screenshots
    apk = pathlib.Path(apk)
    if not apk.is_file() or apk.stat().st_size == 0:
        raise ValueError("APK missing")
    apk_name = f"{app}-{version}.apk"
    shutil.copyfile(apk, output / apk_name)
    digest = hashlib.sha256((output / apk_name).read_bytes()).hexdigest()
    manifest = {
        "schemaVersion": 1,
        "appId": app,
        "version": version,
        "metadata": metadata,
        "apk": {"assetName": apk_name, "sha256": digest},
    }
    data = json.dumps(manifest, ensure_ascii=False, indent=2)
    if len(data.encode()) > 40000:
        raise ValueError("Metadata too large for release notes")
    (output / "boreion-app.json").write_text(data + "\n")
    # A standalone release owns its manifest; no shared index is ever read/rewritten.
    (output / "release-notes.txt").write_text(
        "[boreion-app]\n" + data + "\n[/boreion-app]\n"
    )
    (output / "tag.txt").write_text(f"{app}/v{version}")
    return manifest


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--metadata", default="boreion-app.json")
    p.add_argument("--apk", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--certificate", required=True)
    p.add_argument("--assets", default="distribution")
    p.add_argument("--output", default="public-bundle")
    a = p.parse_args()
    prepare(a.metadata, a.apk, a.version, a.certificate, a.assets, a.output)
