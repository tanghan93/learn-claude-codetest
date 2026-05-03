"""Read and print all task files."""
import json
from pathlib import Path

tasks_dir = Path(r"D:\Pyprogram\learn-claude-codetest\agents\.team\tasks")
for f in sorted(tasks_dir.glob("*.json")):
    t = json.loads(f.read_text(encoding="utf-8"))
    print(f"Task #{t['id']}: {t['subject']}")
    print(f"  status={t['status']} owner='{t.get('owner','')}' blockedBy={t.get('blockedBy',[])}")
