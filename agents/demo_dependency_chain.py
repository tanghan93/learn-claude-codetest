#!/usr/bin/env python3
"""
Demo: Task dependency chain with autonomous teammates.

Teammates auto-scan the task board and only claim tasks without blockedBy.
This demonstrates that dependency ordering is respected.
"""

import json
import time
import sys
import os
from pathlib import Path

# Add agents directory to path
sys.path.insert(0, os.path.dirname(__file__))

from anthropic import Anthropic
from dotenv import load_dotenv
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEFAULT_MODEL

load_dotenv(override=True)

client = Anthropic(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL
)

MODEL = DEFAULT_MODEL

WORKDIR = Path.cwd()
TASKS_DIR = WORKDIR / ".team" / "tasks"

# Import the team manager from s11
# We'll use it directly by importing and running the agent loop
from s11_autonomous_agentstest import (
    TEAM, BUS, TASKS_DIR, agent_loop,
    scan_unclaimed_tasks, claim_task
)

def print_task_board():
    """Display current task board status."""
    TASKS_DIR.mkdir(exist_ok=True)
    tasks = []
    for f in sorted(TASKS_DIR.glob("task_*.json")):
        t = json.loads(f.read_text(encoding="utf-8"))
        tasks.append(t)
    
    print("\n" + "="*60)
    print("  TASK BOARD STATUS")
    print("="*60)
    for t in tasks:
        marker = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}.get(t["status"], "[?]")
        owner = f" @{t['owner']}" if t.get("owner") else ""
        blocked = f" (blocked by: {t['blockedBy']})" if t.get("blockedBy") else ""
        print(f"  {marker} #{t['id']}: {t['subject']}{owner}{blocked}")
    
    # Check which tasks are claimable
    unclaimed = scan_unclaimed_tasks()
    print(f"\n  Claimable now: {[t['id'] for t in unclaimed]}")
    print("="*60 + "\n")
    return tasks

def main():
    print("\n" + "="*60)
    print("  DEMO: Task Dependency Chain with Autonomous Teammates")
    print("="*60)
    print()
    print("  Task 1: Plan architecture          (no deps)")
    print("  Task 2: Write core module          (blocked by Task 1)")
    print("  Task 3: Write tests                 (blocked by Task 2)")
    print("  Task 4: Create documentation        (blocked by Task 3)")
    print()
    print("  Teammates will only claim tasks that have NO blockers.")
    print("  As tasks complete, dependencies clear and new tasks unlock.")
    print()
    
    # Show initial state
    print("--- Initial State ---")
    print_task_board()
    
    # Spawn 2 autonomous teammates
    print(">>> Spawning teammate 'builder' (handles architecture + coding)...")
    result = TEAM.spawn("builder", "coder", 
        "You are a Python developer. Claim tasks from the board and complete them. "
        "Use bash to create files. When done, mark the task as completed by editing "
        "the JSON file status field to 'completed'.")
    print(f"    {result}")
    
    time.sleep(2)
    
    print(">>> Spawning teammate 'tester' (handles tests + docs)...")
    result = TEAM.spawn("tester", "tester", 
        "You are a QA engineer. Claim tasks from the board and complete them. "
        "Use bash to create files. When done, mark the task as completed by editing "
        "the JSON file status field to 'completed'.")
    print(f"    {result}")
    
    # Monitor the task board for a while
    print("\n--- Monitoring Task Board (checking every 10 seconds) ---")
    print("(The teammates auto-poll every 5 seconds)")
    
    prev_state = ""
    for i in range(12):  # Monitor for ~120 seconds
        time.sleep(10)
        
        # Print current status
        tasks = print_task_board()
        
        # Check if all tasks are completed
        all_done = all(t["status"] == "completed" for t in tasks)
        if all_done:
            print("  >>> ALL TASKS COMPLETED! <<<")
            break
    
    # Final state
    print("\n--- Final State ---")
    tasks = print_task_board()
    
    # Print teammate status
    print("\n--- Teammate Status ---")
    print(TEAM.list_all())
    
    print("\n" + "="*60)
    print("  DEMO COMPLETE")
    print("="*60)

if __name__ == "__main__":
    main()
