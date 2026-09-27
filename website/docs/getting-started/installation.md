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
Build the desktop app from the repository after installing the CLI. Prebuilt Jetts-TUI desktop releases will be linked here once published; the old project's installer does not install Jetts-TUI.

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
freeide desktop
```

### What the Installer Does

The installer handles everything automatically — all dependencies (Python, Node.js, ripgrep, ffmpeg), the repo clone, virtual environment, global `freeide` command setup, and LLM provider configuration. By the end, you're ready to chat.

#### Install Layout

Where the installer puts things depends on whether you're installing as a normal user or as root:

| Installer                              | Code lives at                  | `freeide` binary                         | Data directory                       |
| -------------------------------------- | ------------------------------ | --------------------------------------- | ------------------------------------ |
| Per-user (git installer)               | `~/.freeide/freeide-agent/`      | `~/.local/bin/freeide` (symlink)         | `~/.freeide/`                         |
| Root-mode (`sudo curl … \| sudo bash`) | `/usr/local/lib/freeide-agent/` | `/usr/local/bin/freeide`                 | `/root/.freeide/` (or `$FREEIDE_HOME`) |

The root-mode **FHS layout** (`/usr/local/lib/…`, `/usr/local/bin/freeide`) matches where other system-wide developer tools land on Linux. It's useful for shared-machine deployments where one system install should serve every user. Per-user config (auth, skills, sessions) still lives under each user's `~/.freeide/` or explicit `FREEIDE_HOME`.

### After Installation

Reload your shell and start chatting:

```bash
source ~/.bashrc   # or: source ~/.zshrc
freeide             # Start chatting!
```

To reconfigure individual settings later, use the dedicated commands:

```bash
freeide model          # Choose your LLM provider and model
freeide tools          # Configure which tools are enabled
freeide gateway setup  # Set up messaging platforms
freeide config set     # Set individual config values
freeide config get     # Inspect individual config values
freeide setup          # Or run the full setup wizard to configure everything at once
```

:::tip Fastest path: pick a provider
FreeIDE is bring-your-own-key. Run the setup wizard, pick a free or paid provider, and paste an API key (or use a provider's own OAuth like openai-codex, xai-oauth, or qwen-oauth):

```bash
freeide setup
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

Running FreeIDE as a dedicated unprivileged user (e.g. a `freeide` systemd service account, or any user without `sudo` access) is supported. The only thing on the install path that genuinely needs root is Playwright's `--with-deps` step, which `apt`-installs shared libraries (`libnss3`, `libxkbcommon`, etc.) used by Chromium. The installer detects whether sudo is available and gracefully degrades when it isn't — it will install the Chromium binary into the service user's own Playwright cache and print the exact command an administrator needs to run separately.

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

3. **Make `freeide` available to the service user's shells.** The installer writes the launcher to `~/.local/bin/freeide`. System service accounts often have a minimal PATH that doesn't include `~/.local/bin`. Either add it to the user's environment, or symlink the launcher into a system location:
   ```bash
   # Option A — add to the service user's profile
   echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

   # Option B — symlink system-wide (run as an admin)
   sudo ln -s /home/freeide/.freeide/freeide-agent/venv/bin/freeide /usr/local/bin/freeide
   ```

4. **Verify:** `freeide doctor` should now run cleanly. If you get `ModuleNotFoundError: No module named 'dotenv'`, you're invoking the repo source `freeide` file (`~/.freeide/freeide-agent/freeide`) with system Python instead of the venv launcher (`~/.freeide/freeide-agent/venv/bin/freeide`) — fix step 3.

The same pattern works on Arch (the installer uses pacman with the same sudo-detection logic), Fedora/RHEL, and openSUSE — those distros don't support `--with-deps` at all, so an administrator always installs the system libraries separately. The relevant `dnf`/`zypper` commands are printed by the installer.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `freeide: command not found` | Reload your shell (`source ~/.bashrc`) or check PATH |
| `API key not set` | Run `freeide model` to configure your provider, or `freeide config set OPENROUTER_API_KEY your_key` |
| Missing config after update | Run `freeide config check` then `freeide config migrate` |

For more diagnostics, run `freeide doctor` — it will tell you exactly what's missing and how to fix it.

## Install method auto-detection

FreeIDE auto-detects whether it was installed via the git installer, Docker, or NixOS, and `freeide update` prints the matching update command for that path. There's no env var to set — the detection is based on the install layout (`~/.freeide/freeide-agent/` checkout, Docker image stamp, or Nix store path). `freeide doctor` also surfaces the detected method under its environment summary.
