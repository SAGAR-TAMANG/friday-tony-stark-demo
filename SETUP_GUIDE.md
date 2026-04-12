# 🚀 FRIDAY Setup Guide - Get Your AI Assistant Running!

> *"Sometimes you gotta run before you can walk."* - Tony Stark

Welcome, boss! Let's get FRIDAY up and running on your machine. Follow these steps and you'll be talking to your own Tony Stark-style AI in minutes! 🦾

---

## 📋 Prerequisites

- ✅ Python 3.11 or higher
- ✅ macOS, Linux, or WSL2
- ✅ Terminal access
- ✅ 10 minutes of your time

---

## 🔧 Quick Setup (Copy & Paste)

### Step 1: Clean Slate 🧹

```bash
# Deactivate any active virtual environment
deactivate

# Remove old virtual environment (if exists)
rm -rf .venv
```

### Step 2: Create Fresh Environment 🌱

```bash
# Create a new virtual environment
python3 -m venv .venv

# Activate it (you'll see (.venv) in your prompt)
source .venv/bin/activate
```

### Step 3: Install Dependencies 📦

```bash
# Upgrade pip to latest version
python3 -m pip install --upgrade pip

# Install all project dependencies
python3 -m pip install -e .
```

### Step 4: Verify Installation ✅

```bash
# Check if everything installed correctly
python3 -c "import fastmcp; print('✅ FastMCP installed!')"
python3 -c "from livekit import agents; print('✅ LiveKit installed!')"

# Verify you're using the virtual environment
which python3
# Should show: /path/to/stark-agent/.venv/bin/python3
```

---

## ⚡ Alternative: Using uv (Optional - Faster!)

If you want blazing fast installs, try `uv`:

```bash
# Install uv (one-time setup)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Then use uv commands
uv sync              # Install everything
uv run friday        # Run MCP server
uv run friday_voice  # Run voice agent
```

---

## 🔑 Configure API Keys

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your API keys
nano .env  # or use your favorite editor (vim, code, etc.)
```

### Required API Keys:

| Service | Key Name | Get It From | Purpose |
|---------|----------|-------------|---------|
| **LiveKit** | `LIVEKIT_URL`<br>`LIVEKIT_API_KEY`<br>`LIVEKIT_API_SECRET` | [cloud.livekit.io](https://cloud.livekit.io) | Voice infrastructure |
| **Google** | `GOOGLE_API_KEY` | [aistudio.google.com](https://aistudio.google.com) | Gemini LLM (brain) |
| **Sarvam** | `SARVAM_API_KEY` | [dashboard.sarvam.ai](https://dashboard.sarvam.ai) | Speech-to-text (ears) |
| **OpenAI** | `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) | Text-to-speech (voice) |

---

## 🎬 Launch FRIDAY!

### Terminal 1 - MCP Server (Backend) 🖥️

```bash
cd /path/to/stark-agent
source .venv/bin/activate
python server.py
```

✅ **Success looks like:**
```
MCP Server running on http://127.0.0.1:8000/sse
```

### Terminal 2 - Voice Agent (Frontend) 🎤

```bash
cd /path/to/stark-agent
source .venv/bin/activate
python agent_friday.py dev
```

✅ **Success looks like:**
```
FRIDAY online - room: xxx | STT=sarvam | LLM=gemini | TTS=openai
```

### Connect & Talk! 🗣️

1. Open [LiveKit Agents Playground](https://agents-playground.livekit.io)
2. Connect to your room
3. Start talking!

**Try saying:**
- *"What's happening in the world?"*
- *"What time is it?"*
- *"Tell me about yourself"*

---

## 🎛️ Customization

### Switch to ChatGPT (GPT-4o)

Edit `agent_friday.py` line 32:

```python
# Change from:
LLM_PROVIDER = "gemini"

# To:
LLM_PROVIDER = "openai"
```

### Change Voice Speed

Edit `agent_friday.py` line 40:

```python
TTS_SPEED = 1.15  # Increase for faster, decrease for slower
```

---

## 🐛 Troubleshooting

### "Command not found: python3"

```bash
# Try python instead
python --version

# Or install Python 3.11+
brew install python@3.11  # macOS
```

### "Module not found: fastmcp"

```bash
# Make sure venv is activated (you should see (.venv) in prompt)
source .venv/bin/activate

# Reinstall dependencies
pip install -e .
```

### "Cannot connect to MCP server"

```bash
# Make sure server.py is running in Terminal 1
# Check it's accessible
curl http://127.0.0.1:8000/sse

# If not, restart server.py
```

### "LiveKit connection failed"

```bash
# Check your .env file has correct LiveKit credentials
cat .env | grep LIVEKIT

# Verify keys are valid at cloud.livekit.io
```

### Import errors after installation

```bash
# Completely remove and reinstall
deactivate
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
```

---

## 📊 System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    YOU (User)                           │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │   Microphone Input    │
         └───────────┬───────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │  STT (Sarvam Saaras)  │
         │  Speech → Text        │
         └───────────┬───────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │  LLM (Gemini/GPT-4o)  │
         │  Thinks & Decides     │
         └───────────┬───────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
         ▼                       ▼
┌────────────────┐      ┌────────────────┐
│  MCP Server    │      │  Direct Reply  │
│  (Tools)       │      │  (Knowledge)   │
│  - News        │      └────────┬───────┘
│  - Time        │               │
│  - Search      │               │
└────────┬───────┘               │
         │                       │
         └───────────┬───────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │  TTS (OpenAI nova)    │
         │  Text → Speech        │
         └───────────┬───────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │   Speaker Output      │
         └───────────────────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │   YOU (Hear FRIDAY)   │
         └───────────────────────┘
```

---

## 🎉 You're All Set!

FRIDAY is now ready to assist you, boss! 

**What's Next?**
- 📖 Check out `LEARNING_NOTES.md` to understand how it works
- 🛠️ Add custom tools in `friday/tools/`
- 🎨 Customize the personality in `agent_friday.py`
- 🚀 Deploy to production

---

## 💡 Pro Tips

1. **Keep both terminals running** - Server must be up for agent to work
2. **Check logs** - Both terminals show useful debug info
3. **Test incrementally** - Run server first, then agent
4. **Use VSCode split terminal** - Easier to manage both processes
5. **Monitor API usage** - Keep an eye on your API costs

---

## 🆘 Need Help?

- 📚 Read the main [README.md](README.md)
- 🧠 Check [LEARNING_NOTES.md](LEARNING_NOTES.md) for concepts
- 🐛 Open an issue on GitHub
- 💬 Ask in the community

---

> *"I am Iron Man."* - Tony Stark

Welcome to the future, boss! 🚀🦾
