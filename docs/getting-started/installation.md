---
sidebar_position: 2
title: "Installation"
description: "Install Jetts-TUI on Linux, macOS, WSL2, native Windows, or Android via Termux"
---

# Installation

Get Jetts-TUI up and running.

:::tip Platform Support
For the full platform support matrix (which OSes, distribution methods, and
platform-gated features are supported), see **[Platform Support](./platform-support.md)**.
:::

## Quick Install
### Desktop app on macOS or Windows
Build the desktop app from the repository after installing Jetts-TUI. Prebuilt desktop releases will be linked here once published.

### Terminal install
For a terminal install, run:

#### Linux / macOS / WSL2 / Android (Termux)
```bash
curl -fsSL https://raw.githubusercontent.com/Raioshok/JETTS-TUI/main/scripts/install.sh | bash
```

#### Windows (native)

Run in powershell:
```powershell
iex (irm https://raw.githubusercontent.com/Raioshok/JETTS-TUI/main/scripts/install.ps1)
```

To build and run the desktop app from a source install, run
```bash
jetts-tui desktop
```

### What the Installer Does

The installer handles dependencies (Python, Node.js, ripgrep, ffmpeg), the repo clone, virtual environment, global `jetts-tui` command setup, and LLM provider configuration.

#### Install Layout

Where the installer puts things depends on whether you're installing as a normal user or as root:

