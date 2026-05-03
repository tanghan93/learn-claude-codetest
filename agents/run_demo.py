#!/usr/bin/env python3
"""
Demo: Task dependency chain with autonomous teammates.

Creates tasks with dependencies and spawns autonomous teammates.
The teammates only claim tasks that aren't blocked, demonstrating
dependency ordering.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import json
import time
import threading

from s11_autonomous_agentstest import TEAM, TASKS_DIR, BUS, scan_unclaimed_tasks, claim_task

def print_board():
    """Print current task board status."""
    tasks = []
    for f in sorted(TASKS_DIR.glob("*.json")):
        t = json.loads(f.read_text(encoding="utf-8"))
        tasks.append(t)
    
    print("\n" + "="*60)
    print("  TASK BOARD")
    print("="*60)
    for t in tasks:
        marker = {"pending":"[ ]","in_progress":"[>]","completed":"[x]"}.get(t["status"],"[?]")
        owner = f"  @{t['owner']}" if t.get("owner") else ""
        blocked = f"  (blocked by {t['blockedBy']})" if t.get("blockedBy") else ""
        print(f"  {marker} #{t['id']}: {t['subject']}{owner}{blocked}")
    
    unclaimed = scan_unclaimed_tasks()
    print(f"\n  Claimable now: {[t['id'] for t in unclaimed]}")
    print("="*60)
    
    # Check if all completed
    if all(t["status"] == "completed" for t in tasks):
        print("\n  *** ALL TASKS COMPLETED! ***\n")
        return True
    return False

def main():
    print("\n" + "="*60)
    print("  DEMO: Task Dependency Chain")
    print("="*60)
    print("""
  Task 1: Plan architecture          (no deps)
  Task 2: Write core module          (blocked by Task 1)
  Task 3: Write tests                (blocked by Task 2)
  Task 4: Create documentation       (blocked by Task 3)

  Key: [ ]=pending  [>]=in_progress  [x]=completed
       blockedBy=[N] = cannot be claimed until Task N done
    
  Teammates auto-scan every 5 seconds.
  They ONLY claim tasks with NO blockers.
  As tasks complete, dependencies clear -> new tasks unlock.
""")
    
    # Show initial state
    print("--- Initial State ---")
    print_board()
    
    # Clean up old config if needed
    if TEAM.config["members"]:
        print("\nCleaning old teammates...")
        TEAM.config["members"] = []
        TEAM._save_config()
    
    # Spawn teammates
    print("\n>>> Spawning 'builder'...")
    result = TEAM.spawn("builder", "coder", 
        "You are a Python developer. Claim tasks from the board and complete them. "
        "Use bash to create project files. When done, mark the task as completed by "
        "editing the JSON file.")
    print(f"    {result}")
    
    print(">>> Spawning 'tester'...")
    result = TEAM.spawn("tester", "tester",
        "You are a QA engineer. Claim tasks from the board and complete them. "
        "Write test files to verify code. Mark tasks completed by editing the JSON.")
    print(f"    {result}")
    
    # Monitor
    print("\n--- Monitoring (checking every 10 seconds) ---")
    try:
        for i in range(36):  # 6 minutes max
            time.sleep(10)
            done = print_board()
            print(f"  Teammates:\n{TEAM.list_all()}")
            if done:
                print("  >>> All tasks completed! Dependencies respected! <<<")
                break
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user.")
    
    # Final summary
    print("\n" + "="*60)
    print("  FINAL TASK BOARD")
    print_board()
    print("\n  Final Teammate Status:")
    print(TEAM.list_all())
    print("="*60)
    print("  DEMO COMPLETE")
    print("="*60)

if __name__ == "__main__":
    main()
