#!/usr/bin/env python3
"""Generate simple PWA icons as PNG using only stdlib."""

import struct
import zlib


def create_png(width: int, height: int, bg_color: tuple, text: str) -> bytes:
    """Create a minimal PNG with a solid background and centered text via SVG embedding.

    Since we can't render text to PNG without dependencies, we create a solid-color
    PNG icon. The actual icon appearance comes from the background color matching
    the app theme.
    """
    # Create raw pixel data (RGBA)
    r, g, b = bg_color
    row = b'\x00' + bytes([r, g, b, 255]) * width  # filter byte + pixels
    raw = row * height

    # Compress
    compressed = zlib.compress(raw)

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    # Build PNG
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', compressed)
    png += chunk(b'IEND', b'')
    return png


if __name__ == '__main__':
    bg = (15, 23, 42)  # #0f172a (app background)

    for size in [192, 512]:
        data = create_png(size, size, bg, '')
        fname = f'icon-{size}.png'
        with open(fname, 'wb') as f:
            f.write(data)
        print(f'Generated {fname} ({len(data)} bytes)')
