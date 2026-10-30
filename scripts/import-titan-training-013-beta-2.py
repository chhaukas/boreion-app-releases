#!/usr/bin/env python3
"""One exact, owner-requested Titan Trening bounded active direct motor test beta APK. No arbitrary import or source-build claims."""
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
from central import API, REPO, NoRedirect, require, safe_extract, verify_apk

RELEASE_ID = 429212131
TAG = 'chhaukas-titan-trening/v0.13.0-beta.2'
CERT = '1224fbfd595c3dfef8aafbda43f154fa0a7a7770c8130f2e1e640ca75fb6e030'
APPROVED = {'boreion-app.json': {'blob': '812136421540239f7bdbb049441b16fa4cc2835a', 'sha256': 'a7f1a7ec6e73e3a3011496ebc6a4bc8898630fa6fa5cf2587d4abbf563025f93', 'size': 2695}, 'chhaukas-titan-trening-0.13.0-beta.2.apk': {'blob': '4953e9f06ee443e96afa13cb0f776cdab33d8c18', 'sha256': 'f81ebdada0bd7ceeca5baddb7e270df38ae61b5a03ae70b1c390792755369896', 'size': 2116334}}


def files_valid(directory):
    root = Path(directory)
    require({p.name for p in root.iterdir()} == set(APPROVED))
    for name, expected in APPROVED.items():
        path = root / name
        require(path.is_file() and not path.is_symlink())
        data = path.read_bytes()
        require(len(data) == expected['size'] and hashlib.sha256(data).hexdigest() == expected['sha256'])
    manifest = json.loads((root / 'boreion-app.json').read_text())
    require(manifest['appId'] == 'chhaukas-titan-trening' and manifest['version'] == '0.13.0-beta.2')
    require(manifest['metadata']['sourceVisible'] is False and manifest['metadata']['distribution']['public'] is True)
    require(manifest['metadata']['distribution']['signingCertificateSha256'] == CERT)
    require(manifest['apk']['sha256'] == APPROVED['chhaukas-titan-trening-0.13.0-beta.2.apk']['sha256'])
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
    verify_apk(root / 'chhaukas-titan-trening-0.13.0-beta.2.apk', {'certificateSha256':CERT,'androidPackage':'no.titan.trening'}, '0.13.0-beta.2', Path('verifier-image.txt').read_text().strip(), Path(os.environ['ANDROID_HOME']) / 'build-tools/35.0.0')
    print('Approved bounded active direct motor test beta APK verified: signature, package, actual version, size and SHA-256.')


def publish(api):
    run_id = int(os.environ['GITHUB_RUN_ID'])
    artifacts = api.request(f'/repos/{REPO}/actions/runs/{run_id}/artifacts?per_page=100')
    matches = [a for a in artifacts.get('artifacts',[]) if a['name']=='verified-owner-approved-titan-training-013-beta-2' and not a['expired']]
    require(len(matches)==1)
    a=matches[0]
    binding=a.get('workflow_run',{})
    require(binding.get('id')==run_id and binding.get('head_sha')==os.environ['GITHUB_SHA'] and binding.get('repository_id')==int(os.environ['GITHUB_REPOSITORY_ID']))
    api.download(f'/repos/{REPO}/actions/artifacts/{a["id"]}/zip','verified-import.zip',a.get('digest'))
    safe_extract('verified-import.zip','verified-import')
    manifest=files_valid('verified-import')
    release=api.request(f'/repos/{REPO}/releases/{RELEASE_ID}')
    require(release and release.get('tag_name')==TAG and release.get('draft') is True and release.get('prerelease') is True)
    require(release.get('assets')==[], 'Draft is not empty; no automatic overwrite')
    blocks=re.findall(r'\[boreion-app\]([\s\S]*?)\[/boreion-app\]',release['body'])
    require(len(blocks)==1 and json.loads(blocks[0])==manifest)
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
    print('Published owner-requested Titan Trening 0.13.0-beta.2 with verified GitHub asset digests.')


if __name__ == '__main__':
    try:
        require(os.environ['GITHUB_REPOSITORY']==REPO and os.environ['GITHUB_REF']=='refs/heads/main' and os.environ['GITHUB_ACTOR_ID']=='338504245' and os.environ['GITHUB_EVENT_NAME']=='workflow_dispatch')
        api=API(os.environ['GH_TOKEN'])
        if sys.argv[1]=='verify': verify(api)
        elif sys.argv[1]=='publish': publish(api)
        else: raise ValueError('Unknown operation')
    except Exception:
        print('Approved manual import stopped; no automatic overwrite or cleanup.',file=sys.stderr)
        sys.exit(1)
