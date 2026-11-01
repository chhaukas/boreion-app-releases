#!/usr/bin/env python3
"""One exact, owner-requested Superfrog TV audio beta APK. No arbitrary import or source-build claims."""
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

RELEASE_ID = 430800936
TAG = 'superfrog/v0.1.1-beta.5'
CERT = 'd078262a137f152143c5311ed882f82cff13652f9380d1f81058d43b2549f62d'
APPROVED = {'boreion-app.json': {'blob': '587348a557633b390465ed9d390671f6549da0ae', 'sha256': '3131871f3d54a146d01cee11269e2fdf2579f2f8e67cd9ce0e6a215d519a89ec', 'size': 1629}, 'fullscreen-phone.png': {'blob': '1e188d579d9884f16634e35fb53dffa7d5d36923', 'sha256': '89636fa9d21297f98cd46848df013a0ae7de1309220b53591c4f1353b4769e3e', 'size': 391959}, 'fullscreen-tv.png': {'blob': '55d25c72562eaa436c7e6dfa974d08dadf7a0573', 'sha256': 'e038169d6e01c6b26d09c3549d250aedfcb94bb37584c683e286fe9da3e0825f', 'size': 380362}, 'home.png': {'blob': '27ebcd21e1f40d8c973870073d1768f62faef888', 'sha256': '894149c0ec12f4b36a09b539ac0c047571a893357cd3c6199757fc8322a4a535', 'size': 76940}, 'icon.png': {'blob': '8153bdb1e3b6cac27c6e81be3102446d9370c836', 'sha256': 'b10e7daedc16904330774bb67ac71628af1902edd85f71943a0ce09e1bc1c19a', 'size': 46760}, 'normal-phone.png': {'blob': 'b8335431f4a1912fc742956092f0784b33b7b194', 'sha256': 'e2eee6c04b673ad8ce6fd8d1a5dfb2e0bebb28c3df446271baa398e114467a39', 'size': 354498}, 'normal-tv.png': {'blob': '9e266c94c45d1b327fb158af431e6a0f68434ab6', 'sha256': '589fd729eb5777b3869d37ab4e800d24288106dfc420647fc3336c346972ce78', 'size': 325196}, 'superfrog-0.1.1-beta.5.apk': {'blob': 'ba9a7c192337c3b7381c7b2ce6a46dea569005e9', 'sha256': 'ea400280fc8f94ed230b4f7565a16a7fc5c132b234063cc10d96e99597eff23d', 'size': 15038131}, 'tv-settings.png': {'blob': '9e2f03646e6dc206a5d180bd141404e5d7be54cf', 'sha256': 'e353882003bd734d705cf7f6ab05d2bb789bd7324d3eda26496d9a6333e08d9f', 'size': 77050}}


def files_valid(directory):
    root = Path(directory)
    require({p.name for p in root.iterdir()} == set(APPROVED))
    for name, expected in APPROVED.items():
        path = root / name
        require(path.is_file() and not path.is_symlink())
        data = path.read_bytes()
        require(len(data) == expected['size'] and hashlib.sha256(data).hexdigest() == expected['sha256'])
    manifest = json.loads((root / 'boreion-app.json').read_text())
    require(manifest['appId'] == 'superfrog' and manifest['version'] == '0.1.1-beta.5')
    require(manifest['metadata']['sourceVisible'] is False and manifest['metadata']['distribution']['public'] is True)
    require(manifest['metadata']['distribution']['signingCertificateSha256'] == CERT)
    require(manifest['apk']['sha256'] == APPROVED['superfrog-0.1.1-beta.5.apk']['sha256'])
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
    verify_apk(root / 'superfrog-0.1.1-beta.5.apk', {'certificateSha256':CERT,'androidPackage':'no.superfrog'}, '0.1.1-beta.5', Path('verifier-image.txt').read_text().strip(), Path(os.environ['ANDROID_HOME']) / 'build-tools/35.0.0')
    print('Approved TV audio beta APK verified: signature, package, actual version, size and SHA-256.')


def publish(api):
    print('Publish preflight: load run-bound verified artifact')
    run_id = int(os.environ['GITHUB_RUN_ID'])
    artifacts = api.request(f'/repos/{REPO}/actions/runs/{run_id}/artifacts?per_page=100')
    matches = [a for a in artifacts.get('artifacts',[]) if a['name']=='verified-owner-approved-superfrog-011-beta-5' and not a['expired']]
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
    print('Published owner-requested Superfrog 0.1.1-beta.5 with verified GitHub asset digests.')


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
