# Friday MCP Server Package

import os
import sys

# Ensure project root is in sys.path so top-level modules (server, agent_friday) are importable
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
