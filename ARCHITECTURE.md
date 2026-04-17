# FRIDAY Unified Architecture

Complete Jarvis AI system integrating 6 reference projects with real-time capabilities.

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRIDAY JARVIS                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  Voice Layer (LiveKit Agents 1.6+)                                          │
│  ├── Pipeline Mode: STT → LLM → TTS                                          │
│  ├── Realtime Gemini: Gemini Live speech-to-speech                           │
│  └── Realtime OpenAI: GPT Realtime speech-to-speech                         │
├─────────────────────────────────────────────────────────────────────────────┤
│  MCP Server (FastMCP + Streamable HTTP)                                    │
│  ├── 18 Tool Modules                                                         │
│  ├── 50+ Individual Tools                                                    │
│  └── A2A Protocol Endpoint                                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  Core Systems                                                                │
│  ├── Agent Orchestrator (Multi-agent coordination)                          │
│  ├── Skill Registry (Dynamic skill discovery)                                │
│  ├── Memory Manager (Working + Episodic + Long-term)                         │
│  ├── A2A Bus (Agent-to-agent messaging)                                      │
│  └── Persistence Layer (SQLite: telemetry, traces, agents)                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Breakdown

### 1. Voice Layer (`agent_friday.py`)

**Three modes supported:**

| Mode | Latency | Description |
|------|---------|-------------|
| `pipeline` | ~1.5s | STT → LLM → TTS chain (default, most robust) |
| `realtime_gemini` | ~300ms | Gemini Live speech-to-speech |
| `realtime_openai` | ~300ms | GPT Realtime speech-to-speech |

**Features:**
- Noise cancellation (BVC)
- Semantic turn detection (MultilingualModel)
- MCP tool integration in all modes

### 2. MCP Server (`server.py`)

**Transport:** Streamable HTTP (MCP spec 2025-03-26)

**Tool Categories:**

| Category | Tools | Source |
|----------|-------|--------|
| **Web** | search_web, fetch_url, open_world_monitor | Original + SUPER AGI |
| **Browser** | browser_navigate, browser_screenshot, browser_extract_links | OpenJarvis |
| **News** | get_world_news, get_news_by_topic, get_trending_events | Original |
| **Finance** | get_stock_quote, get_market_overview, get_crypto_price | Original |
| **Weather** | get_weather, get_forecast | Original |
| **Notify** | notify_user, send_morning_briefing | Original |
| **Calendar** | get_todays_events, get_upcoming_events | Original |
| **Mail** | check_mail, send_mail | Original |
| **Memory** | remember_fact, recall, forget | Original |
| **Enhanced Memory** | memory_add_working, memory_get_context, memory_save_episode, memory_recall_episodes, memory_list_episodes, memory_save_fact, memory_search_facts, memory_clear_working | aios-local |
| **System** | get_current_time, get_system_info | Original |
| **Utils** | format_json, word_count | Original |
| **Shell** | shell_exec | OpenJarvis |
| **Git** | git_status, git_diff, git_log | OpenJarvis |
| **Code** | run_code | SUPER AGI |
| **A2A** | a2a_send_message, a2a_receive_message, a2a_check_inbox, a2a_get_history, a2a_broadcast | aios-local |
| **Orchestrator** | agent_create_task, agent_execute_task, agent_list_tasks, agent_get_task_status, agent_list_available, agent_register, agent_delegated_task | agency-agents |
| **Skills** | skill_discover, skill_load, skill_info, skill_reload, skill_create_template | OpenJarvis |

### 3. Core Systems (`friday/core/`)

#### A2A Bus (`a2a.py`)
- **Pattern:** aios-local/core/a2a.py
- **Purpose:** Agent-to-agent messaging
- **Features:**
  - Message queuing per agent
  - Handler registration for async processing
  - Message persistence
  - History tracking

```python
# Send message
message = A2AMessage.create(
    from_agent="friday",
    to_agent="code-agent",
    content="Review this code",
    message_type="task"
)
bus.send(message)

# Receive message
msg = bus.receive("code-agent", timeout=5.0)
```

#### Memory Manager (`memory_manager.py`)
- **Pattern:** aios-local/core/memory.py
- **Layers:**
  1. **Working Memory:** Last 100 messages (context window)
  2. **Episodic Memory:** Task outcomes with relevance scoring
  3. **Long-term Facts:** Category-based fact storage

#### Skill Registry (`skill_registry.py`)
- **Pattern:** OpenJarvis/src/openjarvis/skills/
- **Features:**
  - Dynamic skill discovery from `~/.friday/skills/`
  - TOML-based manifest (`skill.toml`)
  - Runtime loading/unloading
  - Dependency tracking

#### Orchestrator (`orchestrator.py`)
- **Pattern:** agency-agents/agency.py
- **Features:**
  - Multi-agent coordination
  - Task routing based on capabilities
  - Parallel task execution
  - Result aggregation
  - Default agents: friday-core, code-agent, research-agent, shell-agent

