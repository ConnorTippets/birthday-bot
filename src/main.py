import discord
from discord.ext.commands import Bot, Context, is_owner
import aiosqlite


class MyBot(Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix=";",
            intents=intents,
        )

        self.bot = None

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


@discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@bot.tree.command(description="Register your (or someone elses) birthday with the bot!")
async def register(
    interaction: discord.Interaction, user: discord.User | discord.Member | None = None
): ...


token = ""
with open("token.txt", "r") as handle:
    token = handle.read().strip()

bot.run(token)
