#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read a strictly symbol-only x86_64 kernel-resource interface.

Normal implementation binaries must use defined exports instead. The caller
must authenticate the KDK/provider identity, OSKernelResource flag and every
offered name's definition in the matching KDK kernel. This does not admit a
private KPI or establish runtime collection inclusion.
"""
import struct


def interface_exports(data):
    if len(data) < 32:
        raise ValueError('Truncated kernel interface')
    fat = struct.unpack_from('>I', data)[0]
    if fat in (0xcafebabe, 0xcafebabf):
        count = struct.unpack_from('>I', data, 4)[0]
        width = 20 if fat == 0xcafebabe else 32
        if not 1 <= count <= 32 or 8 + width * count > len(data):
            raise ValueError('Invalid interface fat header')
        matches = []
        for i in range(count):
            at = 8 + width * i
            if width == 20:
                cpu, sub, offset, size, align = struct.unpack_from('>5I', data, at)
            else:
                cpu, sub, offset, size, align, reserved = struct.unpack_from('>IIQQII', data, at)
                if reserved:
                    raise ValueError('Unexpected interface fat reserved field')
            if offset < 8 + width * count or size < 32 or offset + size > len(data) or align > 31 or offset % (1 << align):
                raise ValueError('Invalid interface slice bounds')
            if (cpu, sub) == (0x1000007, 3):
                matches.append(data[offset:offset + size])
        if len(matches) != 1:
            raise ValueError('Missing or ambiguous x86_64 interface')
        data = matches[0]
    magic, cpu, sub, kind, count, length, flags, _reserved = struct.unpack_from('<8I', data)
    # The reviewed KDK uses a nonzero opaque reserved word here. It grants no
    # capability and is not interpreted as an address or an export identity.
    if (magic, cpu, sub, kind) != (0xfeedfacf, 0x1000007, 3, 11) or not (flags & 2):
        raise ValueError('Require an incremental-link x86_64 interface bundle')
    if count != 4 or 32 + length > len(data):
        raise ValueError('Unexpected symbol-interface load commands')
    offset, commands, table = 32, set(), None
    for _ in range(count):
        if offset + 8 > 32 + length:
            raise ValueError('Truncated interface load command')
        command, size = struct.unpack_from('<2I', data, offset)
        if command in commands or command not in {0x19, 2, 0x1b, 0x1d} or size < 8 or size % 8 or offset + size > 32 + length:
            raise ValueError('Unexpected or duplicate interface load command')
        commands.add(command)
        if command == 0x19:
            if size != 72:
                raise ValueError('Kernel interface contains sections')
            segment = data[offset + 8:offset + 24].rstrip(b'\0')
            start, size_bytes = struct.unpack_from('<2Q', data, offset + 40)
            sections = struct.unpack_from('<I', data, offset + 64)[0]
            if segment != b'__LINKEDIT' or sections or start + size_bytes > len(data):
                raise ValueError('Kernel interface is not symbol-only')
        elif command == 2:
            if size != 24:
                raise ValueError('Invalid interface symbol command')
            table = struct.unpack_from('<4I', data, offset + 8)
        offset += size
    if offset != 32 + length or table is None:
        raise ValueError('Invalid interface command extent')
    symoff, count, stroff, size = table
    if not 0 < count < 100000 or symoff < offset or symoff + count * 16 > len(data) or stroff < symoff + count * 16 or stroff + size > len(data):
        raise ValueError('Invalid interface symbol/string bounds')
    names = {}
    def string(index):
        if not 0 < index < size:
            raise ValueError('Invalid interface string index')
        end = data.find(b'\0', stroff + index, stroff + size)
        if end < 0:
            raise ValueError('Unterminated interface symbol')
        name = data[stroff + index:end].decode('ascii')
        if not name.startswith('_'):
            raise ValueError('Invalid interface symbol spelling')
        return name
    for i in range(count):
        index, kind, section, desc, value = struct.unpack_from('<IBBHQ', data, symoff + i * 16)
        if kind not in (1, 11) or section or (kind == 1 and value):
            raise ValueError('Require external references or explicit interface aliases')
        name = string(index)
        if name in names:
            raise ValueError('Invalid or duplicate interface symbol')
        names[name] = name if kind == 1 else string(value)
    return names
