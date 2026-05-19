import discord
from discord.ext.commands import Bot, Context, is_owner
import zoneinfo
import aiosqlite
import os


class MyBot(Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix=";",
            intents=intents,
        )

        self.db = None

    async def setup_hook(self):
        print(await bot.tree.sync())

        self.db = await aiosqlite.connect("database.db")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS birthday (
                uid INTEGER UNIQUE,
                date TEXT,
                gids TEXT,
                timezone TEXT
            );
        """)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS guildchannel (
                gid INTEGER UNIQUE,
                cid INTEGER
            );
        """)


bot = MyBot()


@bot.command(description="Sync commands.")
@is_owner()
async def sync(interaction: Context):
    await bot.tree.sync(guild=interaction.guild)
    await bot.tree.sync()


@bot.command(description="Graceful shutdown.")
@is_owner()
async def poweroff(interaction: Context):
    os._exit(0)


@bot.command(description="Test things!")
@is_owner()
async def test(interaction: Context):
    if not bot.db:
        return

    cursor = await bot.db.execute("SELECT * FROM birthday")
    await interaction.send(str(await cursor.fetchall()))


async def timezone_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[discord.app_commands.Choice[str]]:
    return [
        discord.app_commands.Choice(name=timezone, value=timezone)
        for timezone in zoneinfo.available_timezones()
        if current.lower() in timezone.lower()
    ][:25]


@discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@discord.app_commands.autocomplete(timezone=timezone_autocomplete)
@bot.tree.command(description="Register your birthday with the bot!")
async def registerme(
    interaction: discord.Interaction,
    month: int,
    day: int,
    timezone: str,
):
    if not bot.db:
        return await interaction.response.send_message(
            "Database connection failed!", ephemeral=True
        )

    if not timezone in zoneinfo.available_timezones():
        return await interaction.response.send_message(
            "Unknown timezone!", ephemeral=True
        )

    await bot.db.execute(
        "INSERT OR REPLACE INTO birthday VALUES (?, ?, ?, ?)",
        (
            interaction.user.id,
            f"{month}-{day}",
            "",
            timezone,
        ),
    )
    await bot.db.commit()

    await interaction.response.send_message("Birthday registered!", ephemeral=True)


token = ""
with open("token.txt", "r") as handle:
    token = handle.read().strip()

bot.run(token)
