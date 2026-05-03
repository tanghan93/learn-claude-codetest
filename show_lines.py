with open('agents/s11_autonomous_agentstest.py', 'rb') as f:
    c = f.read()
lines = c.split(b'\r\n')
for i in range(178, 190):
    print(f'{i}: {lines[i].decode("utf-8", errors="replace")}')
