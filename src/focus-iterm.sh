#!/bin/zsh
# Focus the iTerm2 window/tab that owns the given TTY
TTY_PATH="$1"
osascript <<EOF
tell application "iTerm2"
    activate
    repeat with w in windows
        tell w
            repeat with t in tabs
                repeat with s in sessions of t
                    if tty of s is "$TTY_PATH" then
                        select t
                        set index of w to 1
                        return
                    end if
                end repeat
            end repeat
        end tell
    end repeat
end tell
EOF
