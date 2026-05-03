with open('mcp-server/server.py', 'rb') as f:
    c = f.read()
# Find spawn_teammate
idx = c.find(b'spawn_teammate')
if idx >= 0:
    print(c[idx:idx+2000].decode('utf-8', errors='replace'))
else:
    print("spawn_teammate not found")
    # Find all @server.tool
    parts = c.split(b'@server.tool()')
    print(f"Found {len(parts)-1} tools")
    for i, p in enumerate(parts[1:], 1):
        # extract function name
        start = p.find(b'async def ')
        if start >= 0:
            end = p.find(b'(', start)
            print(f"Tool {i}: {p[start+10:end].decode('utf-8', errors='replace')}")
