# Linux Game Benchmark (lgb)

Automated benchmark tool for Steam games on Linux.
Measures FPS, stutter, frame pacing and more using MangoHud.

![Benchmark Results on linuxgamebench.com](docs/update_e.png)

## Features

- Automatic Steam game detection
- MangoHud integration for frametimes
- Detailed metrics (AVG FPS, 1% Low, 0.1% Low, Stutter)
- Multi-resolution support (HD, FHD, WQHD, UWQHD, UHD)
- **Multi-GPU support** (laptops with iGPU + dGPU)
- Beautiful HTML reports with interactive charts
- Multi-system comparison (compare different GPUs/CPUs)
- Upload to community database at [linuxgamebench.com](https://linuxgamebench.com)
- Automatic update notifications

## Requirements

- Linux (tested on Arch, Fedora, Ubuntu, openSUSE)
- Steam installed
- MangoHud installed
- Vulkan tools (`vulkaninfo`) for GPU detection
- Python 3.10+


## Installation

### Arch Linux / CachyOS (Recommended)

```bash
# Install MangoHud and Vulkan tools
sudo pacman -S mangohud lib32-mangohud vulkan-tools

# Install pipx (manages Python CLI tools)
sudo pacman -S python-pipx

# Install the tool
pipx install git+https://github.com/taaderbe/linuxgamebench.git
```

### Ubuntu/Debian

```bash
sudo apt install mangohud vulkan-tools pipx
pipx install git+https://github.com/taaderbe/linuxgamebench.git
```

### Fedora

```bash
# Install MangoHud and Vulkan tools
sudo dnf install mangohud vulkan-tools

# Install pipx
sudo dnf install pipx

# Install the tool
pipx install git+https://github.com/taaderbe/linuxgamebench.git
```

### openSUSE Tumbleweed

```bash
# All packages available in main repo
sudo zypper install mangohud vulkan-tools python313-pipx

# Install the tool
pipx install git+https://github.com/taaderbe/linuxgamebench.git
```

### Update to Latest Version

```bash
pipx uninstall linux-game-benchmark
pipx install git+https://github.com/taaderbe/linuxgamebench.git
```

### Install from Source (Development)

```bash
git clone https://github.com/taaderbe/linuxgamebench
cd linuxgamebench
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Quick Start

### 1. Check System

```bash
lgb check
```

This will:
- Verify MangoHud, Steam and other tools are installed
- Automatically enable MangoHud globally (asks for confirmation)
- After enabling, log out and back in for changes to take effect

### 2. List Steam Games

```bash
# Scan and show all installed Steam games
lgb list-games

# Refresh game list (after installing new games)
lgb scan

# Filter: only Proton/Windows games
lgb list-games --proton

# Filter: only native Linux games
lgb list-games --native
```

Example output:
```
┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┓
┃ App ID   ┃ Name                        ┃ Type    ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━┩
│ 1245620  │ Elden Ring                  │ Proton  │
│ 1174180  │ Red Dead Redemption 2       │ Proton  │
│ 427520   │ Factorio                    │ Native  │
└──────────┴─────────────────────────────┴─────────┘
```

### 3. Start a Game Benchmark

```bash
# By game name
lgb benchmark "Elden Ring"

# By Steam App ID
lgb benchmark 1245620

# With auto-stop after 60 seconds
lgb benchmark "Factorio" --duration 60
```

**How it works:**
1. lgb launches the game via Steam
2. Press **Shift+F2** in-game to start recording
3. Press **Shift+F2** again to stop (or wait for --duration)
4. Select resolution and optionally upload to community database
5. Repeat for more recordings or exit

---

## ⚡ Game Settings - Better Comparisons!

**The more settings you specify, the better you can compare your results with others!**

When running a benchmark, you can specify your in-game graphics settings. This allows the community to compare apples-to-apples: same game, same resolution, same settings.

### Quick Examples

```bash
# Basic benchmark with preset
lgb benchmark "Cyberpunk 2077" --preset ultra --raytracing high

# Full settings for best comparison
lgb benchmark "Cyberpunk 2077" \
  --preset ultra \
  --raytracing pathtracing \
  --upscaling dlss3.5 \
  --upscaling-quality quality \
  --framegen dlss3-fg \
  --hdr on

# AMD setup
lgb benchmark "Baldurs Gate 3" \
  --preset ultra \
  --upscaling fsr3 \
  --upscaling-quality balanced \
  --framegen afmf2
```

### All Available Settings

| Option | Values |
|--------|--------|
| `--preset` | Low / Medium / High / Ultra / Custom |
| `--raytracing` | Off / Low / Medium / High / Ultra / Pathtracing |
| `--upscaling` | None / FSR1 / FSR2 / FSR3 / FSR4 / DLSS / DLSS2 / DLSS3 / DLSS3.5 / DLSS4 / DLSS4.5 / XeSS / XeSS1 / XeSS2 / TSR |
| `--upscaling-quality` | Performance / Balanced / Quality / Ultra-Quality |
| `--framegen` | Off / FSR3-FG / DLSS3-FG / DLSS4-FG / DLSS4-MFG / XeSS-FG / AFMF / AFMF2 / AFMF3 / Smooth-Motion |
| `--aa` | None / FXAA / SMAA / TAA / DLAA / MSAA |
| `--hdr` | On / Off |
| `--vsync` | On / Off |
| `--framelimit` | None / 30 / 60 / 120 / 144 / 165 / 240 / 360 |
| `--cpu-oc` | Yes / No (+ `--cpu-oc-info "5.0GHz"`) |
| `--gpu-oc` | Yes / No (+ `--gpu-oc-info "+150MHz"`) |

### Configure Defaults

Don't want to type settings every time? Set your defaults:

```bash
lgb settings
```

This opens an interactive menu where you can set your default preset, raytracing, upscaling, etc. These defaults are used automatically when you don't specify them on the command line.

**Tip:** Run `lgb` or `lgb --help` to see all available settings at a glance!

---

### 4. View Report

```bash
xdg-open ~/benchmark_results/index.html
```

![Local HTML Report](docs/screenshot_local_report.png)

## Commands

| Command | Description |
|---------|-------------|
| `lgb check` | Check system requirements |
| `lgb list-games` | Show installed Steam games |
| `lgb scan` | Scan Steam library |
| `lgb info` | Show system information |
| `lgb gpu` | Show detected GPUs and configure default |
| `lgb benchmark [game]` | Launch game and benchmark |
| `lgb analyze [log]` | Analyze MangoHud log |
| `lgb report` | Regenerate HTML reports |
| `lgb settings` | Configure defaults (resolution, upload, etc.) |
| `lgb login` | Login to your account |
| `lgb logout` | Logout from your account |
| `lgb status` | Show login status and account info |

## Metrics

| Metric | Description |
|--------|-------------|
| **AVG FPS** | Average frames per second |
| **1% Low** | Lowest 1% of frametimes (shows micro stutters) |
| **0.1% Low** | Lowest 0.1% of frametimes (extreme stutters) |
| **Stutter** | How often do stutters occur? (excellent/good/moderate/poor) |
| **Consistency** | How consistent is the framerate? |

## Results Structure

```
~/benchmark_results/
    index.html                    # Overview of all games
    Baldurs_Gate_3/
        CachyOS_abc123/           # System 1
            FHD/
                run_001.json
            WQHD/
                run_001.json
        EndeavourOS_def456/       # System 2
            UHD/
                run_001.json
        report.html               # Game report with tabs
```

**Important:**
- Data is **NEVER deleted** - all benchmarks are preserved
- Each system gets its own folder
- Reports show all systems with tabs to switch between them

## MangoHud Setup

MangoHud is automatically configured when you run `lgb check`. Just log out and back in after.

**Manual setup (if needed):**
```bash
mkdir -p ~/.config/environment.d
echo "MANGOHUD=1" >> ~/.config/environment.d/mangohud.conf
# Then log out and back in
```

## Upload Results

Share your benchmarks at **[linuxgamebench.com](https://linuxgamebench.com)** and compare your hardware with the community!

Benchmarks are automatically uploaded after each `lgb benchmark` run. **No login required!**

```bash
lgb benchmark CS2  # Run benchmark - uploads automatically
```

**Optional:** Create an account for extra features (track your benchmarks, better compare, edit settings):
```bash
lgb login          # Login to your account
```

## Multi-GPU Systems

The tool handles multiple GPUs automatically:

1. **MangoHud Log GPU** (Primary): The GPU that actually rendered the game is detected from the log
2. **Saved Default**: For systems with multiple discrete GPUs (e.g., 2x RTX 4090), you can set a default
3. **Auto-Detection**: Falls back to discrete GPU over integrated

```bash
# View all detected GPUs
lgb gpu

# Set default GPU for multi-GPU systems
lgb gpu --set

# Clear saved default
lgb gpu --clear
```

On first benchmark with multiple discrete GPUs, you'll be prompted to select one. The selection is saved for future benchmarks.

## FAQ

### Why is Vulkan required?

The tool uses `vulkaninfo` to detect the exact GPU model. This is the most reliable method across all GPU vendors (AMD, NVIDIA, Intel) and works for GPUs released in the last 10+ years.

**Don't worry:** If you're gaming on Linux, you already have Vulkan installed - it's required for Steam/Proton and MangoHud.

### Which GPUs are supported?

Any GPU with Vulkan support:
- **NVIDIA**: GeForce GTX 600 series and newer (2012+)
- **AMD**: Radeon HD 7000 series and newer (2012+)
- **Intel**: Skylake (HD 520/530) and newer (2015+)

### How do I check if Vulkan is installed?

```bash
vulkaninfo --summary
```

If this shows your GPU, you're good to go!

### My GPU shows as "Unknown" - what do I do?

1. Make sure `vulkan-tools` is installed
2. Run `lgb check` to verify all requirements
3. If still not working, run `lgb gpu` to see what's detected

## License

GPL-3.0 License

## Contributing

Pull requests are welcome! Please create an issue first to discuss the change.
