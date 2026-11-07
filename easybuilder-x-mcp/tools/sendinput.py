#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
sendinput.py - real system-level key injection (SendInput) for the foreground window.
author: hoverwu  version: 0.1.0
Usage: sendinput.py "<combo>"   combos: ctrl+s  ctrl+shift+s  alt+f4  enter  esc  f5  ctrl+c ...
"""
import sys, time, ctypes, ctypes.wintypes as wt

u = ctypes.windll.user32

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _fields_ = [("type", wt.DWORD), ("u", _U)]

KEYEVENTF_KEYUP = 0x0002

VK = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
      "enter": 0x0D, "esc": 0x1B, "tab": 0x09, "space": 0x20,
      "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
      "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
      "delete": 0x2E, "backspace": 0x08, "up": 0x26, "down": 0x28, "left": 0x25,
      "right": 0x27, "home": 0x24, "end": 0x23}
for ch in "abcdefghijklmnopqrstuvwxyz0123456789":
    VK[ch] = ord(ch.upper())

def key(vk, up=False):
    inp = INPUT(type=1)
    inp.u.ki.wVk = vk
    inp.u.ki.wScan = u.MapVirtualKeyW(vk, 0)
    inp.u.ki.dwFlags = KEYEVENTF_KEYUP if up else 0
    u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

def main():
    combo = sys.argv[1].lower().split("+")
    mods = [k for k in combo[:-1] if k in VK]
    mainkey = combo[-1]
    if mainkey not in VK:
        sys.stdout.write("unknown key: %s\n" % mainkey); return 2
    for m in mods:
        key(VK[m]); time.sleep(0.03)
    key(VK[mainkey]); time.sleep(0.03)
    key(VK[mainkey], True)
    for m in reversed(mods):
        key(VK[m], True); time.sleep(0.03)
    sys.stdout.write("sent %s\n" % "+".join(combo))
    return 0

if __name__ == "__main__":
    sys.exit(main())
