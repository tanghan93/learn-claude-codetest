#!/usr/bin/env python3
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('agents/s11_autonomous_agentstest.py', 'rb') as f:
    content = f.read()

old = b'        self.config_path = self.team_dir / "config.json"\r\n        self.threads = {}'
new = b'        self.config_path = self.team_dir / "config.json"\r\n        self.config = self._load_config()\r\n        self.threads = {}'

if old in content:
    content = content.replace(old, new, 1)
    with open('agents/s11_autonomous_agentstest.py', 'wb') as f:
        f.write(content)
    print('FIXED: Added self.config = self._load_config() to __init__')
else:
    print('Pattern not found')
    # Try different variations
    for pattern in [
        b'self.threads = {}',
        b'self.config_path',
        b'def __init__',
    ]:
        idx = content.find(pattern)
        if idx >= 0:
            print(f'Found {pattern} at position {idx}')
            print(content[idx:idx+200])
