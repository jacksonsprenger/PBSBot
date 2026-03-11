#!/usr/bin/env python3
"""
llm_connect.py

Opens an SSH tunnel to the remote machine hosting the Ollama container,
then starts an interactive prompt loop that sends your input to the LLM
and prints the response.

Requirements:
  - Must be connected to the UW-Madison VPN before running.
  - Edit the Configuration block below to match your credentials and host.
"""

import getpass
import json
import select
import socket
import socketserver
import sys
import threading
import urllib.error
import urllib.request

import paramiko

# ---------------------------------------------------------------------------
# Configuration — update these values for your environment
# ---------------------------------------------------------------------------
SSH_HOST = "144.92.195.30"                   # Remote machine hostname/IP
SSH_USER = "capstone"                        # Your SSH username

OLLAMA_REMOTE_HOST = "localhost"             # Ollama host as seen from the remote machine
OLLAMA_REMOTE_PORT = 11434                   # Port Ollama is listening on inside the container
LOCAL_PORT = 11434                           # Local port to forward to

MODEL = "deepseek-coder:6.7b"                # Model name being served by Ollama
# ---------------------------------------------------------------------------


def _forward_handler_factory(ssh_transport, remote_host, remote_port):
    """Return a socketserver request handler that forwards to the remote host:port."""

    class ForwardHandler(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                chan = ssh_transport.open_channel(
                    "direct-tcpip",
                    (remote_host, remote_port),
                    self.request.getpeername(),
                )
            except Exception as exc:
                print(f"[tunnel] Failed to open channel: {exc}")
                return

            try:
                while True:
                    r, _, _ = select.select([self.request, chan], [], [], 5)
                    if self.request in r:
                        data = self.request.recv(4096)
                        if not data:
                            break
                        chan.sendall(data)
                    if chan in r:
                        data = chan.recv(4096)
                        if not data:
                            break
                        self.request.sendall(data)
            finally:
                chan.close()

    return ForwardHandler


def start_tunnel(ssh_client, local_port, remote_host, remote_port):
    """Bind a local TCP port and forward all connections through the SSH tunnel."""

    class ForwardServer(socketserver.ThreadingTCPServer):
        daemon_threads = True
        allow_reuse_address = True

    handler = _forward_handler_factory(
        ssh_client.get_transport(), remote_host, remote_port
    )
    server = ForwardServer(("127.0.0.1", local_port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def prompt_llm(user_prompt: str) -> str:
    """POST a prompt to the tunneled Ollama endpoint and return the response text."""
    url = f"http://localhost:{LOCAL_PORT}/api/generate"
    payload = json.dumps(
        {"model": MODEL, "prompt": user_prompt, "stream": False}
    ).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode())
        return result.get("response", "").strip()


def main():
    print("=== PBS Bot — LLM Connect ===")
    print(f"Target: {SSH_USER}@{SSH_HOST}")
    print("Make sure you are connected to the UW-Madison VPN before continuing.\n")

    password = getpass.getpass("SSH Password: ")

    # Establish SSH connection
    client = paramiko.SSHClient()
    # AutoAddPolicy trusts new host keys automatically — acceptable for dev/VPN use.
    # For production, replace with RejectPolicy and pre-populate ~/.ssh/known_hosts.
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            SSH_HOST,
            username=SSH_USER,
            password=password,
            look_for_keys=False,
            allow_agent=False,
        )
    except paramiko.AuthenticationException:
        print("\nAuthentication failed — check your username and password.")
        sys.exit(1)
    except (paramiko.SSHException, socket.error) as exc:
        print(f"\nConnection failed: {exc}")
        sys.exit(1)

    print(f"Connected. Opening tunnel → localhost:{LOCAL_PORT} → {OLLAMA_REMOTE_HOST}:{OLLAMA_REMOTE_PORT}")
    tunnel = start_tunnel(client, LOCAL_PORT, OLLAMA_REMOTE_HOST, OLLAMA_REMOTE_PORT)
    print(f"Tunnel open. Model: {MODEL}")
    print("Type your prompt and press Enter. Type 'exit' or press Ctrl+C to quit.\n")

    try:
        while True:
            try:
                user_input = input("You: ").strip()
            except EOFError:
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                break

            print("Bot: ", end="", flush=True)
            try:
                response = prompt_llm(user_input)
                print(response)
            except urllib.error.URLError as exc:
                print(f"\n[error] Could not reach Ollama: {exc}")
            except Exception as exc:
                print(f"\n[error] Unexpected error: {exc}")

    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        tunnel.shutdown()
        client.close()
        print("Connection closed.")


if __name__ == "__main__":
    main()
