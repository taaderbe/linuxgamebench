# Linux Game Benchmark (lgb)

Automated benchmark tool for Steam games on Linux.
Measures FPS, stutter, frame pacing and more using MangoHud.

## Features

- Automatic Steam game detection
- MangoHud integration for frametimes
- Detailed metrics (AVG FPS, 1% Low, 0.1% Low, Stutter)
- Multi-resolution support (FHD, WQHD, UHD)
- Beautiful HTML reports with interactive charts
- Multi-system comparison (compare different GPUs/CPUs)
- Upload to community database

## Requirements

- Linux (tested on Arch, Fedora, Ubuntu)
- Steam installed
- MangoHud installed
- Python 3.10+

Optional:
- Gamescope (for resolution tests)
- GameMode (for performance optimization)

## Installation

### Arch Linux / CachyOS (Recommended)

```bash
# Install MangoHud and optional tools
sudo pacman -S mangohud lib32-mangohud gamemode lib32-gamemode gamescope

# Install pipx (manages Python CLI tools)
sudo pacman -S python-pipx

# Install the tool
pipx install git+https://github.com/taaderbe/linuxgamebench.git
```

### Ubuntu/Debian

```bash
sudo apt install mangohud pipx
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
lgb list
```

### 3. Start Benchmark

```bash
# Interactive mode (recommended)
lgb record_manual
```

**How record_manual works:**
1. lgb configures MangoHud and waits
2. Start your game with `MANGOHUD=1 %command%` in Steam launch options
3. Press **Shift+F2** in-game to start recording (60 seconds)
4. Return to terminal: enter game name and resolution
5. Repeat for more recordings or exit

### 4. View Report

```bash
xdg-open ~/benchmark_results/index.html
```

## Commands

| Command | Description |
|---------|-------------|
| `lgb check` | Check system requirements |
| `lgb list` | Show installed Steam games |
| `lgb scan` | Scan Steam library |
| `lgb info` | Show system information |
| `lgb record_manual` | Manual recording mode (recommended) |
| `lgb record [game]` | Auto-launch game and record |
| `lgb analyze [log]` | Analyze MangoHud log |
| `lgb report` | Regenerate HTML reports |
| `lgb status` | Show login status |
| `lgb login` | Login with Steam account |
| `lgb logout` | Logout from Steam |
| `lgb upload` | Upload benchmarks to community database |

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

```bash
# Link Steam account
lgb login

# Benchmark will prompt for upload
lgb record "Cyberpunk 2077"
# → "Upload to community database? [Y/n]"

# Or upload existing benchmarks
lgb upload
```

## License

MIT License

## Contributing

Pull requests are welcome! Please create an issue first to discuss the change.
