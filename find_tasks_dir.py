with open('agents/s11_autonomous_agentstest.py', 'rb') as f:
    c = f.read()
lines = c.split(b'\r\n')
for i, line in enumerate(lines):
    decoded = line.decode('utf-8', errors='replace')
    if ('TASKS_DIR' in decoded or 'TASK_DIR' in decoded) and '=' in decoded:
        print(f'{i}: {decoded}')
    if 'TASKS_DIR' in decoded and 'Path' in decoded:
        print(f'{i}: {decoded}')
    if 'TASKS_DIR' in decoded and 'mkdir' in decoded:
        print(f'{i}: {decoded}')
    if 'TASKS_DIR' in decoded and 'glob' in decoded:
        print(f'{i}: {decoded}')
