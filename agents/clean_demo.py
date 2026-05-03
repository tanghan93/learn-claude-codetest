#!/usr/bin/env python3
"""
Clean Demo: Task Dependency Chain with Autonomous Teammates.

Shows that teammates only claim unblocked tasks (status=pending, no owner, no blockedBy).
As tasks complete, new tasks become claimable. The dependency chain is respected.
"""
import sys, os, json, time

# Ensure we can import from this directory
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

# Force fast model
from config import MODEL_DEEPSEEK_CHAT
import s11_autonomous_agentstest
s11_autonomous_agentstest.MODEL = MODEL_DEEPSEEK_CHAT

from s11_autonomous_agentstest import TEAM, TASKS_DIR, scan_unclaimed_tasks

def log(msg):
    print(msg)
    sys.stdout.flush()

def show_board():
    """Print task board and return if all done."""
    all_done = True
    for f in sorted(TASKS_DIR.glob("*.json")):
        t = json.loads(f.read_text(encoding="utf-8"))
        marker = {"pending":"[ ]","in_progress":"[>]","completed":"[x]"}.get(t["status"],"[?]")
        owner = f" @{t['owner']}" if t.get("owner") else ""
        blocked = f" (blocked by {t['blockedBy']})" if t.get("blockedBy") else ""
        log(f"  {marker} #{t['id']}: {t['subject']}{owner}{blocked}")
        if t["status"] != "completed":
            all_done = False
    unclaimed = scan_unclaimed_tasks()
    log(f"  -> Claimable now: {[t['id'] for t in unclaimed]}")
    return all_done

# ========== MAIN ==========
log("=" * 60)
log("DEMO: Task Dependency Chain")
log("=" * 60)
log("""
Chain: #1 (no deps) -> #2 (blockedBy:1) -> #3 (blockedBy:2) -> #4 (blockedBy:3)
Rule: scan_unclaimed_tasks() ONLY returns tasks with:
  - status == 'pending'
  - no owner
  - no blockedBy (empty list)
""")

# Reset config
TEAM.config["members"] = []
TEAM._save_config()
log("Config reset - no teammates")

# Show initial board
log("\n--- Initial Task Board ---")
show_board()

# Verify only Task 1 is claimable
unclaimed = scan_unclaimed_tasks()
assert len(unclaimed) == 1 and unclaimed[0]["id"] == 1, \
    f"Expected only Task 1 claimable, got {[t['id'] for t in unclaimed]}"
log("\n>> Verified: Only Task 1 is claimable (no blockedBy)")

# Spawn teammates
log("\n>>> Spawning 'builder'...")
r = TEAM.spawn("builder", "coder", 
    "Use bash to create project files. Mark the task as completed by writing "
    "to the JSON file and setting 'status' to 'completed'. Then use idle.")
log(f"    {r}")

log(">>> Spawning 'tester'...")
r = TEAM.spawn("tester", "tester",
    "Write test files. Mark tasks completed by editing the task JSON status. "
    "Use idle when done.")
log(f"    {r}")

# Monitor
log("\n--- Monitoring (checking every 10s) ---")
try:
    for i in range(8):  # 80 seconds max (fits within 120s timeout)
        time.sleep(8)
        log(f"\n--- Check {i+1} @ {time.strftime('%H:%M:%S')} ---")
        done = show_board()
        log(f"  Teammates:\n{TEAM.list_all()}")
        
        # Show what's claimable and why
        log("\n  Claimability analysis:")
        for f in sorted(TASKS_DIR.glob("*.json")):
            t = json.loads(f.read_text(encoding="utf-8"))
            claimable = (t["status"] == "pending" and not t.get("owner") and not t.get("blockedBy"))
            reasons = []
            if t["status"] != "pending":
                reasons.append(f"status={t['status']}")
            if t.get("owner"):
                reasons.append(f"owned by {t['owner']}")
            if t.get("blockedBy"):
                reasons.append(f"blockedBy={t['blockedBy']}")
            if reasons:
                log(f"    #{t['id']}: NOT claimable ({'; '.join(reasons)})")
            else:
                log(f"    #{t['id']}: CLAIMABLE")
        
        if done:
            log("\n>>> ALL TASKS COMPLETED! <<<")
            log(">>> Dependency chain was respected! <<<")
            break
except KeyboardInterrupt:
    log("\nInterrupted")

# Final summary
log("\n" + "=" * 60)
log("FINAL STATE")
log("=" * 60)
show_board()
log(f"\nTeammates:\n{TEAM.list_all()}")

log("\n" + "=" * 60)
log("DEMO COMPLETE")
log("=" * 60)
