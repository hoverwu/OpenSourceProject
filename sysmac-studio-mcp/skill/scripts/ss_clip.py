"""ss_clip.py - inspect / save / replay the Sysmac custom clipboard formats. ELEVATED.

  ss_clip.py list                      enumerate every clipboard format + size
  ss_clip.py dump <formatName> <file>  save one format to a binary file
  ss_clip.py set  <formatName> <file>  put it back on the clipboard

Sysmac writes two custom binary formats (do not try to parse them):
  Omron.SolutionEntityClipboardFormatter   one entity   (~50 KB, id 49713 on 1.68)
  Omron.SolutionMultipleRootEntites        many entities (multi-select copy)
Use 'list' to prove whether 编辑>复制 actually produced data - an ENABLED menu item
does not mean the copy happened.
"""
import sys
import ctypes
import ctypes.wintypes as wt

um = ctypes.windll.user32
k32 = ctypes.windll.kernel32
k32.GlobalSize.argtypes = [ctypes.c_void_p]
k32.GlobalSize.restype = ctypes.c_size_t
k32.GlobalLock.argtypes = [ctypes.c_void_p]
k32.GlobalLock.restype = ctypes.c_void_p
k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
um.RegisterClipboardFormatW.restype = wt.UINT
um.GetClipboardData.argtypes = [wt.UINT]
um.GetClipboardData.restype = ctypes.c_void_p
um.SetClipboardData.argtypes = [wt.UINT, ctypes.c_void_p]
um.SetClipboardData.restype = ctypes.c_void_p


def read_fmt(fid):
    h = um.GetClipboardData(fid)
    if not h:
        return None
    size = k32.GlobalSize(h)
    p = k32.GlobalLock(h)
    try:
        return ctypes.string_at(p, size)
    finally:
        k32.GlobalUnlock(h)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1].lower()
    if not um.OpenClipboard(None):
        print('OpenClipboard failed (another app holds it)')
        return 1
    try:
        if cmd == 'list':
            f = 0
            total = 0
            while True:
                f = um.EnumClipboardFormats(f)
                if f == 0:
                    break
                buf = ctypes.create_unicode_buffer(512)
                n = um.GetClipboardFormatNameW(f, buf, 512)
                h = um.GetClipboardData(f)
                size = k32.GlobalSize(h) if h else 0
                total += 1
                print(f"fmt={f:<6} name='{buf.value if n else ''}' size={size}")
            print(f'formats={total}')
            return 0

        if len(sys.argv) < 4:
            print('need <formatName> <file>')
            return 2
        name, path = sys.argv[2], sys.argv[3]
        fid = um.RegisterClipboardFormatW(name)
        if cmd == 'dump':
            raw = read_fmt(fid)
            if raw is None:
                print(f'no data for {name} (id={fid})')
                return 2
            with open(path, 'wb') as fh:
                fh.write(raw)
            print(f'wrote {len(raw)} bytes -> {path}')
            return 0

        if cmd == 'set':
            with open(path, 'rb') as fh:
                raw = fh.read()
            buf = ctypes.create_string_buffer(raw, len(raw))
            if not um.SetClipboardData(fid, ctypes.cast(buf, ctypes.c_void_p)):
                print('SetClipboardData failed')
                return 3
            print(f'set {len(raw)} bytes as {name} (id={fid})')
            return 0

        print('unknown command', cmd)
        return 2
    finally:
        um.CloseClipboard()


if __name__ == '__main__':
    sys.exit(main())
