"""Minimal readers for PWG raster, CUPS raster v1/v2/v3 and Apple raster (URF).

Only what the comparator needs: per-page header fields and an RGB image.
"""

import struct

import numpy as np

HEADER_SIZE = 1796

# (name, byte offset) of the uint32 fields in cups_page_header2_t.
HEADER_FIELDS = [
    ("AdvanceDistance", 256), ("AdvanceMedia", 260), ("Collate", 264), ("CutMedia", 268),
    ("Duplex", 272), ("HWResolutionX", 276), ("HWResolutionY", 280),
    ("ImagingBBoxLeft", 284), ("ImagingBBoxBottom", 288), ("ImagingBBoxRight", 292), ("ImagingBBoxTop", 296),
    ("InsertSheet", 300), ("Jog", 304), ("LeadingEdge", 308), ("MarginLeft", 312), ("MarginBottom", 316),
    ("ManualFeed", 320), ("MediaPosition", 324), ("MediaWeight", 328), ("MirrorPrint", 332),
    ("NegativePrint", 336), ("NumCopies", 340), ("Orientation", 344), ("OutputFaceUp", 348),
    ("PageSizeW", 352), ("PageSizeH", 356), ("Separations", 360), ("TraySwitch", 364), ("Tumble", 368),
    ("cupsWidth", 372), ("cupsHeight", 376), ("cupsMediaType", 380), ("cupsBitsPerColor", 384),
    ("cupsBitsPerPixel", 388), ("cupsBytesPerLine", 392), ("cupsColorOrder", 396), ("cupsColorSpace", 400),
    ("cupsCompression", 404), ("cupsRowCount", 408), ("cupsRowFeed", 412), ("cupsRowStep", 416),
    ("cupsNumColors", 420),
    # PWG 5102.4 re-uses cupsInteger[] for these.
    ("TotalPageCount", 452), ("CrossFeedTransform", 456), ("FeedTransform", 460),
]
HEADER_STRINGS = [("MediaClass", 0), ("MediaColor", 64), ("MediaType", 128), ("OutputType", 192)]

# cups_cspace_t values that store "ink" (0 = white) rather than light.
INK_SPACES = {3, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16}   # K, CMY(K), ...

URF_COLORSPACES = {0: "sgray", 1: "srgb", 3: "srgb", 4: "adobergb", 6: "cmyk"}


class RasterError(Exception):
    pass


def _decode_rle(data, pos, unit, height, line_bytes, fill):
    """PWG/CUPS-v2/URF compression: line-repeat byte, then pixel packets."""
    out = bytearray()
    y = 0
    white_line = bytes([fill]) * line_bytes
    while y < height:
        if pos >= len(data):
            raise RasterError("truncated raster data")
        repeat = data[pos] + 1
        pos += 1
        line = bytearray()
        while len(line) < line_bytes:
            if pos >= len(data):
                raise RasterError("truncated raster line")
            n = data[pos]
            pos += 1
            if n == 128:
                line += white_line[len(line):]
            elif n < 128:
                line += data[pos:pos + unit] * (n + 1)
                pos += unit
            else:
                count = (257 - n) * unit
                line += data[pos:pos + count]
                pos += count
        line = bytes(line[:line_bytes])
        out += line * min(repeat, height - y)
        y += repeat
    return bytes(out), pos


