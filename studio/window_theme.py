"""Theme the native Windows caption without replacing its window controls."""
import ctypes
import os
import re


def caption_attributes(settings):
    light = settings.get('theme') == 'light'
    colors = {'bg': '#edf1f4' if light else '#0d141b',
              'text': '#14212b' if light else '#f4f6f8',
              'line': '#c5d1d8' if light else '#333e47'}
    for key, value in (settings.get('theme_colors') or {}).items():
        if key in colors and isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value):
            colors[key] = value
    def rgb(value):
        return tuple(int(value[i:i+2], 16) for i in (1, 3, 5))
    def colorref(value):
        r, g, b = rgb(value)
        return r | (g << 8) | (b << 16)
    r, g, b = rgb(colors['bg'])
    dark = int(.2126*r + .7152*g + .0722*b < 128)
    return {20: dark, 34: colorref(colors['line']),
            35: colorref(colors['bg']), 36: colorref(colors['text'])}


def apply_titlebar(window, settings):
    """Windows 11 supports exact colors; older systems retain native fallback.

    DWM constants: https://learn.microsoft.com/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute
    Failure to style a caption must never interrupt playback or window creation.
    """
    if os.name != 'nt':
        return False
    try:
        handle = window.native.Handle.ToInt64()
        dwm = ctypes.WinDLL('dwmapi', use_last_error=True)
        set_attribute = dwm.DwmSetWindowAttribute
        set_attribute.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
        set_attribute.restype = ctypes.c_int32
        applied = False
        for attribute, value in caption_attributes(settings).items():
            data = ctypes.c_uint32(value)
            result = set_attribute(ctypes.c_void_p(handle), attribute,
                                   ctypes.byref(data), ctypes.sizeof(data))
            applied = (result == 0) or applied
        return applied
    except Exception:  # Includes a native window disposed during app shutdown.
        return False
