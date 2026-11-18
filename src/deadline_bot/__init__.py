"""Discord bot: /remind, /deadlines, /done, /timezone, plus automatic reminders."""
import logging
import os
from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from .store import Store
from .timeparse import parse_when

log = logging.getLogger("deadline-bot")

MAX_TITLE = 100
MAX_MESSAGE = 1900  # Discord's hard limit is 2000 characters; leave some room
ALL_TIMEZONES = sorted(available_timezones())


def stamp(ts: int) -> str:
    """Discord shows this in each reader's own timezone, e.g. 'Tuesday, 25 November 2026 14:00 (in 3 days)'."""
    return f"<t:{ts}:F> (<t:{ts}:R>)"


def fit_lines(lines: list[str], limit: int = MAX_MESSAGE) -> str:
    """Join lines, stopping before the message gets too long for Discord."""
    out, size = [], 0
    for i, line in enumerate(lines):
        if size + len(line) + 1 > limit - 30:  # keep room for the "...and N more" note
            out.append(f"…and {len(lines) - i} more.")
            break
        out.append(line)
        size += len(line) + 1
    return "\n".join(out)


class DeadlineBot(discord.Client):
    def __init__(self, store: Store, guild_id: int | None, default_tz: tzinfo):
        # By default the bot pings nobody, so a title like "@everyone" stays plain text.
        # Reminders explicitly allow pinging only the deadline's owner (see _deliver).
        super().__init__(intents=discord.Intents.default(),
                         allowed_mentions=discord.AllowedMentions.none())
        self.store = store
        self.default_tz = default_tz
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

    def user_tz(self, user_id: int) -> tzinfo | None:
        name = self.store.get_timezone(user_id)
        return ZoneInfo(name) if name else None

    def _add_commands(self) -> None:
        @self.tree.command(description="Add a deadline")
        @app_commands.describe(what="What is due", when='e.g. "in 2h", "2026-11-25 14:00", "25.11.2026"')
        async def remind(interaction: discord.Interaction,
                         what: app_commands.Range[str, 1, MAX_TITLE], when: str):
            tz = self.user_tz(interaction.user.id)
            now = datetime.now(tz or self.default_tz)
            try:
                due = parse_when(when, now)
            except ValueError as e:
                await interaction.response.send_message(f"⚠️ {e}", ephemeral=True)
                return
            ts = int(due.timestamp())
            new_id = self.store.add(interaction.user.id, interaction.channel_id, what, ts, int(now.timestamp()))
            await interaction.response.send_message(f"✅ **#{new_id} {what}**, due {stamp(ts)}")
            typed_a_date = not when.strip().lower().startswith("in ")
            if tz is None and typed_a_date:
                await interaction.followup.send(
                    f"ℹ️ I read that time as **{now.tzname()}**. If that's wrong, set yours with "
                    "`/timezone` and add the deadline again.", ephemeral=True)

        @self.tree.command(description="List your upcoming deadlines")
        async def deadlines(interaction: discord.Interaction):
            items = self.store.upcoming(interaction.user.id)
            if not items:
                text = "🎉 No deadlines. Add one with `/remind`."
            else:
                text = fit_lines([f"**#{d.id}** {d.title}: {stamp(d.due)}" for d in items])
            await interaction.response.send_message(text, ephemeral=True)

        @self.tree.command(description="Remove a deadline you finished")
        @app_commands.describe(number="The deadline's # number from /deadlines")
        async def done(interaction: discord.Interaction, number: int):
            if self.store.remove(number, interaction.user.id):
                await interaction.response.send_message(f"✔️ Removed #{number}. Nice work!")
            else:
                await interaction.response.send_message(
                    f"I couldn't find deadline #{number} of yours.", ephemeral=True)

        @self.tree.command(description="Set your time zone, so typed dates mean your local time")
        @app_commands.describe(name='Start typing your city, e.g. "Vienna" or "New_York"')
        async def timezone(interaction: discord.Interaction, name: str):
            try:
                ZoneInfo(name)
            except (ZoneInfoNotFoundError, ValueError):
                await interaction.response.send_message(
                    f"⚠️ I don't know the time zone '{name}'. Pick one from the list while typing.",
                    ephemeral=True)
                return
            self.store.set_timezone(interaction.user.id, name)
            local = datetime.now(ZoneInfo(name)).strftime("%H:%M")
            await interaction.response.send_message(
                f"🌍 Time zone set to **{name}** (it's {local} there now).", ephemeral=True)

        @timezone.autocomplete("name")
        async def timezone_suggestions(interaction: discord.Interaction, current: str):
            needle = current.lower().replace(" ", "_")
            matches = [z for z in ALL_TIMEZONES if needle in z.lower()]
            return [app_commands.Choice(name=z, value=z) for z in matches[:25]]

    @tasks.loop(seconds=30)
    async def check_deadlines(self) -> None:
        now = int(datetime.now().timestamp())
        for d in self.store.needing_warning(now):
            await self._deliver(d, f"⏰ <@{d.user_id}> **{d.title}** is due {stamp(d.due)}")
            self.store.mark_warned(d.id)
        for d in self.store.due_now(now):
            await self._deliver(d, f"🚨 <@{d.user_id}> **{d.title}** is due now!")
            self.store.delete(d.id)

    @check_deadlines.before_loop
    async def _wait_until_ready(self) -> None:
        await self.wait_until_ready()

    async def _deliver(self, d, text: str) -> None:
        """Post in the original channel; if that fails, DM the owner instead."""
        only_owner = discord.AllowedMentions(users=[discord.Object(d.user_id)])
        try:
            channel = self.get_channel(d.channel_id) or await self.fetch_channel(d.channel_id)
            await channel.send(text, allowed_mentions=only_owner)
            return
        except discord.DiscordException:
            log.warning("Could not post reminder #%s in its channel, trying a DM", d.id)
        try:
            user = self.get_user(d.user_id) or await self.fetch_user(d.user_id)
            await user.send(text, allowed_mentions=only_owner)
        except discord.DiscordException:
            log.exception("Could not deliver reminder #%s at all", d.id)


def main() -> None:
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN is missing. Copy .env.example to .env and paste your bot token into it.")
    guild_id = os.getenv("GUILD_ID")
    tz_name = os.getenv("DEFAULT_TIMEZONE")
    default_tz = ZoneInfo(tz_name) if tz_name else datetime.now().astimezone().tzinfo
    bot = DeadlineBot(Store(os.getenv("DB_PATH", "deadlines.db")),
                      int(guild_id) if guild_id else None, default_tz)
    bot.run(token)
