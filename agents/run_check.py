"""Quick check script"""
import sys
sys.path.insert(0, r"D:\Pyprogram\learn-claude-codetest\agents")

from s11_autonomous_agentstest import TEAM, TASKS_DIR, scan_unclaimed_tasks
import json

print("Tasks dir:", TASKS_DIR)
tasks = list(TASKS_DIR.glob("*.json"))
print("Task files:", [f.name for f in tasks])

for f in sorted(TASKS_DIR.glob("*.json")):
    t = json.loads(f.read_text(encoding="utf-8"))
    print(f"  #{t['id']}: {t['subject']} [{t['status']}] blockedBy={t.get('blockedBy', [])} owner={t.get('owner','')}")

unclaimed = scan_unclaimed_tasks()
print(f"\nClaimable tasks: {[t['id'] for t in unclaimed]}")

print("\nTeammates:")
print(TEAM.list_all())
