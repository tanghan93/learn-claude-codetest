#!/usr/bin/env python3
"""Reset state and run the dep chain demo with fast model."""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(__file__))

# Force fast model
from config import MODEL_DEEPSEEK_CHAT
import s11_autonomous_agentstest
s11_autonomous_agentstest.MODEL = MODEL_DEEPSEEK_CHAT

from s11_autonomous_agentstest import TEAM, TASKS_DIR, scan_unclaimed_tasks

# Reset
TEAM.config["members"] = []
TEAM._save_config()
print("Config reset")

# Show tasks
for f in sorted(TASKS_DIR.glob("*.json")):
    t = json.loads(f.read_text())
    print(f"  [{t['status']}] #{t['id']}: {t['subject']} blockedBy={t.get('blockedBy',[])}")

unclaimed = scan_unclaimed_tasks()
print(f"Claimable: {[t['id'] for t in unclaimed]}")

# Spawn
print("\nSpawning builder...")
r = TEAM.spawn("builder", "coder", 
    "Use bash to create project files. Mark task completed by editing the JSON file status to 'completed'.")
print(f"  {r}")
time.sleep(2)

print("Spawning tester...")
r = TEAM.spawn("tester", "tester",
    "Write tests. Mark task completed by editing the JSON file status to 'completed'.")
print(f"  {r}")

# Monitor
print("\n=== Monitoring (checking every 8s) ===")
for i in range(8):
    time.sleep(8)
    print(f"\n--- Check {i+1} ---")
    for f in sorted(TASKS_DIR.glob("*.json")):
        t = json.loads(f.read_text())
        marker = {"pending":"[ ]","in_progress":"[>]","completed":"[x]"}.get(t["status"],"[?]")
        owner = f" @{t['owner']}" if t.get("owner") else ""
        blocked = f" (blocked by {t['blockedBy']})" if t.get("blockedBy") else ""
        print(f"  {marker} #{t['id']}: {t['subject']}{owner}{blocked}")
    print(f"  Claimable: {[t['id'] for t in scan_unclaimed_tasks()]}")
    print(TEAM.list_all())
    
    all_done = all(json.loads(f.read_text())["status"] == "completed" for f in TASKS_DIR.glob("*.json"))
    if all_done:
        print("\n*** ALL COMPLETED! ***")
        break

print("\n=== FINAL ===")
for f in sorted(TASKS_DIR.glob("*.json")):
    t = json.loads(f.read_text())
    print(f"  [{t['status']}] #{t['id']}: {t['subject']} @{t.get('owner','')}")
print(TEAM.list_all())
