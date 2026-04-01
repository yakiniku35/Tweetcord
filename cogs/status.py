import asyncio
import os
from datetime import datetime, timezone

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from configs.load_configs import configs
from core.classes import Cog_Extension
from src.log import setup_logger
from src.utils import get_accounts

log = setup_logger(__name__)

_start_time = datetime.now(timezone.utc)


class Status(Cog_Extension):

    @app_commands.command(name='status')
    async def status(self, itn: discord.Interaction):
        """Query the bot's current running status."""

        await itn.response.defer(ephemeral=True)

        # --- Uptime ---
        now = datetime.now(timezone.utc)
        delta = now - _start_time
        total_seconds = int(delta.total_seconds())
        days, rem = divmod(total_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"

        # --- Tracked users / active notification tasks ---
        notification_cog = self.bot.cogs.get('Notification')
        tracked_users = 0
        active_notification_tasks = 0
        if notification_cog and hasattr(notification_cog, 'account_tracker'):
            tracker = notification_cog.account_tracker
            tracked_users = len(tracker.latest_tweet_timestamps)
            tracked_usernames = {username for username, _ in tracker.latest_tweet_timestamps}
            running_task_names = {task.get_name() for task in asyncio.all_tasks()}
            active_notification_tasks = len(tracked_usernames & running_task_names)

        # --- Twitter accounts configured ---
        num_accounts = len(get_accounts())

        # --- DB connectivity ---
        db_path = os.path.join(os.getenv('DATA_PATH'), 'tracked_accounts.db')
        db_ok = False
        try:
            async with aiosqlite.connect(db_path, timeout=3) as db:
                await db.execute('SELECT 1')
            db_ok = True
        except Exception as e:
            log.warning(f"status command: DB check failed: {e}")

        # --- Embed mode ---
        embed_mode = configs['embed']['type']

        embed = discord.Embed(title='🤖 Bot Status', color=0x1da0f2, timestamp=now)
        embed.add_field(name='⏱ Uptime', value=uptime_str, inline=False)
        embed.add_field(name='👥 Tracked Users', value=str(tracked_users), inline=True)
        embed.add_field(name='🔔 Active Tasks', value=str(active_notification_tasks), inline=True)
        embed.add_field(name='🐦 Twitter Accounts', value=str(num_accounts), inline=True)
        embed.add_field(name='🗄 Database', value='✅ OK' if db_ok else '❌ Error', inline=True)
        embed.add_field(name='🖼 Embed Mode', value=embed_mode, inline=True)

        await itn.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Status(bot))
