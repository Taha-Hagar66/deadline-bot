# Deadline Bot ⏰

A Discord bot that keeps track of your deadlines and pings you before they're due.

## Commands

| Command | What it does |
|---|---|
| `/remind what when` | Add a deadline. `when` can be `in 2h`, `in 3d 4h`, `2026-11-25 14:00` or `25.11.2026` |
| `/deadlines` | List your upcoming deadlines (only you can see the list) |
| `/done number` | Remove a deadline you've finished |

The bot posts a reminder **24 hours before** each deadline and again **when it's due**. Times show in each person's own timezone.

## Run it yourself

Requires [uv](https://docs.astral.sh/uv/).

1. Create a bot at the [Discord Developer Portal](https://discord.com/developers/applications) and copy its token.
2. Copy `.env.example` to `.env` and paste the token in.
3. Start it:
   ```bash
   uv run deadline-bot
   ```

## Tests

```bash
uv run pytest
```

## Tech

Python 3.13 · [discord.py](https://discordpy.readthedocs.io/) · SQLite · pytest · uv
