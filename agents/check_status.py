"""Check current task status"""
import sys
sys.path.insert(0, r"D:\Pyprogram\learn-claude-codetest\agents")

from s11_autonomous_agentstest import TEAM, TASKS_DIR, scan_unclaimed_tasks, BUS
import json

print("=== TASK BOARD ===")
for f in sorted(TASKS_DIR.glob("*.json")):
    t = json.loads(f.read_text(encoding="utf-8"))
    marker = {"pending":"[ ]","in_progress":"[>]","completed":"[x]"}.get(t["status"],"[?]")
    owner = f" @{t['owner']}" if t.get("owner") else ""
    blocked = f" (blocked by {t['blockedBy']})" if t.get("blockedBy") else ""
    print(f"  {marker} #{t['id']}: {t['subject']}{owner}{blocked}")

unclaimed = scan_unclaimed_tasks()
print(f"\nClaimable now: {[t['id'] for t in unclaimed]}")

print("\n=== TEAMMATES ===")
print(TEAM.list_all())

print("\n=== LEAD INBOX ===")
msgs = BUS.read_inbox("lead")
if msgs:
    for m in msgs:
        print(f"  [{m.get('type','?')}] from={m.get('from','?')}: {m.get('content','')[:100]}")
else:
    print("  (empty)")
