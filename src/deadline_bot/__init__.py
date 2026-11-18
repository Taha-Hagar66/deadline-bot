"""Discord bot: /remind, /deadlines, /done, plus automatic reminders."""
import logging
import os
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from .store import Store
from .timeparse import parse_when

log = logging.getLogger("deadline-bot")


def stamp(ts: int) -> str:
    """Discord shows this in each reader's own timezone, e.g. 'Tuesday, 25 November 2026 14:00 (in 3 days)'."""
    return f"<t:{ts}:F> (<t:{ts}:R>)"


class DeadlineBot(discord.Client):
    def __init__(self, store: Store, guild_id: int | None):
        super().__init__(intents=discord.Intents.default())
        self.store = store
        self.guild = discord.Object(guild_id) if guild_id else None
        self.tree = app_commands.CommandTree(self)
        self._add_commands()

    async def setup_hook(self) -> None:
        # Registering commands for one server shows them instantly;
        # registering globally can take a while to appear.
        if self.guild:
            self.tree.copy_global_to(guild=self.guild)
        await self.tree.sync(guild=self.guild)
        self.check_deadlines.start()

    async def on_ready(self) -> None:
        log.info("Logged in as %s", self.user)

    def _add_commands(self) -> None:
        @self.tree.command(description="Add a deadline")
        @app_commands.describe(what="What is due", when='e.g. "in 2h", "2026-11-25 14:00", "25.11.2026"')
        async def remind(interaction: discord.Interaction, what: str, when: str):
            now = datetime.now().astimezone()
            try:
                due = parse_when(when, now)
            except ValueError as e:
                await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
                return
            ts = int(due.timestamp())
            new_id = self.store.add(interaction.user.id, interaction.channel_id, what, ts, int(now.timestamp()))
            await interaction.response.send_message(f"✅ **#{new_id} {what}**, due {stamp(ts)}")

        @self.tree.command(description="List your upcoming deadlines")
        async def deadlines(interaction: discord.Interaction):
            items = self.store.upcoming(interaction.user.id)
            if not items:
                text = "🎉 No deadlines. Add one with `/remind`."
            else:
                text = "\n".join(f"**#{d.id}** {d.title}: {stamp(d.due)}" for d in items)
            await interaction.response.send_message(text, ephemeral=True)

        @self.tree.command(description="Remove a deadline you finished")
        @app_commands.describe(number="The deadline's # number from /deadlines")
        async def done(interaction: discord.Interaction, number: int):
            if self.store.remove(number, interaction.user.id):
                await interaction.response.send_message(f"✔️ Removed #{number}. Nice work!")
            else:
                await interaction.response.send_message(
                    f"I couldn't find deadline #{number} of yours.", ephemeral=True)

    @tasks.loop(seconds=30)
    async def check_deadlines(self) -> None:
        now = int(datetime.now().timestamp())
        for d in self.store.needing_warning(now):
            await self._send(d, f"⏰ <@{d.user_id}> **{d.title}** is due {stamp(d.due)}")
            self.store.mark_warned(d.id)
        for d in self.store.due_now(now):
            await self._send(d, f"🚨 <@{d.user_id}> **{d.title}** is due now!")
            self.store.delete(d.id)

    @check_deadlines.before_loop
    async def _wait_until_ready(self) -> None:
        await self.wait_until_ready()

    async def _send(self, d, text: str) -> None:
        try:
            channel = self.get_channel(d.channel_id) or await self.fetch_channel(d.channel_id)
            await channel.send(text)
        except discord.DiscordException:
            log.exception("Could not send reminder #%s", d.id)


def main() -> None:
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN is missing. Copy .env.example to .env and paste your bot token into it.")
    guild_id = os.getenv("GUILD_ID")
    bot = DeadlineBot(Store(os.getenv("DB_PATH", "deadlines.db")), int(guild_id) if guild_id else None)
    bot.run(token)
