use serde_json::{Map, Value};
use std::error::Error;
use std::fs;
use std::path::{Path, PathBuf};

const LEGACY_EVENTS: &[&str] = &[
    "UserPromptSubmit",
    "Stop",
    "Notification",
    "SessionEnd",
    "SessionStart",
];
const LEGACY_PATTERNS: &[&str] = &["update-status.sh", "session-track.sh"];
const UNINSTALL_PATTERNS: &[&str] = &["session-track.sh", "update-status.sh", "claude-bar"];

pub fn default_settings_path() -> PathBuf {
    let home = std::env::var("HOME").unwrap_or_default();
    PathBuf::from(home).join(".claude").join("settings.json")
}

pub fn install_session_start_hook(
    settings_path: &Path,
    hook_cmd: &str,
) -> Result<bool, Box<dyn Error>> {
    let mut cfg = read_settings_or_empty(settings_path)?;
    let cfg_obj = as_object_mut(&mut cfg, "settings root must be a JSON object")?;

    let hooks_val = cfg_obj
        .entry("hooks".to_string())
        .or_insert_with(|| Value::Object(Map::new()));
    let hooks_obj = as_object_mut(hooks_val, "`hooks` must be a JSON object")?;

    let mut changed = false;
    cleanup_event_patterns(hooks_obj, LEGACY_EVENTS, LEGACY_PATTERNS, &mut changed);

    let session_start = hooks_obj
        .entry("SessionStart".to_string())
        .or_insert_with(|| Value::Array(Vec::new()));
    let matchers = session_start
        .as_array_mut()
        .ok_or("`hooks.SessionStart` must be an array")?;

    let already = matchers
        .iter()
        .any(|matcher| matcher_has_command_containing(matcher, hook_cmd));
    if !already {
        matchers.push(serde_json::json!({
            "hooks": [
                {"type": "command", "command": hook_cmd}
            ]
        }));
        changed = true;
    }

    if hooks_obj.is_empty() {
        cfg_obj.remove("hooks");
    }

    if changed {
        write_settings(settings_path, &cfg)?;
    }
    Ok(changed)
}

pub fn uninstall_managed_hooks(settings_path: &Path) -> Result<bool, Box<dyn Error>> {
    if !settings_path.is_file() {
        return Ok(false);
    }

    let mut cfg = read_settings_file(settings_path)?;
    let cfg_obj = as_object_mut(&mut cfg, "settings root must be a JSON object")?;

    let mut changed = false;
    if let Some(hooks) = cfg_obj.get_mut("hooks") {
        let hooks_obj = as_object_mut(hooks, "`hooks` must be a JSON object")?;
        let events: Vec<String> = hooks_obj.keys().cloned().collect();
        cleanup_event_patterns(
            hooks_obj,
            &events_as_strs(&events),
            UNINSTALL_PATTERNS,
            &mut changed,
        );
        if hooks_obj.is_empty() {
            cfg_obj.remove("hooks");
            changed = true;
        }
    }

    // Keep behavior close to previous uninstall script: write file whenever it exists.
    write_settings(settings_path, &cfg)?;
    Ok(changed)
}

fn cleanup_event_patterns(
    hooks_obj: &mut Map<String, Value>,
    events: &[&str],
    patterns: &[&str],
    changed: &mut bool,
) {
    for event in events {
        let Some(existing) = hooks_obj.get(*event).and_then(|v| v.as_array()) else {
            continue;
        };
        let filtered: Vec<Value> = existing
            .iter()
            .filter(|m| !matcher_has_any_pattern(m, patterns))
            .cloned()
            .collect();
        if filtered.len() != existing.len() {
            *changed = true;
            if filtered.is_empty() {
                hooks_obj.remove(*event);
            } else {
                hooks_obj.insert((*event).to_string(), Value::Array(filtered));
            }
        }
    }
}

fn matcher_has_any_pattern(matcher: &Value, patterns: &[&str]) -> bool {
    patterns
        .iter()
        .any(|pattern| matcher_has_command_containing(matcher, pattern))
}

fn matcher_has_command_containing(matcher: &Value, needle: &str) -> bool {
    matcher
        .get("hooks")
        .and_then(|v| v.as_array())
        .map(|hooks| {
            hooks.iter().any(|h| {
                h.get("command")
                    .and_then(|v| v.as_str())
                    .map(|cmd| cmd.contains(needle))
                    .unwrap_or(false)
            })
        })
        .unwrap_or(false)
}