| Installer | Fresh code checkout | `jetts-tui` launcher | Data directory |
| --- | --- | --- | --- |
| Per-user | `~/.jettstui/jettstui/` | `~/.local/bin/jetts-tui` | `~/.jettstui/` |
| Root-mode (Linux) | `/usr/local/lib/jettstui/` | `/usr/local/bin/jetts-tui` | `/root/.jettstui/` (or `$FREEIDE_HOME`) |
| Native Windows | `%LOCALAPPDATA%\jettstui\jettstui\` | `venv\Scripts\jetts-tui.exe` on user PATH | `%LOCALAPPDATA%\jettstui\` |

The root-mode FHS layout is useful for shared-machine deployments. Per-user config (auth, skills, sessions) lives under each user's `~/.jettstui/` or explicit `FREEIDE_HOME`. Existing `freeide-agent` checkouts are retained at their original paths during migration, and the `freeide` command remains a compatibility alias.

### After Installation

Reload your shell and start chatting:

```bash
source ~/.bashrc   # or: source ~/.zshrc
jetts-tui           # Start chatting!
```

To reconfigure individual settings later, use the dedicated commands:

```bash
jetts-tui model          # Choose your LLM provider and model
jetts-tui tools          # Configure which tools are enabled
jetts-tui gateway setup  # Set up messaging platforms
jetts-tui config set     # Set individual config values
jetts-tui config get     # Inspect individual config values
jetts-tui setup          # Or run the full setup wizard to configure everything at once
```

:::tip Fastest path: pick a provider
Jetts-TUI is bring-your-own-key. Run the setup wizard, pick a free or paid provider, and paste an API key (or use a provider's own OAuth like openai-codex, xai-oauth, or qwen-oauth):

```bash
jetts-tui setup
```

That walks you through choosing your provider and model in one command.
:::

---

## Prerequisites

**Installer:** On non-Windows platforms, the only prerequisite is **Git**. On Linux, also make sure `curl` and `xz-utils` are available (the installer downloads Node.js as a `.tar.xz` archive). The desktop app additionally requires `g++` (or `build-essential` on Debian/Ubuntu) to compile native modules. The installer automatically handles everything else:

- **uv** (fast Python package manager)
- **Python 3.11** (via uv, no sudo needed)
- **Node.js v22** (for browser automation and WhatsApp bridge)
- **ripgrep** (fast file search)
- **ffmpeg** (audio format conversion for TTS)

:::info
You do **not** need to install Python, Node.js, ripgrep, or ffmpeg manually. The installer detects what's missing and installs it for you. Just make sure `git` is available (`git --version`). On Linux, ensure `curl` and `xz-utils` are installed (`sudo apt install curl xz-utils` on Debian/Ubuntu). For the desktop app, also install `build-essential` (`sudo apt install build-essential`).
:::

:::tip Nix users
Nix is **no longer an explicitly supported install path** (best-effort only). If you already use Nix (on NixOS, macOS, or Linux), there's a dedicated setup path with a Nix flake, declarative NixOS module, and optional container mode. See the **[Nix & NixOS Setup](./nix-setup.md)** guide.
:::

---

## Manual / Developer Installation

If you want to clone the repo and install from source — for contributing, running from a specific branch, or having full control over the virtual environment — see the [Development Setup](../developer-guide/contributing.md#development-setup) section in the Contributing guide.

For the fastest local-checkout bootstrap, clone the repository and run the
platform helper from its root:

```bash title="Linux / macOS / WSL2"
bash setup-jetts-tui.sh
```

```powershell title="Native Windows"
.\setup-jetts-tui.ps1
```

If PowerShell blocks local scripts, run
`powershell -NoProfile -ExecutionPolicy Bypass -File .\setup-jetts-tui.ps1`.

Both helpers update an existing local environment by default. Use
`--recreate` on Linux or `-Recreate` on Windows only when you want a clean
environment, and use `--skip-setup` / `-SkipSetup` to postpone provider setup.

---

## Non-Sudo / System Service User Installs

Running Jetts-TUI as a dedicated unprivileged service user is supported. The Playwright `--with-deps` step needs root to install Chromium system libraries (`libnss3`, `libxkbcommon`, etc.). Without sudo, the installer installs the browser binary into the service user's cache and prints the separate administrator command.

**Recommended split (Debian/Ubuntu):**

1. **One time, as an admin user with sudo**, install the system libraries Chromium needs:
   ```bash
   sudo npx playwright install-deps chromium
   ```
   (You can run this from anywhere — `npx` will fetch Playwright on the fly.)

2. **As the unprivileged service user**, run the regular installer. It will detect the missing sudo, skip `--with-deps`, and install Chromium into the user's local Playwright cache:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/Raioshok/JETTS-TUI/main/scripts/install.sh | bash
   ```

   If you want to skip the Playwright step entirely — for example because you're running headless and don't need browser automation — pass `--skip-browser`:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/Raioshok/JETTS-TUI/main/scripts/install.sh | bash -s -- --skip-browser
   ```

3. **Make `jetts-tui` available to the service user's shells.** The installer writes the launcher to `~/.local/bin/jetts-tui`. System service accounts often have a minimal PATH that doesn't include `~/.local/bin`. Add it to the service user's environment:
   ```bash
   echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
   ```

4. **Verify:** `jetts-tui doctor` should now run. If you get `ModuleNotFoundError` for a dependency, check that your shell resolves the installed launcher rather than a source file run with system Python (`command -v jetts-tui`).

The same pattern works on Arch (the installer uses pacman with the same sudo-detection logic), Fedora/RHEL, and openSUSE — those distros don't support `--with-deps` at all, so an administrator always installs the system libraries separately. The relevant `dnf`/`zypper` commands are printed by the installer.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `jetts-tui: command not found` | Reload your shell (`source ~/.bashrc`) or check PATH |
| `API key not set` | Run `jetts-tui setup`; credentials belong in the active home's `.env`, not `config.yaml` |
| Missing config after update | Run `jetts-tui config check` then `jetts-tui config migrate` |

For more diagnostics, run `jetts-tui doctor` — it will tell you what's missing and how to fix it.

## Install method auto-detection

Jetts-TUI auto-detects git, Docker, or Nix installs, and `jetts-tui update` prints the matching update command. Detection uses the checkout, Docker image stamp, or Nix store path; `jetts-tui doctor` reports the detected method. Legacy checkouts at `~/.freeide/freeide-agent/` remain supported during migration.
