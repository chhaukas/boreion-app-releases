#!/usr/bin/env python3
"""Read-only App integration probe. Never download, execute or publish an APK."""
import os
import sys
from central import API, require, positive


def check(api, repository_id):
    require(positive(repository_id))
    found = None
    for page in range(1, 11):
        result = api.request(f"/installation/repositories?per_page=100&page={page}")
        require(result is not None, "Cannot enumerate reader installation")
        repositories = result.get("repositories", [])
        for repository in repositories:
            if repository.get("id") == repository_id:
                require(repository.get("private") is True)
                require(repository.get("owner", {}).get("id") == 338504245)
                require(repository.get("owner", {}).get("login") == "chhaukas")
                found = repository
        if len(repositories) < 100:
            break
    require(found is not None, "Approved source is not accessible to the reader App")
    # Name is obtained from authenticated metadata; never printed publicly.
    result = api.request(f"/repos/{found['full_name']}/actions/workflows")
    require(result is not None, "Reader cannot access source Actions")
    workflows = result.get("workflows", [])
    build = [w for w in workflows if w.get("path") == ".github/workflows/boreion-build.yml" and w.get("state") == "active"]
    print("PASS: central App authentication, selected private repository, owner and Actions-read access.")
    if build:
        print("PASS: source build-only distribution workflow is registered.")
    else:
        print("PENDING: source build-only workflow is not yet registered on main.")
    return bool(build)


if __name__ == "__main__":
    try:
        check(API(os.environ["SOURCE_TOKEN"]), int(os.environ["EXPECTED_SOURCE_ID"]))
    except Exception:
        print("Reader integration probe failed; no files or releases were published.", file=sys.stderr)
        sys.exit(1)
