# Claude Bar

Native macOS menu bar app for live Claude Code and Codex session status.
It auto-discovers running sessions and hides itself when no sessions are active.

![demo](doc/example.gif)

## Features

- Single icon shows one `cpu.fill` SF Symbol per detected session.
- Colors map to status:
  - Green: running
  - Orange: waiting for user action
  - Gray: idle
- Pending and idle sessions use a breathing animation.
- Click menu item to focus the matching terminal window (iTerm2 / Alacritty).
- Supports mixed environments (including tmux/zellij sessions via fallback detection).

## Prerequisites

- macOS
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI and/or [Codex CLI](https://developers.openai.com/codex)
- [Rust toolchain](https://rustup.rs/) (for building `claude-bar`)
- Xcode Command Line Tools (`swiftc`)
- iTerm2 and/or Alacritty for best focus support

## Install

```sh
git clone https://github.com/qianxiaofeng/claude-menubar.git
cd claude-menubar
./install.sh
```

`install.sh` will:

- build `target/release/claude-bar` (Rust)
- build `target/release/claude-bar-app` (Swift)
- install/start LaunchAgent `com.claude.claude-bar-daemon`
- register Claude Code `SessionStart` hook: `claude-bar hook`

After install, the menu bar item appears automatically when sessions are detected.

## Uninstall

```sh
./uninstall.sh
```

This removes the LaunchAgent, cleans hook entries from `~/.claude/settings.json`, and deletes local state files under `~/.claude/claude-bar`.

## Status Semantics

### Claude sessions

- `pending`: unpaired `tool_use` waiting for user action (with grace/timeout logic)
- `active`: recent transcript activity, or last message from user while Claude is working
- `idle`: assistant done and no pending work

### Codex sessions

- `pending`: at least one pending `function_call` requesting `sandbox_permissions=require_escalated`
- `active`: pending non-escalation call, or very recent session activity
- `idle`: no pending calls and session not recently updated

## CLI

```sh
# One-shot poll; prints JSON array of SessionInfo
target/release/claude-bar poll

# SessionStart hook (reads JSON from stdin, writes session state file)
target/release/claude-bar hook

# Install/uninstall hook entries in settings.json
target/release/claude-bar hooks-install --command "target/release/claude-bar hook"
target/release/claude-bar hooks-uninstall

# Focus terminal window for a session
target/release/claude-bar focus --terminal iterm2 --tty /dev/ttys003 --cwd /path/to/project
```

`poll` output fields:

- `tty`, `pid`, `cwd`
- `provider` (`claude` or `codex`)
- `terminal` (`iterm2`, `alacritty`, `unknown`)
- `transcript` (optional path)
- `status` (`active`, `pending`, `idle`)

## Architecture

```
claude-bar-app (Swift, NSStatusItem, launchd-managed)
  -> polls `claude-bar poll` every 2s
  -> renders SF Symbols + menu
  -> calls `claude-bar focus` on click

claude-bar (Rust)
  poll  -> detect claude/codex processes + terminal TTYs + transcript status
  hook  -> SessionStart hook state writer
  focus -> terminal focus action
```

Main data locations:

- Claude transcripts: `~/.claude/projects/<project-hash>/*.jsonl`
- Codex sessions: `~/.codex/sessions/**/*.jsonl`
- Hook state cache: `~/.claude/claude-bar/<project-hash>/session-<tty>.json`

## Troubleshooting

- Check daemon logs:
  - `/tmp/claude-bar.out.log`
  - `/tmp/claude-bar.err.log`
- Verify polling manually:
  - `target/release/claude-bar poll`
- If focusing Alacritty fails, ensure Accessibility permissions allow window control via System Events.
- If no sessions appear, confirm `claude`/`codex` are running in interactive TTYs (not detached `??` processes).

## Source Modules

| Module | Purpose |
|--------|---------|
| `src/main.rs` | CLI entry point (`poll`, `hook`, `focus`) |
| `src/serve.rs` | Session discovery and aggregation |
| `src/process.rs` | Process/TTY/CWD discovery via `pgrep`/`ps`/`lsof` |
| `src/transcript.rs` | Claude/Codex JSONL parsing and status determination |
| `src/terminal.rs` | iTerm2 + Alacritty session enumeration and merge |
| `src/settings.rs` | Hook settings.json install/uninstall management |
| `src/state.rs` | Core data models (`SessionInfo`, `Status`, `Provider`, `Terminal`) |
| `src/hook.rs` | Claude SessionStart hook handler |
| `src/focus.rs` | iTerm2/Alacritty window focusing |
| `swift/ClaudeBar.swift` | AppKit menu bar UI |

## License

MIT
