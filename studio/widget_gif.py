"""Bound GIF canvas, frame count and compressed blocks without rewriting animation."""
import struct
MAX_GIF = 20 * 1024 * 1024

def gif(data):
    if len(data)>MAX_GIF or len(data)<14 or data[:6] not in (b'GIF87a',b'GIF89a'):
        raise ValueError('Choose a valid GIF up to 20 MB.')
    w,h,packed=struct.unpack_from('<HHB',data,6)
    if not 1<=w<=1600 or not 1<=h<=1000 or w*h>1_000_000:
        raise ValueError('GIF canvas must be at most 1600 × 1000 and one million pixels.')
    pos=13;frames=0;pixels=0;global_table=bool(packed&128)
    def take(n):
        nonlocal pos
        if pos+n>len(data):raise ValueError('Truncated GIF background.')
        value=data[pos:pos+n];pos+=n;return value
    def blocks():
        while True:
            n=take(1)[0]
            if not n:return
            take(n)
    if global_table:take(3*(2**((packed&7)+1)))
    while pos<len(data):
        marker=take(1)[0]
        if marker==0x3b:
            if not frames or pos!=len(data):raise ValueError('Invalid GIF trailer.')
            return data
        if marker==0x21:
            label=take(1)[0]
            if label not in (0xf9,0xfe,0xff):raise ValueError('Unsupported GIF extension.')
            blocks()
        elif marker==0x2c:
            x,y,fw,fh,flags=struct.unpack('<HHHHB',take(9))
            if not fw or not fh or x+fw>w or y+fh>h:raise ValueError('GIF frame exceeds the canvas.')
            frames+=1;pixels+=w*h
            if frames>300 or pixels>60_000_000:raise ValueError('GIF is too complex. Use fewer/smaller frames (up to 300 frames, 60 million canvas pixels total).')
            if flags&128:take(3*(2**((flags&7)+1)))
            elif not global_table:raise ValueError('GIF color table is missing.')
            if not 2<=take(1)[0]<=8:raise ValueError('Invalid GIF compression.')
            blocks()
        else:raise ValueError('Invalid GIF block.')
    raise ValueError('Incomplete GIF background.')
