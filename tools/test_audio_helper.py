#!/usr/bin/env python3
"""TEST ONLY: deterministic PCM source; never selected by production code."""
import json, math, struct, sys, time
if sys.argv[1:]==['--list'] or (len(sys.argv)==3 and sys.argv[1]=='--follow-list'):
    print(json.dumps([{'pid':111,'started':'1001','name':'Spotify.exe'},{'pid':222,'started':'2002','name':'chrome.exe','peer':True}]+([{'pid':333,'started':'3003','name':'NextUp'}] if sys.argv[1]=='--follow-list' else [])))
elif len(sys.argv)==4 and sys.argv[1]=='--capture':
    if sys.argv[2:] not in [['111','1001'],['222','2002'],['333','3003']]:
        print('APP_CLOSED',file=sys.stderr,flush=True);sys.exit(2)
    print('READY',file=sys.stderr,flush=True)
    freq=100 if sys.argv[2]=='111' else 6000 if sys.argv[2]=='222' else 1500
    for block in range(100000):
        # Periodic silence verifies stopped bars without decorative fallback.
        amp=.45 if block%150<90 else 0
        data=bytearray()
        for i in range(1024):
            sample=int(amp*32767*math.sin(2*math.pi*freq*(block*1024+i)/48000))
            data.extend(struct.pack('<hh',sample,sample))
        sys.stdout.buffer.write(data);sys.stdout.buffer.flush();time.sleep(1024/48000)
else:sys.exit(64)
