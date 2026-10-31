#!/usr/bin/env python3
"""One exact, owner-requested Titan Trening guided Android Home selection and friendly training messages beta APK. No arbitrary import or source-build claims."""
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

RELEASE_ID = 429860908
TAG = 'chhaukas-titan-trening/v0.15.0-beta.3'
CERT = '1224fbfd595c3dfef8aafbda43f154fa0a7a7770c8130f2e1e640ca75fb6e030'
APPROVED = {'boreion-app.json': {'blob': '0ad7f176681036408e06e8a9f85e69f5be916099', 'sha256': 'ff780a323f215fd4d77d821bd193f5daf9a584c1e24055ff1480e10d5a7d6b30', 'size': 2418}, 'chhaukas-titan-trening-0.15.0-beta.3.apk': {'blob': 'ac8e4350b221e415f6a05a7e417d0790f0e27b29', 'sha256': '416b7161440183559f4645a4482a8cffc8353af593ed56444016652b36de24c0', 'size': 2373301}, 'home-choice-0153.png': {'blob': 'b1dab5c3c9be3e60947b03771b2224f26914c706', 'sha256': 'b3f6698fba5ba3343d97bc927188ba2c2fd6f1e8cfd88ac9b4f8a6cc32309780', 'size': 124321}, 'home-0152.png': {'blob': '495f31c0753cea8848e4a70f9645a5e262181e59', 'sha256': '1655e316cc771c250ab2e527737148ad0f280c93f607768c15f4c19060c2e7b6', 'size': 265786}, 'training-0152.png': {'blob': '10d4f8d5c2a6deb4384b00bd8954e63f25775dd5', 'sha256': 'dda74c696fe75e1e56ef9d73720a555c808e4b50d8317325926bc1781b0a8940', 'size': 239979}}


def files_valid(directory):
    root = Path(directory)
    require({p.name for p in root.iterdir()} == set(APPROVED))
    for name, expected in APPROVED.items():
        path = root / name
        require(path.is_file() and not path.is_symlink())
        data = path.read_bytes()
        require(len(data) == expected['size'] and hashlib.sha256(data).hexdigest() == expected['sha256'])
    manifest = json.loads((root / 'boreion-app.json').read_text())
    require(manifest['appId'] == 'chhaukas-titan-trening' and manifest['version'] == '0.15.0-beta.3')
    require(manifest['metadata']['sourceVisible'] is False and manifest['metadata']['distribution']['public'] is True)
    require(manifest['metadata']['distribution']['signingCertificateSha256'] == CERT)
    require(manifest['apk']['sha256'] == APPROVED['chhaukas-titan-trening-0.15.0-beta.3.apk']['sha256'])
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
    verify_apk(root / 'chhaukas-titan-trening-0.15.0-beta.3.apk', {'certificateSha256':CERT,'androidPackage':'no.titan.trening'}, '0.15.0-beta.3', Path('verifier-image.txt').read_text().strip(), Path(os.environ['ANDROID_HOME']) / 'build-tools/35.0.0')
    print('Approved guided Android Home selection and friendly training messages beta APK verified: signature, package, actual version, size and SHA-256.')


def publish(api):
    print('Publish preflight: load run-bound verified artifact')
    run_id = int(os.environ['GITHUB_RUN_ID'])
    artifacts = api.request(f'/repos/{REPO}/actions/runs/{run_id}/artifacts?per_page=100')
    matches = [a for a in artifacts.get('artifacts',[]) if a['name']=='verified-owner-approved-titan-training-015-beta-3' and not a['expired']]
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
    print('Published owner-requested Titan Trening 0.15.0-beta.3 with verified GitHub asset digests.')


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
