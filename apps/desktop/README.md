# Jetts-TUI Desktop

The desktop app is a native Electron interface to the same Jetts-TUI agent runtime used by the terminal UI and messaging gateway. It provides streaming chat, tool activity, project navigation, previews, voice, and settings without requiring a terminal window.

See the [main README](../../README.md) for source installation and the [documentation](../../docs/) for setup and configuration. This repository does not publish a separate documentation website. Desktop installers are intended for [Jetts-TUI releases](https://github.com/Raioshok/JETTS-TUI/releases); check that page for actual availability before relying on a prebuilt installer.

## Run from a checkout

Install Jetts-TUI using the platform script in the repository root, then run:

```bash
jetts-tui desktop
```

The app uses the same configuration, credentials, sessions, and skills as the TUI. First launch can connect to an existing gateway or set up a local runtime.

## Develop

From the repository root:

```bash
npm install
cd apps/desktop
npm run dev
```

For an isolated development profile, use `../scripts/dev-sandbox.sh npm run dev` on a supported POSIX shell. `npm run dev:fake-boot` exercises the startup overlay without a real backend.

The desktop app is an independent chat surface. Electron starts the headless `jetts-tui serve` backend; React renders the desktop transcript; `@jetts-tui/shared` carries the JSON-RPC/WebSocket transport. The browser dashboard instead embeds the Ink TUI in a PTY. For architecture and contribution rules, read [AGENTS.md](AGENTS.md) and [DESIGN.md](DESIGN.md).

## Build and verify

```bash
npm run typecheck
npm run lint
npm run test:ui
npm run test:desktop:platforms
npm run build
```

For changes to installation, startup, updates, or packaging, also run `npm run test:desktop:all`. Installer targets are `npm run dist:mac`, `npm run dist:win`, and `npm run dist:linux`; packaging and signing require the relevant host and credentials.

## Troubleshooting

Backend boot logs are under `FREEIDE_HOME/logs/desktop.log`. Without a `FREEIDE_HOME` override, Jetts-TUI uses `~/.jettstui` on POSIX and `%LOCALAPPDATA%\jettstui` on Windows. The `FREEIDE_HOME` environment variable is retained for compatibility with existing installations.

If the app cannot start a local backend, check that `jetts-tui --version` works from a new shell, then inspect the boot log. For persistent problems, open an [issue](https://github.com/Raioshok/JETTS-TUI/issues) with the platform, app version, and redacted log excerpt.

MIT licensed; see [LICENSE](../../LICENSE) for copyright and third-party notices.
