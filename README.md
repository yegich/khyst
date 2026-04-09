# khyst (хист)

A personal plugin marketplace for coding agents. "Хист" means talent/skill in Ukrainian.

## Usage

Add this marketplace to Claude Code:

```
/plugin marketplace add yegich/khyst
```

Then browse and install plugins:

```
/plugin
```

## Adding a plugin

1. Create a plugin repo with `.claude-plugin/plugin.json`
2. Add it to `.claude-plugin/marketplace.json` in this repo
3. Push — it's instantly available via `/plugin`

## Plugin sources

Plugins can live anywhere:

```json
{"source": "github", "repo": "yegich/my-plugin"}
{"source": "npm", "package": "@yegich/my-plugin"}
{"source": "git-subdir", "url": "https://github.com/yegich/khyst", "path": "plugins/my-plugin"}
"./plugins/my-plugin"
```

## Structure

```
khyst/
├── .claude-plugin/
│   └── marketplace.json   ← plugin registry
├── plugins/               ← bundled plugins (optional)
└── README.md
```
