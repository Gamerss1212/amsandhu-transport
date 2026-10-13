# Backup and restore (1.4.1 → 1.5.0)

Version 1.5.0 replaces the 320-agent fleet with 100 trading agents run by one master agent. Before that change, the
previous system was preserved in three ways. Any one of them gets you back to 1.4.1.

## 1. The previous program (Windows download)

`downloads/TradingAI-v1.4.1-windows.zip` stays in the repository, unchanged.

- SHA-256: `aa7aaac08132ca576c839d003f05695654fa4a4e9e9f13be33cf43486ded2bc3`
- To use it: unzip it into its own folder and double-click `START_TRADING_AI.exe`, exactly as before.
- It keeps its own data folder next to the program, so it does not touch a 1.5.0 installation.

## 2. The previous source code (git)

The last 1.4.1 commit is `a3c3952` on the branch `claude/amazing-tesla-1i8gj8`. It also has the local tag
`backup-1.4.1-320-agents` in the session that made the change.

To look at it or build it again:

```
git checkout a3c3952          # or: git checkout backup-1.4.1-320-agents
```

To go back to the newest version afterwards:

```
git checkout claude/amazing-tesla-1i8gj8
```

## 3. Your data (automatic, on first start of 1.5.0)

1.5.0 adds four tables (agent versions, lessons, mistakes, regression runs). When it finds an older database, it copies
the whole database before changing anything:

```
<data folder>/data/backups/pre-upgrade-schema4-<date>-<time>.sqlite3
```

- The start-up check "database open and migrated" names the file it wrote.
- The copy holds the paper account, positions, orders, fills, decisions, research ledger and audit log exactly as 1.4.1
  left them.

To restore it:

1. Close the program.
2. Put the 1.4.1 program back (section 1).
3. Replace `<data folder>/data/app.sqlite3` with the backup file, renamed to `app.sqlite3`.

## What 1.5.0 does with the old bots

- The 320 agents and their bots are not converted. The master removes each old bot once it holds no position.
- A bot that still holds a position is kept until that position is closed. Its exits keep working, and it can never open
  a new position: only an instrument's owning agent may open one.
- Nothing is sold to make room for the new agents.
