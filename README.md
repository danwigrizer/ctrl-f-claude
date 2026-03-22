# CTRL+F+Claude

> Because "which conversation had that thing?" shouldn't be this hard.

A native Mac app that finally lets you **search, browse, and manage** everything in your Claude Code world — conversations, MCP servers, plugins, permissions — all from one place.

![Python](https://img.shields.io/badge/python-3.10+-blue) ![macOS](https://img.shields.io/badge/platform-macOS-lightgrey) ![License](https://img.shields.io/badge/license-MIT-green)

## The Problem

You've been using Claude Code for weeks. You have hundreds of conversations scattered across dozens of projects. You know you solved that exact problem before, but *where*? Which project? Which conversation? And don't even get started on figuring out which MCP servers are configured where, or what permissions you've set.

## The Solution

CTRL+F+Claude reads your local `~/.claude/` directory and gives you a clean, searchable interface for everything.

## Quick Start

```bash
git clone https://github.com/danwigrizer/ctrl-f-claude.git
cd ctrl-f-claude
pip install -r requirements.txt
python app.py
```

That's it. A native Mac window opens with all your Claude Code data.

## Install as a Real Mac App

Want it in your Applications folder with an icon and Spotlight search?

```bash
pip install py2app
./build.sh
```

Then Cmd+Space, type "CTRL+F+Claude", and you're in.

## Features & Usage

The app has three tabs: **Conversations**, **Settings & MCP**, and **Plugins**.

### Conversations Tab

This is the home screen. When you open the app, you'll see:

**Home View**
- **Bookmarked conversations** appear at the top (if you've starred any)
- **Recent conversations** from the last 15 sessions across all projects
- **Project list** in the sidebar — click any project to see its conversations

**Browsing Conversations**
- Click a project in the sidebar to see all its conversations
- Each conversation shows: first message preview (or custom name if renamed), message count, date, session ID, and working directory
- Conversations with **agent sub-conversations** show an agent badge — click to expand and see the individual agents
- Click any conversation to view the full message thread

**Conversation Actions** (buttons in the header when viewing a conversation)
- **Star icon** — bookmark/unbookmark the conversation (persists across sessions)
- **Rename** — give the conversation a custom name (same format as Claude Code's `/rename` command — the name shows up in Claude Code too)
- **Copy ID** — copy the session ID to clipboard (useful for scripting or `claude --resume`)
- **Resume in iTerm** — opens a new iTerm2 window, `cd`s to the project directory, and runs `claude --resume <session-id>`

**Search**
- **Global search** (top bar) — type to search across all conversations. Results show highlighted matching text with context. Click a result to jump into the conversation and auto-scroll to the match.
- **In-conversation search** (Cmd+F) — when viewing a conversation, press Cmd+F to open a search bar. Matches are highlighted in the messages. Use arrow buttons or Enter/Shift+Enter to navigate between matches.

**Sidebar**
- The sidebar is **resizable** — drag the border between sidebar and main panel
- **Back to projects** button takes you back to the home screen from anywhere

### Settings & MCP Tab

**Global MCP Servers**
- Shows MCP servers configured globally with their command/URL config
- **Copy Add Cmd** / **Copy Remove Cmd** buttons on each server

**MCP Servers by Project**
- Every MCP server with tags showing which projects use it
- Copy commands to replicate a server config to another project

**Global Settings**
- Model, environment variables, enabled plugins, and permissions from `~/.claude/settings.json`

**Permissions Audit**
- See all permissions across all scopes in one view:
  - Global: `~/.claude/settings.json` and `~/.claude/settings.local.json`
  - Per-project: `.claude/settings.json` (shared) and `.claude/settings.local.json` (local)
- Expandable per-project details showing allow/deny rules and which file they come from

**Per-Project Settings**
- Expand any project to see and **edit** its permissions
- The allow/deny text areas are editable — click **Save Permissions** to write changes directly to the project's `settings.local.json`

### Plugins Tab

**Installed Plugins**
- Each plugin shows: name, enabled/disabled/blocked status, marketplace, version, and scope
- **Copy Install/Enable/Disable/Uninstall** buttons generate the `/plugin` slash commands
- **View Files** — browse the plugin's file tree and click any file to view its contents
- **Skills & Agents** — expand to see all skills and agents bundled in the plugin, with full frontmatter (description, model, allowed tools, arguments) and content

**Marketplaces**
- Lists all registered marketplaces with source URL and last updated date
- **Unregistered marketplaces** (exist on disk but not in `known_marketplaces.json`) show a warning with the command to register them
- **Copy Update Cmd** / **Copy Remove Cmd** / **Copy Register Cmd** buttons
- **View Files** — browse the raw marketplace directory
- **N Available Plugins** — expand to see every plugin in the marketplace catalog, with install status and one-click **Copy Install** buttons

**Standalone Skills**
- Shows skills from `~/.claude/skills/` (user-level) and `.claude/skills/` (project-level)
- These work without plugins — just place a `SKILL.md` in the right directory

## How It Works

The app reads Claude Code's local data files — nothing is sent anywhere:

| Data | Source |
|------|--------|
| Conversations | `~/.claude/projects/*.jsonl` |
| MCP servers | `~/.claude/backups/.claude.json.backup.*` |
| Settings & permissions | `~/.claude/settings.json`, per-project `.claude/settings.local.json` |
| Plugins & marketplaces | `~/.claude/plugins/` |
| Bookmarks | `~/.claude/conversation_bookmarks.json` (created by the app) |

All data stays on your machine. Zero network calls. The only file the app *writes* is the bookmarks file and permission edits you explicitly save.

## Requirements

- macOS
- Python 3.10+
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) with some conversation history in `~/.claude/`

## Development

```bash
# Run from source (hot reload — just restart the app)
python app.py

# Rebuild the .app after changes
./build.sh
```

The app is two files:
- `api.py` — Python backend that reads `~/.claude/` data
- `index.html` — frontend UI (HTML/CSS/JS, no build tools)

## Contributing

Found a bug? Want a feature? PRs welcome.

## License

MIT
