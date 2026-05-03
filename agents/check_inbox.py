"""Check inbox files"""
import sys
sys.path.insert(0, r"D:\Pyprogram\learn-claude-codetest\agents")
from s11_autonomous_agentstest import INBOX_DIR
import json

print("Inbox dir:", INBOX_DIR)
inboxes = list(INBOX_DIR.glob("*.jsonl"))
print(f"Found {len(inboxes)} inbox files")

for f in sorted(inboxes):
    content = f.read_text(encoding="utf-8")
    lines = [l for l in content.strip().split("\n") if l]
    print(f"\n{f.name}: {len(lines)} messages")
    for l in lines[:5]:
        try:
            msg = json.loads(l)
            print(f"  [{msg.get('type')}] from={msg.get('from')}: {str(msg.get('content',''))[:100]}")
        except:
            print(f"  (parse error): {l[:100]}")
