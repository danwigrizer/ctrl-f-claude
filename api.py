import json
import os
import subprocess
from pathlib import Path
from datetime import datetime
from glob import glob

CLAUDE_DIR = Path.home() / ".claude" / "projects"
CLAUDE_HOME = Path.home() / ".claude"
HOME_DIR = str(Path.home())
BOOKMARKS_FILE = CLAUDE_HOME / "conversation_bookmarks.json"


def _short_name(full_path):
    """Return last 2 path segments for display."""
    parts = full_path.strip("/").split("/")
    if len(parts) <= 2:
        return full_path
    return "/".join(parts[-2:])


def _folder_to_real_path_map():
    """Build mapping from project folder names to real paths using backup file."""
    backup = _get_latest_backup()
    mapping = {}
    home = str(Path.home())
    for proj_path in backup.get("projects", {}):
        # Convert real path to the folder name format Claude uses
        folder_name = proj_path.replace("/", "-")
        if not folder_name.startswith("-"):
            folder_name = "-" + folder_name
        mapping[folder_name] = proj_path
    return mapping


def _compute_unique_names(projects):
    """Compute shortest unique display names for a list of projects."""
    home = str(Path.home())
    # Start with last 2 segments, increase until unique
    paths = [p["real_path"] for p in projects]
    result = {}
    for path in paths:
        display = path
        if display.startswith(home):
            display = "~" + display[len(home):]
        # Try progressively more segments until unique
        parts = display.strip("/").split("/")
        for n in range(2, len(parts) + 1):
            candidate = "/".join(parts[-n:])
            # Check if this is unique among all projects
            others = [p for p in paths if p != path]
            is_unique = True
            for other in others:
                other_display = other
                if other_display.startswith(home):
                    other_display = "~" + other_display[len(home):]
                other_parts = other_display.strip("/").split("/")
                if "/".join(other_parts[-n:]) == candidate:
                    is_unique = False
                    break
            if is_unique:
                result[path] = candidate
                break
        if path not in result:
            result[path] = display
    return result


def _read_first_entry(filepath):
    """Read the first valid JSON line from a JSONL file."""
    try:
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return None


