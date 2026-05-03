#!/usr/bin/env python3
with open('agents/s11_autonomous_agentstest.py', 'rb') as f:
    c = f.read()
lines = c.split(b'\r\n')
for i, line in enumerate(lines):
    if b'DIR' in line and b'=' in line:
        print(f"Line {i}: {line.decode('utf-8', errors='replace')}")
    if b'TASKS' in line and b'=' in line:
        print(f"Line {i}: {line.decode('utf-8', errors='replace')}")
    if b'TEAM ' in line and b'=' in line:
        print(f"Line {i}: {line.decode('utf-8', errors='replace')}")
