"""Debug what's happening with the threads"""
import sys
sys.path.insert(0, r"D:\Pyprogram\learn-claude-codetest\agents")

import threading
print(f"Active threads at start: {threading.active_count()}")

from s11_autonomous_agentstest import TEAM, TASKS_DIR
print(f"TASKS_DIR = {TASKS_DIR}")
print(f"Tasks exist: {list(TASKS_DIR.glob('*.json'))}")

# Check the _save_config works
print(f"Config before: {TEAM.config['members']}")

# Test _set_status directly
TEAM._set_status("builder", "debug_test")
print(f"Config after set_status: {TEAM.config['members']}")

print(f"Threads in TEAM.threads: {TEAM.threads}")

# Check if _load_config works
TEAM._load_config()
print(f"Config reloaded: {TEAM.config['members']}")
