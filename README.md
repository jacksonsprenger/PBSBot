# PBSBot

Welcome to the PBSBot Project!

## Getting Started

### Prerequisites

- Python 3.x installed on your machine

### 1. Create a Virtual Environment

**macOS / Linux:**
```bash
python -m venv .venv
```

**Windows (Command Prompt):**
```cmd
python -m venv .venv
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
```

### 2. Install Dependencies

Before activating the virtual environment, install all project dependencies from `requirements.txt`:

**macOS / Linux:**
```bash
.venv/bin/pip install -r requirements.txt
```

**Windows (Command Prompt):**
```cmd
.venv\Scripts\pip install -r requirements.txt
```

**Windows (PowerShell):**
```powershell
.venv\Scripts\pip install -r requirements.txt
```

### 3. Activate the Virtual Environment

**macOS / Linux:**
```bash
source .venv/bin/activate
```

**Windows (Command Prompt):**
```cmd
.venv\Scripts\activate.bat
```

**Windows (PowerShell):**
```powershell
.venv\Scripts\Activate.ps1
```

> **Note for Windows PowerShell users:** If you get an execution policy error, run this first:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

Once activated, your terminal prompt will show `(.venv)` to confirm it's active.

### 4. Run the Bot (Doesn't currently work because of depreciated tokens)

```bash
python main.py
```

---

## Connecting to the Remote LLM (Ollama)

The bot uses a local LLM hosted inside an Ollama container on a remote machine. Access is provided through a persistent SSH tunnel.

### Prerequisites

- **UW-Madison VPN** — You must be connected to the WISC VPN before attempting to connect. Download the VPN client from [it.wisc.edu/services/wiscvpn](https://it.wisc.edu/services/wiscvpn/).

### 1. Configure the Script

Open [scripts/llm_connect.py](scripts/llm_connect.py) and update the configuration block near the top of the file:

```python
SSH_HOST = "144.92.195.30"          # Remote machine hostname/IP
SSH_USER = "capstone"               # Your SSH username
MODEL   = "deepseek-coder:6.7b"     # Model name being served
```

### 2. Run the Script

With the venv active:

```bash
python scripts/llm_connect.py
```

You will be prompted for your SSH password. Once authenticated, an SSH tunnel is opened and you can type prompts directly in the terminal:

```
=== PBS Bot — LLM Connect ===
Target: capstone@144.92.195.30
Make sure you are connected to the UW-Madison VPN before continuing.

SSH Password:
Connected. Opening tunnel → localhost:11434 → localhost:11434
Tunnel open. Model: deepseek-coder:6.7b
Type your prompt and press Enter. Type 'exit' or press Ctrl+C to quit.

You: What is the capital of France?
Bot: The capital of France is Paris.

You: exit
Connection closed.
```

### Installed Dependencies

| Package | Purpose |
|---|---|
| `slack_bolt` | Slack Bolt framework for handling events |
| `slack_sdk` | Slack SDK for API interactions |
| `python-dotenv` | Loads environment variables from `.env` |
| `certifi` | SSL certificate fix for macOS |
| `paramiko` | SSH tunnel for remote Ollama connection |

