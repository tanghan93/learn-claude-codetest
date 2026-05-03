with open('agents/s10_team_protocolstest.py', 'rb') as f:
    c = f.read()
lines = c.split(b'\r\n')
for i, line in enumerate(lines):
    decoded = line.decode('utf-8', errors='replace')
    if 'TASKS_DIR' in decoded or 'TASK_DIR' in decoded:
        print(f'{i}: {decoded}')
    if 'TEAM_DIR' in decoded and '=' in decoded:
        print(f'{i}: {decoded}')
    if 'TEAM =' in decoded:
        print(f'{i}: {decoded}')