fn read_settings_or_empty(path: &Path) -> Result<Value, Box<dyn Error>> {
    if path.is_file() {
        read_settings_file(path)
    } else {
        Ok(Value::Object(Map::new()))
    }
}

fn read_settings_file(path: &Path) -> Result<Value, Box<dyn Error>> {
    let content = fs::read_to_string(path)?;
    let value: Value = serde_json::from_str(&content)?;
    Ok(value)
}

fn write_settings(path: &Path, value: &Value) -> Result<(), Box<dyn Error>> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut out = serde_json::to_string_pretty(value)?;
    out.push('\n');
    fs::write(path, out)?;
    Ok(())
}

fn as_object_mut<'a>(
    value: &'a mut Value,
    err_msg: &'static str,
) -> Result<&'a mut Map<String, Value>, Box<dyn Error>> {
    value.as_object_mut().ok_or_else(|| err_msg.into())
}

fn events_as_strs(events: &[String]) -> Vec<&str> {
    events.iter().map(String::as_str).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn read_json(path: &Path) -> Value {
        serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap()
    }

    #[test]
    fn install_creates_settings_and_hook() {
        let tmp = tempfile::TempDir::new().unwrap();
        let path = tmp.path().join("settings.json");

        let changed = install_session_start_hook(&path, "/tmp/claude-bar hook").unwrap();
        assert!(changed);

        let v = read_json(&path);
        let hooks = v.get("hooks").unwrap().as_object().unwrap();
        let session = hooks.get("SessionStart").unwrap().as_array().unwrap();
        assert_eq!(session.len(), 1);
    }

    #[test]
    fn install_is_idempotent_for_same_command() {
        let tmp = tempfile::TempDir::new().unwrap();
        let path = tmp.path().join("settings.json");

        install_session_start_hook(&path, "/tmp/claude-bar hook").unwrap();
        let changed = install_session_start_hook(&path, "/tmp/claude-bar hook").unwrap();
        assert!(!changed);

        let v = read_json(&path);
        let hooks = v.get("hooks").unwrap().as_object().unwrap();
        let session = hooks.get("SessionStart").unwrap().as_array().unwrap();
        assert_eq!(session.len(), 1);
    }

    #[test]
    fn install_removes_legacy_patterns() {
        let tmp = tempfile::TempDir::new().unwrap();
        let path = tmp.path().join("settings.json");
        let seed = serde_json::json!({
            "hooks": {
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": "/a/update-status.sh"}]},
                    {"hooks": [{"type": "command", "command": "/b/keep.sh"}]}
                ],
                "Stop": [
                    {"hooks": [{"type": "command", "command": "/x/session-track.sh"}]}
                ]
            }
        });
        write_settings(&path, &seed).unwrap();

        install_session_start_hook(&path, "/tmp/claude-bar hook").unwrap();
        let v = read_json(&path);
        let hooks = v.get("hooks").unwrap().as_object().unwrap();

        let stop = hooks.get("Stop");
        assert!(stop.is_none());

        let session = hooks.get("SessionStart").unwrap().as_array().unwrap();
        assert_eq!(session.len(), 2);
        assert!(session
            .iter()
            .any(|m| matcher_has_command_containing(m, "/b/keep.sh")));
        assert!(session
            .iter()
            .any(|m| matcher_has_command_containing(m, "/tmp/claude-bar hook")));
    }

    #[test]
    fn uninstall_removes_managed_hooks_only() {
        let tmp = tempfile::TempDir::new().unwrap();
        let path = tmp.path().join("settings.json");
        let seed = serde_json::json!({
            "hooks": {
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": "/tmp/claude-bar hook"}]},
                    {"hooks": [{"type": "command", "command": "/tmp/keep.sh"}]}
                ],
                "Notification": [
                    {"hooks": [{"type": "command", "command": "/tmp/update-status.sh"}]}
                ]
            }
        });
        write_settings(&path, &seed).unwrap();

        uninstall_managed_hooks(&path).unwrap();
        let v = read_json(&path);
        let hooks = v.get("hooks").unwrap().as_object().unwrap();

        let session = hooks.get("SessionStart").unwrap().as_array().unwrap();
        assert_eq!(session.len(), 1);
        assert!(matcher_has_command_containing(&session[0], "/tmp/keep.sh"));
        assert!(hooks.get("Notification").is_none());
    }
}
