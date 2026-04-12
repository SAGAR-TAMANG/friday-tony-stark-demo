# 🧠 FRIDAY Learning Notes - Understanding the Magic

> *"If you're nothing without the suit, then you shouldn't have it."* - Tony Stark

This guide breaks down the key concepts behind FRIDAY. Perfect for understanding how everything works under the hood! 🔧

---

## 📚 Table of Contents

1. [Core Concepts](#core-concepts)
2. [Python Async Magic](#python-async-magic)
3. [MCP Framework](#mcp-framework)
4. [Networking & Protocols](#networking--protocols)
5. [Quick Reference](#quick-reference)

---

## 🎯 Core Concepts

### 1. RSS - Really Simple Syndication

**What it is:**
- A live feed of new content from websites
- Structured format (XML) that programs can read automatically
- Like subscribing to a newsletter, but for machines

**How FRIDAY uses it:**
```python
# Fetches news from BBC, NYT, etc.
feeds = [
    'https://feeds.bbci.co.uk/news/world/rss.xml',
    'https://rss.nytimes.com/services/xml/rss/nyt/World.xml'
]
```

**Real-world analogy:**
- 📰 Website = Newspaper publisher
- 📡 RSS Feed = Automatic delivery service
- 🤖 FRIDAY = Reader who checks all newspapers at once

---

### 2. Coroutine Objects - Async Superpowers

**What it is:**
- A function that can pause and resume
- Allows multiple tasks to run "at the same time"
- The secret sauce behind fast, non-blocking code

**The Magic:**
```python
async def my_func():
    return 123

# Creates coroutine object (doesn't run yet!)
coro = my_func()

# Actually runs the function
result = await coro  # Pauses here until done
```

**Why "coroutine"?**
- **Routine** = Normal function (runs start → finish)
- **Co-routine** = Cooperative routine (pauses to let others run)

**Real-world analogy:**
```
Normal function (routine):
You: Cook dinner start to finish (blocks everything else)

Coroutine:
You: Start boiling water → While waiting, chop vegetables → 
     Check water → While waiting, prepare sauce → etc.
```

---

### 3. The `*` Unpacking Operator

**What it does:**
```python
tasks = [task1, task2, task3]

# Without *
asyncio.gather(tasks)  # ❌ Passes a list

# With *
asyncio.gather(*tasks)  # ✅ Unpacks to: task1, task2, task3
```

**Real-world analogy:**
```python
# You have a box of apples
apples = [🍎, 🍎, 🍎]

# Without * - you hand over the box
give_to_friends(apples)  # Here's a box

# With * - you hand out individual apples
give_to_friends(*apples)  # Here's one, here's one, here's one
```

---

## ⚡ Python Async Magic

### Parallel Execution with `asyncio.gather()`

**The Problem:**
```python
# Slow - one at a time (10 seconds total)
news1 = await fetch_bbc()      # 5 seconds
news2 = await fetch_nyt()      # 5 seconds
```

**The Solution:**
```python
# Fast - all at once (5 seconds total)
results = await asyncio.gather(
    fetch_bbc(),    # Runs in parallel
    fetch_nyt(),    # Runs in parallel
)
```

**How it works:**
```
Sequential (slow):
BBC: ████████████ (5s)
                    NYT: ████████████ (5s)
Total: 10 seconds

Parallel (fast):
BBC: ████████████ (5s)
NYT: ████████████ (5s)
Total: 5 seconds (both at once!)
```

---

## 🛠️ MCP Framework

### The Big 3 Decorators

MCP gives you three superpowers to expose functionality to the AI:

---

#### 1. `@mcp.tool()` - Actions the AI Can DO

**Purpose:** Make functions callable by the LLM

```python
@mcp.tool()
async def get_weather(city: str) -> str:
    """Fetch current weather for a city."""
    return f"Weather in {city}: Sunny, 72°F"
```

**When AI uses it:**
- User: "What's the weather in New York?"
- AI thinks: "I need real-time weather data"
- AI calls: `get_weather("New York")`
- AI responds: "It's sunny and 72°F in New York"

**Real-world analogy:**
- Tool = A hammer in your toolbox
- AI = The carpenter who decides when to use it

---

#### 2. `@mcp.resource()` - Data the AI Can READ

**Purpose:** Expose information like virtual files

```python
@mcp.resource("config://app")
def config():
    """App configuration."""
    return {"mode": "friday", "version": "1.0"}
```

**When AI uses it:**
- User: "What mode are you in?"
- AI thinks: "I should check the config"
- AI reads: `config://app`
- AI responds: "I'm running in Friday mode, version 1.0"

**Key insight:**
- ✅ Can be virtual (just return data)
- ✅ Can read actual files
- ✅ Can query databases
- ✅ Can call APIs

**Real-world analogy:**
- Resource = A book on a shelf
- AI = The reader who looks it up when needed

---

#### 3. `@mcp.prompt()` - Templates the AI Can USE

**Purpose:** Reusable instruction templates

```python
@mcp.prompt()
def summarize_style():
    """Summarization style guide."""
    return "Summarize like Tony Stark: short, witty, confident"
```

**When AI uses it:**
- User: "Summarize this article"
- AI thinks: "I should use the summarize style"
- AI applies: Template instructions
- AI responds: In Tony Stark style

**Real-world analogy:**
- Prompt = A recipe card
- AI = The chef who follows it

---

### Tools vs Resources - When to Use What?

| Scenario | Use | Why |
|----------|-----|-----|
| Get current news | **Tool** | Needs to fetch live data |
| Read server info | **Resource** | Static information |
| Search the web | **Tool** | Performs an action |
| Read documentation | **Resource** | Reference material |
| Send email | **Tool** | Does something |
| Read config | **Resource** | Just data |

**Rule of thumb:**
- 🔧 **Tool** = Verb (do, get, send, search)
- 📖 **Resource** = Noun (info, docs, config, data)

---

## 🌐 Networking & Protocols

### SSE - Server-Sent Events

**What it is:**
- A way for servers to push updates to clients
- Built on top of HTTP/HTTPS
- One-way communication (server → client)

**The Stack:**
```
Application (FRIDAY)
        ↓
    SSE Protocol
        ↓
   HTTP/HTTPS
        ↓
    TCP/IP
        ↓
   Network
```

**How FRIDAY uses it:**
```python
# MCP Server exposes tools via SSE
mcp.run(transport='sse')  # Runs on port 8000

# Voice Agent connects via SSE
mcp_servers=[
    mcp.MCPServerHTTP(
        url="http://127.0.0.1:8000/sse",
        transport_type="sse"
    )
]
```

**Real-world analogy:**
```
HTTP Request/Response:
You: "Hey, any updates?" (request)
Server: "Here's one update" (response)
You: "Any more?" (request)
Server: "Here's another" (response)
[Repeat forever - inefficient!]

SSE:
You: "Keep me updated" (one request)
Server: "Update 1" (push)
Server: "Update 2" (push)
Server: "Update 3" (push)
[Connection stays open - efficient!]
```

---

## 🎓 Quick Reference

### Async Patterns

```python
# Run one thing
result = await some_async_function()

# Run multiple things in parallel
results = await asyncio.gather(
    task1(),
    task2(),
    task3()
)

# Run with timeout
result = await asyncio.wait_for(task(), timeout=5.0)
```

---

### MCP Patterns

```python
# Register a tool
@mcp.tool()
async def my_tool(param: str) -> str:
    """Tool description for AI."""
    return "result"

# Register a resource
@mcp.resource("myapp://data")
def my_resource():
    """Resource description."""
    return {"key": "value"}

# Register a prompt
@mcp.prompt()
def my_prompt():
    """Prompt description."""
    return "Instructions for AI"
```

---

### Common Patterns in FRIDAY

```python
# Fetch multiple RSS feeds in parallel
tasks = [fetch_feed(url) for url in urls]
results = await asyncio.gather(*tasks)

# Read environment variables
api_key = os.getenv("API_KEY", "default_value")

# Load .env file
from dotenv import load_dotenv
load_dotenv()

# HTTP requests
async with httpx.AsyncClient() as client:
    response = await client.get(url)
    return response.json()
```

---

## 💡 Pro Tips

### 1. Understanding the Flow

```
User speaks
    ↓
STT converts to text
    ↓
LLM receives text + available tools
    ↓
LLM decides: Use tool OR answer directly
    ↓
If tool: Calls MCP server → Gets result
    ↓
LLM generates response
    ↓
TTS converts to speech
    ↓
User hears FRIDAY
```

### 2. Debugging Async Code

```python
# Add logging
import logging
logger = logging.getLogger(__name__)

async def my_func():
    logger.info("Starting task")
    result = await some_task()
    logger.info(f"Got result: {result}")
    return result
```

### 3. Error Handling

```python
# Always handle errors in async code
try:
    result = await risky_operation()
except Exception as e:
    logger.error(f"Operation failed: {e}")
    return "Error occurred"
```

---

## 🎯 Key Takeaways

1. **Async = Efficiency** - Do multiple things at once
2. **MCP = Structure** - Organized way to expose functionality
3. **Tools = Actions** - What AI can DO
4. **Resources = Data** - What AI can READ
5. **SSE = Real-time** - Efficient server-to-client communication

---

## 📖 Further Reading

- [Python Asyncio Docs](https://docs.python.org/3/library/asyncio.html)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [LiveKit Agents Guide](https://docs.livekit.io/agents/)
- [Server-Sent Events Spec](https://html.spec.whatwg.org/multipage/server-sent-events.html)

---

> *"The truth is... I am Iron Man."* - Tony Stark

Now you understand the magic behind FRIDAY! 🧙‍♂️✨

Keep learning, keep building, boss! 🚀