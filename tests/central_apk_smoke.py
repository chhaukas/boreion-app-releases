"""Optional real crypto test. Creates/deletes a local fixture; never calls GitHub APIs."""

import hashlib, importlib.util, os, pathlib, re, subprocess, tempfile, zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "central_smoke",
    pathlib.Path(
        os.environ.get(
            "BOREION_CENTRAL_TEMPLATE_ROOT", ROOT / "templates/central-publisher"
        )
    )
    / "scripts/central.py",
)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def command(argv):
    r = subprocess.run(
        [str(x) for x in argv], capture_output=True, text=True, timeout=90
    )
    if r.returncode:
        raise RuntimeError("Local fixture command failed: " + r.stderr[:1200])
    return r.stdout


def main():
    tools = pathlib.Path(os.environ["BOREION_TEST_BUILD_TOOLS"]).resolve()
    android_jar = pathlib.Path(os.environ["BOREION_TEST_ANDROID_JAR"]).resolve()
    image = (
        (
            pathlib.Path(
                os.environ.get(
                    "BOREION_CENTRAL_TEMPLATE_ROOT",
                    ROOT / "templates/central-publisher",
                )
            )
            / "verifier-image.txt"
        )
        .read_text()
        .strip()
    )
    with tempfile.TemporaryDirectory(prefix="boreion-local-apk-test-") as folder:
        folder = pathlib.Path(folder)
        password = folder / "password"
        password.write_text("test-fixture-only-not-production\n")
        password.chmod(0o600)
        key_password = folder / "key-password"
        key_password.write_text(password.read_text())
        key_password.chmod(0o600)
        manifest = folder / "AndroidManifest.xml"
        manifest.write_text(
            """<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.boreion.test" android:versionCode="1" android:versionName="1.0.0"><uses-sdk android:minSdkVersion="26" android:targetSdkVersion="35"/><application android:hasCode="false" android:label="Local verification fixture"/></manifest>"""
        )
        unsigned = folder / "unsigned.apk"
        signed = folder / "signed.apk"
        key = folder / "fixture.jks"
        command(
            [
                tools / "aapt",
                "package",
                "-f",
                "-M",
                manifest,
                "-I",
                android_jar,
                "-F",
                unsigned,
            ]
        )
        command(
            [
                "keytool",
                "-genkeypair",
                "-keystore",
                key,
                "-storepass:file",
                password,
                "-keypass:file",
                key_password,
                "-alias",
                "fixture",
                "-keyalg",
                "RSA",
                "-keysize",
                "2048",
                "-validity",
                "1",
                "-dname",
                "CN=Boreion local fixture",
                "-noprompt",
            ]
        )
        command(
            [
                "java",
                "-jar",
                tools / "lib/apksigner.jar",
                "sign",
                "--ks",
                key,
                "--ks-key-alias",
                "fixture",
                "--ks-pass",
                "file:" + str(password),
                "--key-pass",
                "file:" + str(key_password),
                "--out",
                signed,
                unsigned,
            ]
        )
        details = command(
            [
                "java",
                "-jar",
                tools / "lib/apksigner.jar",
                "verify",
                "--print-certs",
                signed,
            ]
        )
        cert = re.search(
            r"Signer #1 certificate SHA-256 digest: ([a-f0-9]{64})", details
        )[1]
        source = {"certificateSha256": cert, "androidPackage": "com.boreion.test"}

        def diagnose(argv, **kwargs):
            result = subprocess.run(argv, **kwargs)
            if result.returncode:
                raise RuntimeError(
                    "Sandbox fixture tool failed: " + result.stderr[:1500]
                )
            return result

        c.verify_apk(signed, source, "1.0.0", image, tools, diagnose)
        for changed_source, version in [
            ({**source, "certificateSha256": "f" * 64}, "1.0.0"),
            (source, "2.0.0"),
            ({**source, "androidPackage": "com.boreion.other"}, "1.0.0"),
        ]:
            try:
                c.verify_apk(signed, changed_source, version, image, tools)
            except c.Rejected:
                pass
            else:
                raise AssertionError("Invalid signer/package/version accepted")
        with zipfile.ZipFile(signed, "a") as z:
            z.writestr("tampered.txt", "modified after signing")
        try:
            c.verify_apk(signed, source, "1.0.0", image, tools)
        except c.Rejected:
            pass
        else:
            raise AssertionError("Tampered APK accepted")
    print(
        "Real sandbox smoke passed: valid signature accepted; wrong signer/package/version and modified APK rejected. Temporary test APK/key deleted; nothing published."
    )


if __name__ == "__main__":
    main()
