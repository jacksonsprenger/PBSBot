# Ollama Setup Guide

This setup details:

1. Installing Ollama on an Ubuntu machine
2. Enabling **GPU acceleration with CUDA** (required NVIDIA GPU)
3. Running **Llama 3.1 7B** 
4. (Optional) Running everything in Docker

---

### System Requirements

* Ubuntu 20.04+
* 8GB RAM minimum (16GB recommended)
* ~10GB disk space

---

# Step 1: Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Verify:

```bash
ollama --version
```

---

# Step 2: Start Ollama

```bash
ollama serve
```

Or background:

```bash
nohup ollama serve > ollama.log 2>&1 &
```

---

# Step 3: Pull & Run Llama 3.1 (7B)

```bash
ollama pull llama3.1:7b
```

```bash
ollama run llama3.1:7b
```

---

# Step 4: Enable GPU with CUDA (NVIDIA Only)

## What You’re Installing

* GPU drivers
* CUDA toolkit (enables GPU compute which significantly increases model performance)
* Verification tools

---

## 4.1 Check for NVIDIA GPU

```bash
lspci | grep -i nvidia
```

If nothing shows → CUDA won’t work on this machine.

---

## 4.2 Install NVIDIA Drivers

```bash
sudo apt update
sudo apt install -y nvidia-driver-535
```

Reboot:

```bash
sudo reboot
```

Verify:

```bash
nvidia-smi
```

You should see GPU info and driver version.

---

## 4.3 Install CUDA Toolkit

Download CUDA (example for Ubuntu):

```bash
sudo apt install -y nvidia-cuda-toolkit
```

Verify:

```bash
nvcc --version
```

---

## 4.4 Ensure Ollama Uses GPU

Restart Ollama:

```bash
pkill ollama
ollama serve
```

Then run:

```bash
ollama run llama3.1:7b
```

---

## 4.5 Confirm GPU Usage

In another terminal:

```bash
watch -n 1 nvidia-smi
```

If working correctly:

* You’ll see VRAM usage increase
* A process like `ollama` using GPU

---

## Common CUDA Issues

### GPU not detected

* Driver not installed correctly
* Reboot missing

### Ollama still using CPU

Try:

```bash
OLLAMA_DEBUG=1 ollama run llama3.1:7b
```

---

# Optional: Run Ollama with Docker (GPU Enabled)

## 5.1 Install Docker

```bash
sudo apt update
sudo apt install -y docker.io
sudo systemctl enable docker
sudo systemctl start docker
```

Add user to docker group:

```bash
sudo usermod -aG docker $USER
```

Log out/in after this.

---

## 5.2 Install NVIDIA Container Toolkit

This allows Docker to access your GPU.

```bash
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)

curl -s -L https://nvidia.github.io/libnvidia-container/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update
sudo apt install -y nvidia-container-toolkit
```

Restart Docker:

```bash
sudo systemctl restart docker
```

---

## 5.3 Run Ollama Container (GPU Enabled)

```bash
docker run -d \
  --gpus all \
  -v ollama:/root/.ollama \
  -p 11434:11434 \
  --name ollama \
  ollama/ollama
```

---

## 5.4 Pull Model Inside Docker

```bash
docker exec -it ollama ollama pull llama3.1:7b
```

Run it:

```bash
docker exec -it ollama ollama run llama3.1:7b
```

---

## 5.5 Verify GPU in Docker

```bash
docker exec -it ollama nvidia-smi
```

---

# Model Management

```bash
ollama list
ollama rm llama3.1:7b
```

---

# Notes

If the main app is running on the same machine as ollama, docker is not going to be necessary for connection, but you will need to rewire the ollama connection in ```llm_connect.py``` as its currently wired to connect to a remote machine that is using docker. When the main app runs on the same machine, the wiring of the llm connection is much more simple as it will just need to make a request to the already running Ollama. There is no need to connect remotely, and interface with docker, you can interface with Ollama directly. 