def _extract_text_from_content(content):
    """Extract readable text from message content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    tool_name = block.get("name", "tool")
                    tool_input = block.get("input", {})
                    if tool_name in ("Read", "read"):
                        parts.append(f"\U0001f4c4 Read: {tool_input.get('file_path', '')}")
                    elif tool_name in ("Write", "write"):
                        parts.append(f"\u270f\ufe0f Write: {tool_input.get('file_path', '')}")
                    elif tool_name in ("Edit", "edit"):
                        parts.append(f"\U0001f527 Edit: {tool_input.get('file_path', '')}")
                    elif tool_name in ("Bash", "bash"):
                        cmd = tool_input.get("command", "")
                        parts.append(f"\U0001f4bb `{cmd[:200]}`")
                    elif tool_name in ("Grep", "grep"):
                        parts.append(f"\U0001f50d Grep: {tool_input.get('pattern', '')}")
                    elif tool_name in ("Glob", "glob"):
                        parts.append(f"\U0001f4c2 Glob: {tool_input.get('pattern', '')}")
                    else:
                        parts.append(f"\U0001f527 {tool_name}")
        return "\n\n".join(parts)
    return ""


def get_projects():
    """Return list of projects with metadata."""
    projects = []
    if not CLAUDE_DIR.exists():
        return projects

    path_map = _folder_to_real_path_map()

    raw = []
    for folder in sorted(CLAUDE_DIR.iterdir()):
        if not folder.is_dir():
            continue
        convos = list(folder.glob("*.jsonl"))
        convos = [c for c in convos if not c.stem.startswith("agent-") and c.stat().st_size > 0]
        if not convos:
            continue

        # Use real path from backup, fall back to lossy conversion
        real_path = path_map.get(folder.name, "")
        if not real_path:
            name = folder.name.replace("-", "/")
            if name.startswith("/"):
                real_path = name
            else:
                real_path = "/" + name

        latest = max(c.stat().st_mtime for c in convos)

        raw.append({
            "id": folder.name,
            "real_path": real_path,
            "conversation_count": len(convos),
            "last_active": datetime.fromtimestamp(latest).isoformat(),
        })

    # Compute unique short names
    unique_names = _compute_unique_names(raw)

    for p in raw:
        home = str(Path.home())
        full_display = p["real_path"]
        if full_display.startswith(home):
            full_display = "~" + full_display[len(home):]
        projects.append({
            "id": p["id"],
            "name": full_display,
            "short_name": unique_names.get(p["real_path"], full_display),
            "conversation_count": p["conversation_count"],
            "last_active": p["last_active"],
        })

    projects.sort(key=lambda p: p["last_active"], reverse=True)
    return projects


def get_conversations(project_id):
    """Return list of conversations for a project, with agent sub-conversations grouped."""
    project_dir = CLAUDE_DIR / project_id
    if not project_dir.exists():
        return []

    # First, map agent files to their parent session IDs
    agent_map = {}  # parent_session_id -> [agent_info, ...]
    for filepath in project_dir.glob("agent-*.jsonl"):
        entry = _read_first_entry(filepath)
        if not entry:
            continue
        parent_session = entry.get("sessionId", "")
        agent_id = entry.get("agentId", filepath.stem.replace("agent-", ""))
        cwd = entry.get("cwd", "")
        timestamp = entry.get("timestamp", "")

        # Get first meaningful message as preview (agents often start with assistant)
        preview = ""
        msg_count = 0
        first_timestamp = timestamp
        try:
            with open(filepath, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg_count += 1
                    if not first_timestamp:
                        first_timestamp = e.get("timestamp", "")
                    if e.get("type") in ("user", "assistant") and not preview:
                        msg = e.get("message", {})
                        content = msg.get("content", "")
                        text = _extract_text_from_content(content)
                        if text.strip():
                            preview = text[:120]
        except Exception:
            continue
        timestamp = first_timestamp

        if parent_session not in agent_map:
            agent_map[parent_session] = []
        agent_map[parent_session].append({
            "id": filepath.stem,
            "agent_id": agent_id,
            "preview": preview or "(agent task)",
            "message_count": msg_count,
            "timestamp": timestamp,
            "cwd": cwd,
        })

    # Now build main conversation list
    conversations = []
    for filepath in project_dir.glob("*.jsonl"):
        if filepath.stem.startswith("agent-"):
            continue

        if filepath.stat().st_size == 0:
            continue

        first_user_msg = ""
        custom_title = ""
        msg_count = 0
        timestamp = None
        last_timestamp = None
        cwd = ""
        try:
            with open(filepath, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if entry.get("type") == "custom-title":
                        custom_title = entry.get("customTitle", "")
                    entry_ts = entry.get("timestamp") or ""
                    if not timestamp:
                        timestamp = entry_ts
                    if entry_ts:
                        last_timestamp = entry_ts
                    if not cwd:
                        cwd = entry.get("cwd", "")
                    if entry.get("type") in ("user", "assistant"):
                        msg_count += 1
                        if not first_user_msg and entry.get("type") == "user":
                            msg = entry.get("message", {})
                            content = msg.get("content", "")
                            text = _extract_text_from_content(content)
                            if text.strip():
                                first_user_msg = text[:150]
        except Exception:
            continue

        session_id = filepath.stem
        agents = sorted(
            agent_map.get(session_id, []),
            key=lambda a: a["timestamp"],
        )

        preview = first_user_msg
        is_agent_only = msg_count == 0 and len(agents) > 0

        # For parent conversations with no real messages, use first agent's preview
        if not preview and agents:
            preview = agents[0]["preview"]
        if not preview:
            preview = "(empty conversation)"

        # Use first agent's timestamp/cwd if parent has none
        if not timestamp and agents:
            timestamp = agents[0].get("timestamp", "")
        if not cwd and agents:
            cwd = agents[0].get("cwd", "")

        conversations.append({
            "id": session_id,
            "preview": preview,
            "custom_title": custom_title,
            "message_count": msg_count,
            "timestamp": timestamp or "",
            "project_id": project_id,
            "cwd": cwd,
            "agents": agents,
            "is_agent_only": is_agent_only,
        })

    conversations.sort(key=lambda c: c["timestamp"], reverse=True)
    return conversations


def get_messages(project_id, conversation_id):
    """Return all messages in a conversation."""
    filepath = CLAUDE_DIR / project_id / f"{conversation_id}.jsonl"
    if not filepath.exists():
        return []

    messages = []
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = entry.get("type", "")
            if msg_type not in ("user", "assistant"):
                continue

            msg = entry.get("message", {})
            content = msg.get("content", "")
            text = _extract_text_from_content(content)

            if not text.strip():
                continue

            messages.append({
                "role": msg_type,
                "text": text,
                "timestamp": entry.get("timestamp", ""),
                "model": msg.get("model", ""),
            })

    return messages


def search_conversations(query):
    """Search across all conversations with context snippets."""
    query_lower = query.lower()
    results = []

    if not CLAUDE_DIR.exists():
        return results

    path_map = _folder_to_real_path_map()

    for folder in CLAUDE_DIR.iterdir():
        if not folder.is_dir():
            continue
        for filepath in folder.glob("*.jsonl"):
            if filepath.stem.startswith("agent-"):
                continue
            try:
                cwd = ""
                with open(filepath, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not cwd:
                            cwd = entry.get("cwd", "")
                        if entry.get("type") not in ("user", "assistant"):
                            continue
                        msg = entry.get("message", {})
                        content = msg.get("content", "")
                        if isinstance(content, str):
                            text = content
                        elif isinstance(content, list):
                            text = " ".join(
                                b.get("text", "") if isinstance(b, dict) else str(b)
                                for b in content
                            )
                        else:
                            text = ""

                        idx = text.lower().find(query_lower)
                        if idx >= 0:
                            name = folder.name.replace("-", "/")
                            if name.startswith("/"):
                                name = name[1:]

                            # Build context snippet around match
                            start = max(0, idx - 50)
                            end = min(len(text), idx + len(query) + 100)
                            snippet = text[start:end]
                            match_start = idx - start
                            match_len = len(query)

                            # Resolve cwd: prefer conversation cwd, fall back to project real path
                            resolved_cwd = cwd or path_map.get(folder.name, "")

                            results.append({
                                "project_id": folder.name,
                                "project_name": name,
                                "short_name": _short_name(name),
                                "conversation_id": filepath.stem,
                                "role": entry.get("type"),
                                "snippet": snippet,
                                "match_start": match_start,
                                "match_len": match_len,
                                "timestamp": entry.get("timestamp", ""),
                                "cwd": resolved_cwd,
                            })
                            break
            except Exception:
                continue

    results.sort(key=lambda r: r["timestamp"], reverse=True)
    return results[:50]


def _get_latest_backup():
    """Read the most recent Claude backup file for MCP/settings data."""
    backup_dir = CLAUDE_HOME / "backups"
    if not backup_dir.exists():
        return {}
    backups = sorted(backup_dir.glob(".claude.json.backup.*"))
    if not backups:
        return {}
    try:
        with open(backups[-1], "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _read_json_file(path):
    """Read a JSON file, return empty dict on failure."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _get_marketplace_plugins(install_location):
    """Read the plugin catalog from a marketplace directory."""
    if not install_location:
        return []
    base = Path(install_location)
    for loc in [base / ".claude-plugin" / "marketplace.json", base / "marketplace.json"]:
        if loc.exists():
            data = _read_json_file(loc)
            raw = data.get("plugins", {})
            result = []
            if isinstance(raw, dict):
                for name, entry in raw.items():
                    if isinstance(entry, dict):
                        result.append({
                            "name": entry.get("name", name),
                            "description": entry.get("description", ""),
                            "version": entry.get("version", ""),
                            "category": entry.get("category", ""),
                        })
                    else:
                        result.append({"name": name, "description": "", "version": "", "category": ""})
            elif isinstance(raw, list):
                for entry in raw:
                    if isinstance(entry, dict):
                        result.append({
                            "name": entry.get("name", "?"),
                            "description": entry.get("description", ""),
                            "version": entry.get("version", ""),
                            "category": entry.get("category", ""),
                        })
            return result
    return []


