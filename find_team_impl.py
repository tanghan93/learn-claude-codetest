import os
import re

root = r'D:\Pyprogram\learn-claude-codetest'
for dirpath, dirnames, filenames in os.walk(root):
    # skip .venv
    if '.venv' in dirpath or '__pycache__' in dirpath:
        continue
    for fn in filenames:
        if fn.endswith('.py'):
            fp = os.path.join(dirpath, fn)
            try:
                with open(fp, 'rb') as f:
                    c = f.read()
                if b'TeammateManager' in c or b'spawn_teammate' in c or b'TEAM =' in c:
                    print(f'{fp}: contains TeammateManager/spawn_teammate/TEAM')
            except:
                pass
