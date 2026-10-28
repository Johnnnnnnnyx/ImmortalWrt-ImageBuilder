"""Reset only a saved disposable guest's overlay for diagnostic re-use, never release."""
import gzip
import hashlib
from pathlib import Path
import shutil
import struct
import sys

source, target = map(Path, sys.argv[1:])
raw = target.with_suffix('')
with gzip.open(source, 'rb') as reader, raw.open('wb') as writer:
    shutil.copyfileobj(reader, writer)
with raw.open('r+b') as disk:
    disk.seek(512)
    header = disk.read(92)
    assert header[:8] == b'EFI PART'
    table = struct.unpack_from('<Q', header, 72)[0] * 512
    entry_size = struct.unpack_from('<I', header, 84)[0]
    disk.seek(table + entry_size)
    entry = disk.read(entry_size)
    first, last = struct.unpack_from('<QQ', entry, 32)
    assert first == 66048 and last - first + 1 == 2097152
    disk.seek(first * 512)
    superblock = disk.read(96)
    assert superblock[:4] == b'hsqs'
    used = struct.unpack_from('<Q', superblock, 40)[0]
    start = first * 512 + (used + 65535) // 65536 * 65536
    end = (last + 1) * 512
    disk.seek(0)
    prefix_hash = hashlib.sha256(disk.read(start)).hexdigest()
    disk.seek(end)
    tail = disk.read()
    disk.seek(start)
    remaining = end - start
    while remaining:
        count = min(remaining, 1024 * 1024)
        disk.write(bytes(count))
        remaining -= count
    disk.seek(0)
    assert hashlib.sha256(disk.read(start)).hexdigest() == prefix_hash
    disk.seek(end)
    assert disk.read() == tail
with raw.open('rb') as reader, gzip.open(target, 'wb', compresslevel=1) as writer:
    shutil.copyfileobj(reader, writer)
print(f'DIAGNOSTIC ONLY: immutable prefix SHA256 {prefix_hash}; GPT and ROM preserved')
