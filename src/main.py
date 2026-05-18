import discord
from discord.ext.commands import Bot, Context, is_owner


class MyBot(Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix=";",
            intents=intents,
        )

    async def setup_hook(self):
        print(await bot.tree.sync())


bot = MyBot()


@bot.command(description="Sync commands.")
@is_owner()
async def sync(interaction: Context):
    await bot.tree.sync(guild=interaction.guild)
    await bot.tree.sync()


token = ""
with open("token.txt", "r") as handle:
    token = handle.read().strip()

bot.run(token)