def get_settings():
    """Return MCP servers, permissions, and settings across all scopes."""
    # Global settings files
    global_settings = _read_json_file(CLAUDE_HOME / "settings.json")
    global_local = _read_json_file(CLAUDE_HOME / "settings.local.json")

    # Backup file has MCP server definitions and per-project config
    backup = _get_latest_backup()

    # Global MCP servers (defined at top level of backup)
    global_mcp = {}
    for name, cfg in backup.get("mcpServers", {}).items():
        global_mcp[name] = {
            "command": cfg.get("command", ""),
            "args": cfg.get("args", []),
            "type": cfg.get("type", "stdio"),
            "url": cfg.get("url", ""),
            "env": cfg.get("env", {}),
            "env_keys": list(cfg.get("env", {}).keys()),
            "always_allow": cfg.get("alwaysAllow", []),
            "scope": "global",
        }

    # Per-project data
    projects = []
    all_mcp_names = set(global_mcp.keys())

    for proj_path, proj_data in backup.get("projects", {}).items():
        mcp_servers = {}
        raw_servers = proj_data.get("mcpServers", {})

        if isinstance(raw_servers, dict):
            for name, cfg in raw_servers.items():
                if isinstance(cfg, dict):
                    mcp_servers[name] = {
                        "command": cfg.get("command", ""),
                        "args": cfg.get("args", []),
                        "type": cfg.get("type", "stdio"),
                        "url": cfg.get("url", ""),
                        "env": cfg.get("env", {}),
                        "env_keys": list(cfg.get("env", {}).keys()),
                        "always_allow": cfg.get("alwaysAllow", []),
                        "scope": "project",
                    }
                    all_mcp_names.add(name)
        elif isinstance(raw_servers, list):
            for name in raw_servers:
                mcp_servers[name] = {"scope": "project (ref)"}
                all_mcp_names.add(name)

        # Read project-level settings.local.json for permissions
        proj_settings_path = Path(proj_path) / ".claude" / "settings.local.json"
        proj_settings = _read_json_file(proj_settings_path)

        projects.append({
            "path": proj_path,
            "short_name": _short_name(proj_path),
            "mcp_servers": mcp_servers,
            "mcp_server_names": list(mcp_servers.keys()),
            "permissions": proj_settings.get("permissions", {}),
            "enabled_mcp_json": proj_data.get("enabledMcpjsonServers", []),
            "disabled_mcp_json": proj_data.get("disabledMcpjsonServers", []),
            "disabled_mcp_servers": proj_data.get("disabledMcpServers", []),
            "enable_all_project_mcp": proj_data.get("enableAllProjectMcpServers", None),
        })

    # Sort projects by path
    projects.sort(key=lambda p: p["path"])

    return {
        "global_settings": {
            "model": global_settings.get("model", ""),
            "env": global_settings.get("env", {}),
            "permissions": global_settings.get("permissions", {}),
            "local_permissions": global_local.get("permissions", {}),
            "plugins": global_settings.get("enabledPlugins", {}),
            "always_thinking": global_settings.get("alwaysThinkingEnabled", False),
        },
        "global_mcp": global_mcp,
        "projects": projects,
        "all_mcp_names": sorted(all_mcp_names),
    }