def _to_rgb(pixels, width, height, bpc, bpp, cspace):
    """Turn packed pixel bytes into an HxWx3 uint8 array."""
    if bpp == 1:
        bits = np.unpackbits(np.frombuffer(pixels, np.uint8).reshape(height, -1), axis=1)[:, :width]
        on, off = (0, 255) if cspace in INK_SPACES else (255, 0)
        gray = np.where(bits == 1, on, off).astype(np.uint8)
        return np.repeat(gray[:, :, None], 3, axis=2)

    arr = np.frombuffer(pixels, np.uint8)
    if bpc == 16:
        arr = arr.reshape(-1, 2)[:, 0]          # big-endian high byte
    channels = max(1, bpp // bpc)
    arr = arr[: width * height * channels].reshape(height, width, channels)

    if channels == 1:
        gray = 255 - arr[:, :, 0] if cspace in INK_SPACES else arr[:, :, 0]
        return np.repeat(gray[:, :, None], 3, axis=2)
    if channels == 3:
        return (255 - arr) if cspace in INK_SPACES else arr.copy()
    if channels == 4:                            # CMYK, naive conversion
        c, m, y, k = (arr[:, :, i].astype(np.uint16) for i in range(4))
        return np.stack([255 - np.minimum(255, c + k), 255 - np.minimum(255, m + k),
                         255 - np.minimum(255, y + k)], axis=2).astype(np.uint8)
    raise RasterError(f"unsupported channel count {channels}")


def _read_cups(data, big_endian, version):
    fmt = ">I" if big_endian else "<I"
    pages, pos = [], 4
    while pos + HEADER_SIZE <= len(data):
        raw = data[pos:pos + HEADER_SIZE]
        pos += HEADER_SIZE
        header = {name: struct.unpack_from(fmt, raw, off)[0] for name, off in HEADER_FIELDS}
        for name, off in HEADER_STRINGS:
            header[name] = raw[off:off + 64].split(b"\0", 1)[0].decode("latin-1")

        w, h = header["cupsWidth"], header["cupsHeight"]
        bpc, bpp, bpl = header["cupsBitsPerColor"], header["cupsBitsPerPixel"], header["cupsBytesPerLine"]
        if not (w and h and bpp and bpl):
            raise RasterError("invalid raster header")
        if header["cupsColorOrder"] != 0:
            raise RasterError("only chunky raster is supported")

        if version == 2:
            fill = 0 if header["cupsColorSpace"] in INK_SPACES else 255
            pixels, pos = _decode_rle(data, pos, max(1, bpp // 8), h, bpl, fill)
        else:
            size = bpl * h
            pixels, pos = data[pos:pos + size], pos + size
            if len(pixels) < size:
                raise RasterError("truncated raster data")

        pages.append({"header": header, "image": _to_rgb(pixels, w, h, bpc, bpp, header["cupsColorSpace"])})
    return pages


def _read_urf(data):
    if len(data) < 12:
        raise RasterError("truncated URF")
    count = struct.unpack_from(">I", data, 8)[0]
    pages, pos = [], 12
    for _ in range(count):
        if pos + 32 > len(data):
            raise RasterError("truncated URF page header")
        bpp, cs, duplex, quality = data[pos], data[pos + 1], data[pos + 2], data[pos + 3]
        w, h, res = struct.unpack_from(">III", data, pos + 12)
        pos += 32
        unit = bpp // 8
        header = {"cupsBitsPerPixel": bpp, "URFColorSpace": cs, "Duplex": duplex, "URFQuality": quality,
                  "cupsWidth": w, "cupsHeight": h, "HWResolutionX": res, "HWResolutionY": res}
        pixels, pos = _decode_rle(data, pos, unit, h, w * unit, 255)
        cspace = 3 if URF_COLORSPACES.get(cs) == "cmyk" else 19
        pages.append({"header": header, "image": _to_rgb(pixels, w, h, 8, bpp, cspace)})
    return pages


def read_raster(path):
    """Return a list of {"header": dict, "image": HxWx3 uint8} per page."""
    data = open(path, "rb").read()
    magic = data[:4]
    if data[:8] == b"UNIRAST\0":
        return _read_urf(data)
    if magic in (b"RaS2", b"2SaR"):
        return _read_cups(data, magic == b"RaS2", 2)
    if magic in (b"RaS3", b"3SaR", b"RaSt", b"tSaR"):
        return _read_cups(data, magic in (b"RaS3", b"RaSt"), 3)
    raise RasterError(f"unknown raster magic {magic!r}")
