#!/usr/bin/env python3
"""Generate simple PWA icons as PNG using only stdlib.

Creates dark-themed icons with a wave-like accent stripe for visual identity.
"""

import struct
import zlib


def create_png(width: int, height: int, bg_color: tuple) -> bytes:
    """Create a minimal PNG with a solid background and accent stripe."""
    r, g, b = bg_color
    # Accent color: #93c5fd (light blue)
    ar, ag, ab = 147, 197, 253

    rows = []
    for y in range(height):
        row = b'\x00'  # filter byte
        for x in range(width):
            # Draw a wave-like accent stripe in the middle third
            mid = height // 2
            # Simple sine-ish wave using integer math
            wave_offset = (x * 8 // width) % 3 - 1  # -1, 0, or 1
            stripe_y = mid + wave_offset * (height // 20)
            dist = abs(y - stripe_y)
            stripe_width = height // 12

            if dist < stripe_width:
                row += bytes([ar, ag, ab, 255])
            else:
                row += bytes([r, g, b, 255])
        rows.append(row)

    raw = b''.join(rows)
    compressed = zlib.compress(raw)

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', compressed)
    png += chunk(b'IEND', b'')
    return png


if __name__ == '__main__':
    bg = (15, 23, 42)  # #0f172a (app background)

    for size in [192, 512]:
        data = create_png(size, size, bg)
        fname = f'icon-{size}.png'
        with open(fname, 'wb') as f:
            f.write(data)
        print(f'Generated {fname} ({len(data)} bytes)')