class Api:
    """PyWebView JS-accessible API."""

    def get_projects(self):
        return get_projects()

    def get_conversations(self, project_id):
        return get_conversations(project_id)

    def get_messages(self, project_id, conversation_id):
        return get_messages(project_id, conversation_id)

    def search(self, query):
        return search_conversations(query)

    def get_settings(self):
        return get_settings()

    def generate_add_command(self, server_name, server_cfg, scope="local"):
        """Generate a `claude mcp add` CLI command for a server."""
        cfg = server_cfg
        transport = cfg.get("type", "stdio")
        if transport == "http" or cfg.get("url", ""):
            transport = "http"
        parts = ["claude mcp add"]
        parts.append(f"--transport {transport}")
        if scope != "local":
            parts.append(f"--scope {scope}")
        env = cfg.get("env", {})
        for k, v in env.items():
            parts.append(f"--env {k}={v}")
        parts.append(server_name)
        if transport in ("http", "sse"):
            parts.append(cfg.get("url", ""))
        else:
            cmd = cfg.get("command", "")
            args = cfg.get("args", [])
            parts.append("--")
            parts.append(cmd)
            parts.extend(args)
        return " ".join(parts)

    def generate_remove_command(self, server_name):
        """Generate a `claude mcp remove` CLI command."""
        return f"claude mcp remove {server_name}"

    def save_project_permissions(self, project_path, allow_list, deny_list):
        """Save permissions to a project's settings.local.json."""
        settings_path = Path(project_path) / ".claude" / "settings.local.json"
        settings = _read_json_file(settings_path)
        if "permissions" not in settings:
            settings["permissions"] = {}
        settings["permissions"]["allow"] = allow_list
        settings["permissions"]["deny"] = deny_list
        # Ensure directory exists
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=2)
        return {"ok": True, "path": str(settings_path)}

    def get_project_permissions(self, project_path):
        """Read a project's settings.local.json permissions."""
        settings_path = Path(project_path) / ".claude" / "settings.local.json"
        settings = _read_json_file(settings_path)
        return {
            "allow": settings.get("permissions", {}).get("allow", []),
            "deny": settings.get("permissions", {}).get("deny", []),
            "path": str(settings_path),
        }

    def open_in_iterm(self, session_id, cwd, project_id=None):
        """Open a conversation in iTerm2 with claude --resume."""
        # Resolve cwd: use provided cwd, fall back to project real path
        if not cwd and project_id:
            path_map = _folder_to_real_path_map()
            cwd = path_map.get(project_id, "")
        cwd = cwd or str(Path.home())
        script = f'''
        tell application "iTerm"
            activate
            create window with default profile
            tell current session of current window
                write text "cd {cwd} && claude --resume {session_id}"
            end tell
        end tell
        '''
        subprocess.Popen(["osascript", "-e", script])

    def get_plugins(self):
        """Return installed plugins, marketplaces, and blocklist."""
        plugins_dir = CLAUDE_HOME / "plugins"

        # Installed plugins — format: {version: 2, plugins: {"name@mkt": [...]}}
        raw = _read_json_file(plugins_dir / "installed_plugins.json")
        plugins_map = raw.get("plugins", {}) if isinstance(raw, dict) else {}
        installed_list = []
        for full_name, entries in plugins_map.items():
            parts = full_name.split("@", 1)
            name = parts[0]
            marketplace = parts[1] if len(parts) > 1 else "?"
            entry = entries[0] if isinstance(entries, list) and entries else {}
            install_path = entry.get("installPath", "")
            # If recorded path doesn't exist, try to find actual versioned dir
            if install_path and not Path(install_path).exists():
                parent = Path(install_path).parent
                if parent.exists():
                    subdirs = sorted(parent.iterdir())
                    if subdirs:
                        install_path = str(subdirs[-1])  # Use latest version

            installed_list.append({
                "full_name": full_name,
                "name": name,
                "marketplace": marketplace,
                "scope": entry.get("scope", "?"),
                "version": entry.get("version", "?"),
                "install_path": install_path,
                "installed_at": entry.get("installedAt", ""),
                "last_updated": entry.get("lastUpdated", ""),
            })

        # Scan for local plugins (dirs with .claude-plugin/plugin.json)
        for item in plugins_dir.iterdir():
            if not item.is_dir():
                continue
            if item.name in ("cache", "marketplaces", "data"):
                continue
            manifest = item / ".claude-plugin" / "plugin.json"
            if manifest.exists():
                pdata = _read_json_file(manifest)
                pname = pdata.get("name", item.name)
                full_name = f"{pname}@local"
                # Check if already in installed list
                if not any(p["full_name"] == full_name for p in installed_list):
                    installed_list.append({
                        "full_name": full_name,
                        "name": pname,
                        "marketplace": "local",
                        "scope": "user",
                        "version": pdata.get("version", "local"),
                        "install_path": str(item),
                        "installed_at": "",
                        "last_updated": "",
                    })

        # Enabled plugins from settings
        global_settings = _read_json_file(CLAUDE_HOME / "settings.json")
        enabled_plugins = global_settings.get("enabledPlugins", {})

        # Marketplaces — format: {"name": {source: {}, installLocation: "", lastUpdated: ""}}
        raw_mkts = _read_json_file(plugins_dir / "known_marketplaces.json")
        registered_names = set()
        marketplaces = []
        if isinstance(raw_mkts, dict):
            for mkt_name, mkt_data in raw_mkts.items():
                registered_names.add(mkt_name)
                src = mkt_data.get("source", {})
                install_loc = mkt_data.get("installLocation", "")
                marketplaces.append({
                    "name": mkt_name,
                    "source_type": src.get("source", "?"),
                    "url": src.get("url", src.get("repo", "")),
                    "install_location": install_loc,
                    "last_updated": mkt_data.get("lastUpdated", ""),
                    "registered": True,
                    "available_plugins": _get_marketplace_plugins(install_loc),
                })

        # Scan for unregistered marketplaces
        mkts_dir = plugins_dir / "marketplaces"
        if mkts_dir.exists():
            for item in mkts_dir.iterdir():
                if item.is_dir() and item.name not in registered_names:
                    marketplaces.append({
                        "name": item.name,
                        "source_type": "local",
                        "url": str(item),
                        "install_location": str(item),
                        "last_updated": "",
                        "registered": False,
                        "available_plugins": _get_marketplace_plugins(str(item)),
                    })

        # Blocklist
        blocklist = _read_json_file(plugins_dir / "blocklist.json")
        if isinstance(blocklist, dict):
            blocklist = blocklist.get("blocked", [])
        if not isinstance(blocklist, list):
            blocklist = []

        return {
            "installed": installed_list,
            "enabled": enabled_plugins,
            "marketplaces": marketplaces,
            "blocklist": blocklist,
        }

    def get_plugin_files(self, plugin_path):
        """Return the file tree and contents of key files for a plugin."""
        base = Path(plugin_path)
        if not base.exists():
            return {"error": "Plugin path not found", "path": plugin_path}

        files = []
        key_files = {}

        for root, dirs, filenames in os.walk(base):
            # Skip node_modules, .git, etc.
            dirs[:] = [d for d in dirs if d not in (
                "node_modules", ".git", "__pycache__", "dist", "build"
            )]
            for fname in sorted(filenames):
                full = Path(root) / fname
                rel = str(full.relative_to(base))
                size = full.stat().st_size
                files.append({"path": rel, "size": size})

                # Auto-read key plugin files
                if fname in ("plugin.json", "marketplace.json", ".mcp.json",
                             ".lsp.json", "hooks.json", "SKILL.md",
                             "README.md", "SETUP.md"):
                    try:
                        key_files[rel] = full.read_text(errors="replace")[:5000]
                    except Exception:
                        pass
                elif fname.endswith(".md") and size < 10000:
                    try:
                        key_files[rel] = full.read_text(errors="replace")[:5000]
                    except Exception:
                        pass

        return {"files": files, "key_files": key_files, "path": plugin_path}

    def get_plugin_skills_and_agents(self, install_path):
        """Read skills and agents from a plugin directory."""
        base = Path(install_path)
        result = {"skills": [], "agents": []}

        # Read skills
        skills_dir = base / "skills"
        if skills_dir.exists():
            for item in sorted(skills_dir.iterdir()):
                if not item.is_dir():
                    continue
                skill_md = item / "SKILL.md"
                skill = {"name": item.name, "description": "", "frontmatter": {}, "content": ""}
                if skill_md.exists():
                    try:
                        text = skill_md.read_text(errors="replace")
                        # Parse frontmatter
                        if text.startswith("---"):
                            end = text.find("---", 3)
                            if end > 0:
                                fm_text = text[3:end].strip()
                                for line in fm_text.split("\n"):
                                    if ":" in line:
                                        k, v = line.split(":", 1)
                                        skill["frontmatter"][k.strip()] = v.strip()
                                skill["description"] = skill["frontmatter"].get("description", "")
                                skill["content"] = text[end+3:].strip()[:2000]
                            else:
                                skill["content"] = text[:2000]
                        else:
                            skill["content"] = text[:2000]
                    except Exception:
                        pass
                # List supporting files
                supporting = []
                for root, dirs, files in os.walk(item):
                    dirs[:] = [d for d in dirs if d not in ("node_modules", ".git")]
                    for f in files:
                        if f != "SKILL.md":
                            supporting.append(str(Path(root, f).relative_to(item)))
                skill["supporting_files"] = supporting
                result["skills"].append(skill)

        # Read agents
        agents_dir = base / "agents"
        if agents_dir.exists():
            for item in sorted(agents_dir.iterdir()):
                if not item.is_file() or not item.name.endswith(".md"):
                    continue
                agent = {"name": item.stem, "description": "", "frontmatter": {}, "content": ""}
                try:
                    text = item.read_text(errors="replace")
                    if text.startswith("---"):
                        end = text.find("---", 3)
                        if end > 0:
                            fm_text = text[3:end].strip()
                            for line in fm_text.split("\n"):
                                if ":" in line:
                                    k, v = line.split(":", 1)
                                    agent["frontmatter"][k.strip()] = v.strip()
                            agent["description"] = agent["frontmatter"].get("description", "")
                            agent["content"] = text[end+3:].strip()[:2000]
                        else:
                            agent["content"] = text[:2000]
                    else:
                        agent["content"] = text[:2000]
                except Exception:
                    pass
                result["agents"].append(agent)

        return result

    def get_standalone_skills(self):
        """Read standalone skills from ~/.claude/skills/ and .claude/skills/."""
        results = []
        for scope, base in [("user", CLAUDE_HOME / "skills"), ("project", Path.cwd() / ".claude" / "skills")]:
            if not base.exists():
                continue
            for item in sorted(base.iterdir()):
                if not item.is_dir():
                    continue
                skill_md = item / "SKILL.md"
                skill = {"name": item.name, "scope": scope, "path": str(item), "description": "", "frontmatter": {}}
                if skill_md.exists():
                    try:
                        text = skill_md.read_text(errors="replace")
                        if text.startswith("---"):
                            end = text.find("---", 3)
                            if end > 0:
                                fm_text = text[3:end].strip()
                                for line in fm_text.split("\n"):
                                    if ":" in line:
                                        k, v = line.split(":", 1)
                                        skill["frontmatter"][k.strip()] = v.strip()
                                skill["description"] = skill["frontmatter"].get("description", "")
                    except Exception:
                        pass
                results.append(skill)
        return results

    def read_plugin_file(self, file_path):
        """Read a specific file from a plugin."""
        try:
            p = Path(file_path)
            if not p.exists():
                return {"error": "File not found"}
            content = p.read_text(errors="replace")
            return {"content": content[:50000], "path": file_path}
        except Exception as e:
            return {"error": str(e)}

    def rename_conversation(self, project_id, conversation_id, new_title):
        """Rename a conversation by writing a custom-title entry to the JSONL file."""
        filepath = CLAUDE_DIR / project_id / f"{conversation_id}.jsonl"
        if not filepath.exists():
            return {"error": "Conversation not found"}
        # Remove any existing custom-title entry, then append the new one
        lines = []
        with open(filepath, "r") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    entry = json.loads(stripped)
                    if entry.get("type") == "custom-title":
                        continue  # skip old title
                except json.JSONDecodeError:
                    pass
                lines.append(stripped)
        # Append new title
        title_entry = json.dumps({
            "type": "custom-title",
            "customTitle": new_title,
            "sessionId": conversation_id,
        })
        lines.append(title_entry)
        with open(filepath, "w") as f:
            f.write("\n".join(lines) + "\n")
        return {"ok": True, "title": new_title}

    def get_home_dir(self):
        """Return the home directory path for dynamic ~ replacement."""
        return HOME_DIR

    def get_recent_conversations(self, limit=15):
        """Return most recent conversations across all projects."""
        if not CLAUDE_DIR.exists():
            return []
        path_map = _folder_to_real_path_map()
        all_convos = []
        for folder in CLAUDE_DIR.iterdir():
            if not folder.is_dir():
                continue
            real_path = path_map.get(folder.name, folder.name.replace("-", "/"))
            if real_path.startswith("-"):
                real_path = real_path[1:]
            short = _short_name(real_path)
            for filepath in folder.glob("*.jsonl"):
                if filepath.stem.startswith("agent-"):
                    continue
                if filepath.stat().st_size == 0:
                    continue
                preview = ""
                custom_title = ""
                timestamp = ""
                cwd = ""
                try:
                    with open(filepath, "r") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                entry = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            if entry.get("type") == "custom-title":
                                custom_title = entry.get("customTitle", "")
                            if not timestamp:
                                timestamp = entry.get("timestamp") or ""
                            if not cwd:
                                cwd = entry.get("cwd", "")
                            if entry.get("type") == "user" and not preview:
                                msg = entry.get("message", {})
                                content = msg.get("content", "")
                                text = _extract_text_from_content(content)
                                if text.strip():
                                    preview = text[:120]
                except Exception:
                    continue
                all_convos.append({
                    "id": filepath.stem,
                    "project_id": folder.name,
                    "project_name": short,
                    "preview": preview or "(empty)",
                    "custom_title": custom_title,
                    "timestamp": timestamp,
                    "cwd": cwd,
                })
        all_convos.sort(key=lambda c: c["timestamp"], reverse=True)
        return all_convos[:limit]

    def get_bookmarks(self):
        """Read bookmarked conversations."""
        return _read_json_file(BOOKMARKS_FILE)

    def toggle_bookmark(self, project_id, conversation_id, label):
        """Add or remove a bookmark."""
        bookmarks = _read_json_file(BOOKMARKS_FILE)
        if not isinstance(bookmarks, dict):
            bookmarks = {}
        key = f"{project_id}/{conversation_id}"
        if key in bookmarks:
            del bookmarks[key]
            action = "removed"
        else:
            bookmarks[key] = {
                "project_id": project_id,
                "conversation_id": conversation_id,
                "label": label,
                "added": datetime.now().isoformat(),
            }
            action = "added"
        with open(BOOKMARKS_FILE, "w") as f:
            json.dump(bookmarks, f, indent=2)
        return {"action": action, "bookmarks": bookmarks}

    def get_permissions_audit(self):
        """Return permissions from all scopes for audit comparison."""
        global_settings = _read_json_file(CLAUDE_HOME / "settings.json")
        global_local = _read_json_file(CLAUDE_HOME / "settings.local.json")
        backup = _get_latest_backup()

        projects = []
        for proj_path in backup.get("projects", {}):
            proj_settings = _read_json_file(Path(proj_path) / ".claude" / "settings.local.json")
            proj_shared = _read_json_file(Path(proj_path) / ".claude" / "settings.json")
            perms_local = proj_settings.get("permissions", {})
            perms_shared = proj_shared.get("permissions", {})
            if not perms_local and not perms_shared:
                continue
            projects.append({
                "path": proj_path,
                "short_name": _short_name(proj_path),
                "local_permissions": perms_local,
                "shared_permissions": perms_shared,
            })
        projects.sort(key=lambda p: p["path"])

        return {
            "global": {
                "settings_json": global_settings.get("permissions", {}),
                "settings_local_json": global_local.get("permissions", {}),
            },
            "projects": projects,
        }
