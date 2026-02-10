# Claude Code SwiftBar Status

A [SwiftBar](https://github.com/swiftbar/SwiftBar) plugin that shows the status of your running Claude Code sessions in the macOS menu bar.

## Status Indicators

| Icon | Color | Meaning |
|------|-------|---------|
| Filled circle | Green | Session is actively running (transcript updated within 15s) |
| Exclamation circle | Orange | Session is waiting for tool approval |
| Filled circle | Gray | Session is idle |
| Dashed circle | Dark | No Claude process detected for this slot |

The menu bar icon reflects the most urgent status across all sessions. Click to expand the dropdown and see each session individually, with project name and per-session click-to-focus.

## Prerequisites

- macOS
- [SwiftBar](https://github.com/swiftbar/SwiftBar)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI
- [iTerm2](https://iterm2.com/) (for click-to-focus)
- Python 3 (ships with macOS)

## Installation

1. Clone this repository:

   ```sh
   git clone https://github.com/<your-username>/claude-swiftbar-status.git
   ```

2. Create a symlink in your SwiftBar plugins directory. The filename determines the refresh interval (e.g. `2s` = every 2 seconds):

   ```sh
   ln -s /path/to/claude-swiftbar-status/ClaudeBar.sh \
     "$(defaults read com.ameba.SwiftBar PluginDirectory)/ClaudeBar.2s.sh"
   ```

3. SwiftBar will pick it up automatically. You can adjust the refresh interval by changing the filename (e.g. `ClaudeBar.1s.sh`, `ClaudeBar.5s.sh`).

## Configuration

Edit `MAX_SESSIONS` at the top of `ClaudeBar.sh` to change how many Claude sessions to monitor (default: 3).

## How It Works

1. Finds running `claude` processes via `pgrep` and maps each to its TTY and working directory.
2. Locates the Claude Code transcript (`.jsonl`) for each session under `~/.claude/projects/`.
3. Determines status by checking transcript age and whether the last assistant message contains a pending tool use.
4. Outputs SwiftBar-formatted lines with SF Symbols.
5. Clicking a session in the dropdown runs `focus-iterm.sh`, which uses AppleScript to activate the iTerm2 tab owning that TTY.

## Files

- **`ClaudeBar.sh`** - Main SwiftBar plugin script
- **`focus-iterm.sh`** - Helper that focuses the iTerm2 tab for a given TTY

## License

MIT
