#!/usr/bin/env python3
"""One exact, owner-requested Mosefot H01 Bak fossen beta APK. No arbitrary import or source-build claims."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import urllib.parse
import urllib.request
from central import API, REPO, NoRedirect, require, safe_extract, verify_apk, Rejected

RELEASE_ID = 432730820
TAG = 'mosefot/v0.1.0-beta.6'
CERT = 'c2e542bbdb88a9a1a30cfe99b25162da01b4c7321feefc0b6805f7d7c95d16b8'
APPROVED = {'boreion-app.json': {'blob': '2f3d6eac04efedd549f3ffcb6277391b53852668', 'sha256': '3d0a8d33fbc1d973f50ad7968d0a092c29743bbefe29918e5ce8ae48a90bb1de', 'size': 905}, 'h01-bergny.png': {'blob': '9e36a982cb6547be5400dca5fcedb772316eff6e', 'sha256': '4099d71753ec2279dcccd22b7d83be77720beae615e87825a0c98518c6e3b03d', 'size': 746800}, 'h01-start.png': {'blob': 'df142bda947d1c6d79df432b048074f1a0fbaf7c', 'sha256': '7f84988938df732f3666710c1a6d3a38aaf0eeb986be1f114cee2a0c9cfe7fb0', 'size': 781373}, 'icon.png': {'blob': 'd13ac993e82c34fc06a6d90b40a4337b25bff6b8', 'sha256': '9938a198f06015e79aedf5c065ba8bc7bb72b171a757207a178458542b13abff', 'size': 498844}, 'mosefot-0.1.0-beta.6.apk': {'blob': '8ea67a326c2baddc428ae8bdabfa1bdb25e7dd94', 'sha256': 'c00b3a00e04f18e9810c7972554f6c8d0d2ef0658e39e12393b5c4aa5f400971', 'size': 72844308}}


def files_valid(directory):
    root = Path(directory)
    require({p.name for p in root.iterdir()} == set(APPROVED))
    for name, expected in APPROVED.items():
        path = root / name
        require(path.is_file() and not path.is_symlink())
        data = path.read_bytes()
        require(len(data) == expected['size'] and hashlib.sha256(data).hexdigest() == expected['sha256'])
    manifest = json.loads((root / 'boreion-app.json').read_text())
    require(manifest['appId'] == 'mosefot' and manifest['version'] == '0.1.0-beta.6')
    require(manifest['metadata']['sourceVisible'] is False and manifest['metadata']['distribution']['public'] is True)
    require(manifest['metadata']['distribution']['signingCertificateSha256'] == CERT)
    require(manifest['apk']['sha256'] == APPROVED['mosefot-0.1.0-beta.6.apk']['sha256'])
    return manifest


def verify(api):
    root = Path('owner-approved-import')
    root.mkdir()
    for name, expected in APPROVED.items():
        blob = api.request(f'/repos/{REPO}/git/blobs/{expected["blob"]}')
        require(blob and blob.get('encoding') == 'base64' and blob.get('sha') == expected['blob'])
        data = base64.b64decode(''.join(blob['content'].split()), validate=True)
        require(len(data) == expected['size'] and hashlib.sha256(data).hexdigest() == expected['sha256'])
        (root / name).write_bytes(data)
    files_valid(root)
    verify_apk(root / 'mosefot-0.1.0-beta.6.apk', {'certificateSha256':CERT,'androidPackage':'no.mosefot'}, '0.1.0-beta.6', Path('verifier-image.txt').read_text().strip(), Path(os.environ['ANDROID_HOME']) / 'build-tools/35.0.0')
    print('Approved H01 Bak fossen beta APK verified: signature, package, actual version, size and SHA-256.')


def publish(api):
    print('Publish preflight: load run-bound verified artifact')
    run_id = int(os.environ['GITHUB_RUN_ID'])
    artifacts = api.request(f'/repos/{REPO}/actions/runs/{run_id}/artifacts?per_page=100')
    matches = [a for a in artifacts.get('artifacts',[]) if a['name']=='verified-owner-approved-mosefot-010-beta-6' and not a['expired']]
    require(len(matches)==1)
    a=matches[0]
    binding=a.get('workflow_run',{})
    require(binding.get('id')==run_id and binding.get('head_sha')==os.environ['GITHUB_SHA'] and binding.get('repository_id')==int(os.environ['GITHUB_REPOSITORY_ID']))
    print('Publish preflight: download and digest-check verified artifact')
    api.download(f'/repos/{REPO}/actions/artifacts/{a["id"]}/zip','verified-import.zip',a.get('digest'))
    print('Publish preflight: safe extraction and exact file binding')
    safe_extract('verified-import.zip','verified-import')
    manifest=files_valid('verified-import')
    print('Publish preflight: exact empty draft and manifest')
    release=api.request(f'/repos/{REPO}/releases/{RELEASE_ID}')
    require(release and release.get('tag_name')==TAG and release.get('draft') is True and release.get('prerelease') is True)
    require(release.get('assets')==[], 'Draft is not empty; no automatic overwrite')
    blocks=re.findall(r'\[boreion-app\]([\s\S]*?)\[/boreion-app\]',release['body'])
    require(len(blocks)==1 and json.loads(blocks[0])==manifest)
    print('Publish preflight passed; upload exact approved bytes')
    for name,expected in APPROVED.items():
        url=f'https://uploads.github.com/repos/{REPO}/releases/{RELEASE_ID}/assets?name='+urllib.parse.quote(name,safe='')
        req=urllib.request.Request(url,data=(Path('verified-import')/name).read_bytes(),method='POST',headers={'Authorization':'Bearer '+api.token,'Content-Type':'application/octet-stream','Accept':'application/vnd.github+json','User-Agent':'Boreion-approved-manual-import'})
        with urllib.request.build_opener(NoRedirect).open(req,timeout=120) as response:
            asset=json.load(response)
        require(asset.get('state')=='uploaded' and asset.get('name')==name and asset.get('size')==expected['size'] and asset.get('digest')=='sha256:'+expected['sha256'])
    check=api.request(f'/repos/{REPO}/releases/{RELEASE_ID}')
    require({a['name'] for a in check['assets']}==set(APPROVED))
    for asset in check['assets']:
        expected=APPROVED[asset['name']]
        require(asset['state']=='uploaded' and asset['size']==expected['size'] and asset['digest']=='sha256:'+expected['sha256'])
    done=api.request(f'/repos/{REPO}/releases/{RELEASE_ID}','PATCH',{'tag_name':TAG,'draft':False,'prerelease':True})
    require(done and done.get('draft') is False and done.get('prerelease') is True and done.get('tag_name')==TAG)
    print('Published owner-requested Mosefot 0.1.0-beta.6 with verified GitHub asset digests.')


if __name__ == '__main__':
    try:
        require(os.environ['GITHUB_REPOSITORY']==REPO and os.environ['GITHUB_REF']=='refs/heads/main' and os.environ['GITHUB_ACTOR_ID']=='338504245' and os.environ['GITHUB_EVENT_NAME']=='workflow_dispatch')
        api=API(os.environ['GH_TOKEN'])
        if sys.argv[1]=='verify': verify(api)
        elif sys.argv[1]=='publish': publish(api)
        else: raise ValueError('Unknown operation')
    except Exception as error:
        # Rejected messages are fixed controller diagnostics; never print HTTP bodies or token values.
        detail=str(error) if isinstance(error,Rejected) else type(error).__name__
        print('Approved manual import stopped; no automatic overwrite or cleanup. '+detail,file=sys.stderr)
        sys.exit(1)
