"""Remove publisher credentials from an authorized prebuilt PyInstaller runtime.

This compatibility packaging tool requires the maintainers' existing runtime.
It does not reconstruct the original application from the current source tree.
The complete public account implementation is backend/public_account.py.
"""
from __future__ import annotations

import argparse
import dis
import marshal
from pathlib import Path
import struct
import types
import zlib


ACCOUNT_NAMES = {"_ACCOUNT_USERNAME", "_ACCOUNT_SALT_HEX", "_ACCOUNT_DIGEST_HEX"}


def nested_code(value):
    if isinstance(value, types.CodeType):
        return value
    if isinstance(value, bytes):
        try:
            decoded = marshal.loads(value)
        except Exception:
            return None
        if isinstance(decoded, types.CodeType):
            return decoded
    return None


def credential_constants(code):
    result = set()
    instructions = list(dis.get_instructions(code))
    for previous, current in zip(instructions, instructions[1:]):
        if (current.opname == "STORE_NAME" and current.argval in ACCOUNT_NAMES
                and previous.opname == "LOAD_CONST" and isinstance(previous.argval, str)
                and previous.argval):
            result.add(previous.argval)
    for value in code.co_consts:
        child = nested_code(value)
        if child is not None:
            result.update(credential_constants(child))
    return result


def scrub(code, forbidden):
    values = []
    for value in code.co_consts:
        child = nested_code(value)
        if child is not None:
            fixed = scrub(child, forbidden)
            values.append(marshal.dumps(fixed) if isinstance(value, bytes) else fixed)
        elif isinstance(value, str) and value in forbidden:
            values.append("")
        else:
            values.append(value)
    return code.replace(co_consts=tuple(values))


def patch_pyz(data):
    offset = struct.unpack("!i", data[8:12])[0]
    toc = marshal.loads(data[offset:])
    entries = list(toc.items()) if isinstance(toc, dict) else toc
    output = bytearray(data[:8] + b"\0" * 4)
    rebuilt = []
    forbidden = None
    for name, (kind, start, size) in entries:
        if not size:
            rebuilt.append((name, (kind, 0, 0)))
            continue
        compressed = data[start:start + size]
        if name == "app.ui2.licensing":
            code = marshal.loads(zlib.decompress(compressed))
            forbidden = credential_constants(code)
            if len(forbidden) != 3:
                raise ValueError("Expected exactly three legacy credential constants")
            clean = marshal.dumps(scrub(code, forbidden))
            source = (
                "import marshal as _public_marshal\n"
                f"exec(_public_marshal.loads({clean!r}), globals())\n"
                "import importlib.util as _public_util\n"
                "import os as _public_os\n"
                "import sys as _public_sys\n"
                "_public_spec = _public_util.spec_from_file_location('public_account', "
                "_public_os.path.join(_public_os.path.dirname(_public_sys.executable), 'public_account.py'))\n"
                "_public_module = _public_util.module_from_spec(_public_spec)\n"
                "_public_sys.modules['public_account'] = _public_module\n"
                "_public_spec.loader.exec_module(_public_module)\n"
                "_public_module.install_legacy(globals())\n"
            )
            compressed = zlib.compress(marshal.dumps(compile(source, "app/ui2/licensing.py", "exec")), 9)
        rebuilt.append((name, (kind, len(output), len(compressed))))
        output.extend(compressed)
    if forbidden is None:
        raise ValueError("Application licensing module not found")
    output[8:12] = struct.pack("!i", len(output))
    output.extend(marshal.dumps(rebuilt))
    return bytes(output), forbidden


def repack(executable: Path, webui: Path):
    data = executable.read_bytes()
    cookie_at = data.rfind(b"MEI\014\013\012\013\016")
    cookie = struct.unpack("!8sIIII64s", data[cookie_at:cookie_at + 88])
    magic, package_size, toc_offset, toc_size, python_version, python_dll = cookie
    base = cookie_at + 88 - package_size
    position = base + toc_offset
    payload = bytearray()
    records = []
    forbidden = None
    while position < base + toc_offset + toc_size:
        length, offset, size, unpacked, compression, kind = struct.unpack("!IIIIBc", data[position:position + 18])
        name = data[position + 18:position + length].rstrip(b"\0")
        content = data[base + offset:base + offset + size]
        if kind == b"z":
            content, forbidden = patch_pyz(zlib.decompress(content) if compression else content)
            unpacked = len(content)
            if compression:
                content = zlib.compress(content, 9)
        records.append((name, len(payload), len(content), unpacked, compression, kind))
        payload.extend(content)
        position += length
    if forbidden is None:
        raise ValueError("Missing PYZ container")
    toc = bytearray()
    for name, offset, size, unpacked, compression, kind in records:
        length = ((18 + len(name) + 1 + 15) // 16) * 16
        toc.extend(struct.pack("!IIIIBc", length, offset, size, unpacked, compression, kind))
        toc.extend((name + b"\0").ljust(length - 18, b"\0"))
    cookie = struct.pack("!8sIIII64s", magic, len(payload) + len(toc) + 88,
                         len(payload), len(toc), python_version, python_dll)
    executable.write_bytes(data[:base] + payload + toc + cookie)
    # Clear the old username prefill without logging any credential values.
    content = webui.read_bytes()
    for value in forbidden:
        content = content.replace(value.encode(), b"")
    webui.write_bytes(content)
    print("Sanitized legacy account constants; installed public local account adapter.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("webui", type=Path)
    arguments = parser.parse_args()
    repack(arguments.executable, arguments.webui)