#### Persistence (`persistence.py`)
- **Pattern:** .openjarvis (SQLite databases)
- **Databases:**
  - **agents.db:** Agent configurations and state
  - **telemetry.db:** Usage events and metrics
  - **traces.db:** Execution traces for debugging

### 4. Data Flow

```
User Voice Input
       ↓
LiveKit Agent (Voice Layer)
       ↓
MCP Client (mcp.MCPServerHTTP)
       ↓
MCP Server (FastMCP)
       ↓
Tool Router
       ↓
┌─────────────┬─────────────┬─────────────┐
│   Tools     │  Memory     │  A2A Bus    │
│  (50+)      │  Manager    │  (Agents)   │
└─────────────┴─────────────┴─────────────┘
       ↓
Persistence (SQLite)
       ↓
Response (Voice/Text)
```

## Configuration

### Environment Variables

```bash
# Core paths
FRIDAY_HOME=~/.friday
FRIDAY_DB_PATH=~/.friday/databases
FRIDAY_MEMORY_PATH=~/.friday/memory.json

# Transport
MCP_TRANSPORT=streamable-http
MCP_SERVER_HOST=127.0.0.1
MCP_SERVER_PORT=8000

# Voice
VOICE_MODE=pipeline  # or: realtime_gemini, realtime_openai

# Security
SHELL_EXEC_ENABLED=true
SHELL_BLOCKED_COMMANDS=rm -rf /,rm -rf /*,dd if=/dev/zero

# A2A Protocol
A2A_ENABLED=false
A2A_PORT=8001
```

## Directory Structure

```
~/.friday/
├── databases/
│   ├── agents.db
│   ├── telemetry.db
│   └── traces.db
├── episodes/
│   └── [episode_id].json
├── skills/
│   └── [skill_name]/
│       ├── skill.toml
│       └── main.py
├── a2a_history.json
├── long_term_memory.json
└── memory.json
```

## Usage Examples

### Multi-Agent Task Delegation

```python
# Create task
await agent_create_task(
    task_type="coding",
    description="Write a function to calculate fibonacci",
    input_data='{"n": 10}'
)

# Execute
await agent_execute_task("abc123")

# Check status
await agent_get_task_status("abc123")
```

### A2A Communication

```python
# Send to another agent
await a2a_send_message(
    to_agent="code-agent",
    content="Review this PR",
    message_type="task"
)

# Receive messages
await a2a_receive_message(agent_name="friday", timeout=5.0)
```

### Enhanced Memory

```python
# Working memory (context)
await memory_add_working("user", "I need help with Python")
context = await memory_get_context()

# Episodic memory (task history)
await memory_save_episode(
    task="Fixed bug in login",
    outcome="Tests passing",
    tools_used=["code_runner", "shell_exec"]
)

# Recall similar episodes
await memory_recall_episodes("bug fix", limit=3)
```

### Skill Development

```python
# Create template
await skill_create_template("my_skill", "Does something cool")

# Discover
await skill_discover("custom")

# Load
await skill_load("my_skill")
```

## Real-Time Capabilities

### Latest Patterns (April 2026)

1. **Gemini Live API**
   - Speech-to-speech realtime
   - Bidirectional streaming
   - Multimodal support

2. **OpenAI Realtime API**
   - Low-latency conversation
   - Server-sent events
   - Native audio in/out

3. **MCP Streamable HTTP**
   - Replaces SSE transport
   - Standard HTTP POST/GET
   - Better proxy support

4. **Semantic Turn Detection**
   - Replaces VAD-based detection
   - Predicts end-of-utterance from meaning
   - Faster response times

## Security Model

| Component | Protection |
|-----------|-----------|
| Shell Tool | Sanitized env, blocked commands, timeouts |
| Browser Tool | Headless only, no uploads, optional dep |
| Code Runner | Subprocess isolation, AST check, timeout |
| Git Tool | Read-only operations |
| A2A Bus | No external network (local only) |

## Performance Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| Tool execution | 10-500ms | Depends on tool |
| Memory recall | <10ms | Local JSON files |
| A2A message | <1ms | In-memory queue |
| SQLite write | 1-5ms | Async where possible |
| Voice pipeline | 1.5s | STT → LLM → TTS |
| Realtime voice | 300ms | Speech-to-speech |

## Extension Points

1. **New Tools:** Add to `friday/tools/`, register in `__init__.py`
2. **New Skills:** Create in `~/.friday/skills/[name]/`
3. **New Agents:** Register with `agent_register()`
4. **Custom Memory:** Extend `MemoryManager` class
5. **External A2A:** Implement `A2AClient` for remote agents

## Credits

| Project | Key Contribution |
|---------|-----------------|
| OpenJarvis | Registry pattern, SkillManager, shell/browser/git tools |
| SUPER AGI | Clean tool architecture, CodeRunnerTool |
| aios-local | MemoryManager, A2A protocol |
| agency-agents | Agent orchestrator, multi-agent patterns |
| .openjarvis | SQLite persistence layer |
| claude-code-best-practice | Architecture patterns |

---

*Built with patterns from 6 projects + real-time voice AI capabilities*
