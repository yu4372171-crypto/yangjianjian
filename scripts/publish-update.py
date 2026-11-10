"""Publish signed update manifests for the in-app updater.

The Ed25519 private key stays with the publisher (outside the customer
package). Customers receive only the public key through update-channel.json.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.parse

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, NoEncryption, PrivateFormat

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT
DEFAULT_OUT = ROOT / 'artifacts/updates'
PRODUCT = 'yangyu-autoedit'


def _raw_private(private):
    return private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())


def _raw_public(private):
    return private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def _write_keypair(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    private = Ed25519PrivateKey.generate()
    private_path = directory / 'update-publisher-private.key'
    public_path = directory / 'update-publisher-public.key'
    if private_path.exists() or public_path.exists():
        raise SystemExit('Key files already exist; refusing to overwrite them.')
    private_path.write_text(base64.b64encode(_raw_private(private)).decode(), 'ascii')
    public_path.write_text(base64.b64encode(_raw_public(private)).decode(), 'ascii')
    print(json.dumps({'private': str(private_path), 'public': str(public_path),
                      'publicKey': base64.b64encode(_raw_public(private)).decode()}, ensure_ascii=False))


def _load_private(path):
    value = Path(path).read_text('ascii').strip()
    return Ed25519PrivateKey.from_private_bytes(base64.b64decode(value, validate=True))


def _version(value):
    if not re.fullmatch(r'\d{1,5}(?:\.\d{1,5}){3}', value):
        raise SystemExit('Version must look like 2026.10.18.7')
    return value


def _channel(path):
    channel = json.loads(Path(path).read_text('utf-8'))
    if channel.get('schema') != 1 or not channel.get('publicKey') or not channel.get('channel'):
        raise SystemExit('update-channel.json is missing or incomplete')
    return channel


def init_channel(args):
    app_root = Path(args.app_root)
    public = args.public
    if Path(public).is_file():
        public = Path(public).read_text('ascii').strip()
    base64.b64decode(public, validate=True)
    if args.manifest_url and not re.match(r'^https?://', args.manifest_url):
        raise SystemExit('manifest-url must start with https:// or http://')
    target = app_root / 'update-channel.json'
    try:
        channel = json.loads(target.read_text('utf-8')) if target.is_file() else {}
    except (OSError, ValueError):
        channel = {}
    if not isinstance(channel, dict):
        channel = {}
    channel.update({
        'schema': 1, 'channel': 'stable',
        'manifestUrl': args.manifest_url or '', 'publicKey': public,
    })
    target.write_text(json.dumps(channel, ensure_ascii=False, indent=2) + '\n', 'utf8')
    print(f'channel written: {target}')


def publish(args):
    channel = _channel(Path(getattr(args, 'app_root', APP)) / 'update-channel.json')
    installer = Path(args.installer).resolve()
    if not installer.is_file():
        raise SystemExit('installer does not exist: ' + str(installer))
    if installer.suffix.lower() != '.exe' or not 2 <= installer.stat().st_size <= 2 * 1024 ** 3:
        raise SystemExit('Expected a Windows installer between 2 bytes and 2 GiB.')
    with installer.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise SystemExit('Installer is not a Windows executable.')
    private = _load_private(args.private_key)
    if base64.b64encode(_raw_public(private)).decode() != channel['publicKey']:
        raise SystemExit('Publisher key does not match the public channel; release was not signed.')
    version = _version(args.version)
    notes = Path(args.notes_file).read_text('utf8') if args.notes_file else (args.notes or '')
    base_url = (args.url or '').rstrip('/')
    url = base_url + '/' + urllib.parse.quote(installer.name, safe='') if base_url else ''
    feed = urllib.parse.urlsplit(channel.get('manifestUrl', ''))
    package = urllib.parse.urlsplit(url)
    for parsed in (feed, package):
        if (not parsed.hostname or parsed.username is not None or parsed.password is not None
                or parsed.fragment or parsed.query or '\\' in parsed.geturl()
                or any(ord(char) < 33 for char in parsed.geturl())
                or (parsed.scheme != 'https' and not (
                    parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1')))):
            raise SystemExit('Feed and download base must use safe HTTPS URLs.')
    if ((feed.scheme, feed.hostname, feed.port or (443 if feed.scheme == 'https' else 80))
            != (package.scheme, package.hostname, package.port or (443 if package.scheme == 'https' else 80))):
        raise SystemExit('Installer must use the configured feed origin.')
    if len(notes) > 16000:
        raise SystemExit('Release notes exceed the customer verifier limit.')
    size = installer.stat().st_size
    digest = hashlib.sha256()
    with installer.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    payload = {
        'schema': 1, 'product': PRODUCT, 'channel': channel['channel'], 'version': version,
        'url': url, 'size': size, 'sha256': digest.hexdigest(), 'notes': notes,
        'publishedAt': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf8')
    envelope = {'payload': payload, 'signature': base64.b64encode(private.sign(raw)).decode()}
    out = Path(args.out) if args.out else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)
    (out / 'latest.json').write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + '\n', 'utf8')
    (out / f'manifest-{version}.json').write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + '\n', 'utf8')
    print(json.dumps({'version': version, 'size': size, 'sha256': digest.hexdigest(),
                      'manifest': str(out / 'latest.json'), 'url': url}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    key = sub.add_parser('gen-key', help='create a new Ed25519 publisher key pair')
    key.add_argument('--out', required=True, help='private directory outside the repository')
    channel = sub.add_parser('init-channel', help='write the customer public channel file')
    channel.add_argument('--app-root', default=str(APP))
    channel.add_argument('--public', required=True, help='base64 public key or its file')
    channel.add_argument('--manifest-url', default='')
    pub = sub.add_parser('publish', help='sign an installer into latest.json')
    pub.add_argument('--installer', required=True)
    pub.add_argument('--version', required=True)
    pub.add_argument('--private-key', required=True)
    pub.add_argument('--app-root', default=str(APP), help='directory containing update-channel.json')
    pub.add_argument('--url', default='')
    pub.add_argument('--notes', default='')
    pub.add_argument('--notes-file', default='')
    pub.add_argument('--out', default='')
    args = parser.parse_args()
    if args.command == 'gen-key':
        _write_keypair(args.out)
    elif args.command == 'init-channel':
        init_channel(args)
    else:
        publish(args)


if __name__ == '__main__':
    main()
