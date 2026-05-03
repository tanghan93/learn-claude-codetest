with open('mcp-server/server.py', 'rb') as f:
    c = f.read()
print(c[:3000].decode('utf-8', errors='replace'))
