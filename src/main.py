import discord
from discord.ext.commands import Bot, Context, is_owner
from discord import ui
import zoneinfo
import aiosqlite
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler

DAY_SUFFIXES = (
    ["st", "nd", "rd"]
    + (
        [
            "th",
        ]
        * 17
    )
    + ["st", "nd", "rd"]
    + (
        [
            "th",
        ]
        * 17
    )
    + [
        "st",
    ]
)

MONTHS = [
    "January",
    "Feburary",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


class MyBot(Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(
            command_prefix=";",
            intents=intents,
        )

        self.db = None
        self.scheduler = None
        self.jobs = {}
        self.allowed_mentions = discord.AllowedMentions.all()

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
            CREATE TABLE IF NOT EXISTS guild (
                gid INTEGER UNIQUE,
                cid INTEGER,
                message TEXT,
                icon TEXT,
                enabled BOOLEAN
            );
        """)

        self.scheduler = AsyncIOScheduler(event_loop=self.loop)

        cursor = await self.db.execute("SELECT * FROM birthday")
        async for row in cursor:
            if not row[1] or not row[2]:
                continue

            month_raw, _, day_raw = row[1].partition("-")
            month, day = int(month_raw), int(day_raw)

            timezone = row[3]

            self.jobs[row[0]] = self.scheduler.add_job(
                send_birthday_message,
                "cron",
                args=(row,),
                month=month,
                day=day,
                hour=0,
                minute=0,
                second=1,
                timezone=timezone,
            )

        self.scheduler.start()

        await self.load_extension("jishaku")


bot = MyBot()


async def send_birthday_message(row: aiosqlite.Row):
    if not bot.db:
        return

    user = bot.get_user(row[0])

    if not user:
        return

    gids: list[int] = [int(gid) for gid in row[2].split(",")]
    for gid in gids:
        cursor = await bot.db.execute("SELECT * FROM guild WHERE gid = ?", (gid,))
        guild_row = await cursor.fetchone()

        if not guild_row or not guild_row[4]:
            continue

        channel = bot.get_channel(guild_row[1])
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        guild = bot.get_guild(gid)
        if not guild:
            return

        embed = discord.Embed()
        embed.color = discord.Color.from_rgb(70, 200, 230)
        embed.set_author(name=f"It's a special day!")

        icon_url: str = (
            guild_row[3]
            or (bot.user.avatar.url if bot.user and bot.user.avatar else None)
            or (guild.icon.url if guild.icon else "")
        )
        embed.set_thumbnail(url=icon_url)

        embed.description = guild_row[2].replace("${0}", user.mention)

        await channel.send(embed=embed)


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

    await interaction.send(
        str(
            {
                key: (job.trigger.fields, job.trigger.timezone)
                for key, job in bot.jobs.items()
            }
        )
    )


async def month_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[discord.app_commands.Choice[str]]:
    return [
        discord.app_commands.Choice(name=month, value=month)
        for month in MONTHS
        if current.lower() in month.lower()
    ]


async def timezone_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[discord.app_commands.Choice[str]]:
    return [
        discord.app_commands.Choice(name=timezone, value=timezone)
        for timezone in sorted(zoneinfo.available_timezones())
        if current.lower() in timezone.lower()
    ][:25]


@discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@discord.app_commands.autocomplete(
    raw_month=month_autocomplete, timezone=timezone_autocomplete
)
@discord.app_commands.rename(raw_month="month")
@bot.tree.command(description="Register your birthday with the bot!")
async def registerme(
    interaction: discord.Interaction,
    raw_month: str,
    day: int,
    timezone: str,
):
    if not bot.db:
        return await interaction.response.send_message(
            "Database connection failed!", ephemeral=True
        )

    if not bot.scheduler:
        return await interaction.response.send_message(
            "AsyncIOScheduler connection failed!", ephemeral=True
        )

    if not timezone in zoneinfo.available_timezones():
        return await interaction.response.send_message(
            "Unknown timezone!", ephemeral=True
        )

    month: int = -1
    try:
        month = int(raw_month)
    except ValueError:
        month = MONTHS.index(raw_month.capitalize()) + 1

    if not month in range(1, 13):
        return await interaction.response.send_message("Invalid month!", ephemeral=True)

    if not day in range(
        1,
        29 + (1 if not month == 2 else 0) + (1 if not month in (2, 4, 6, 9, 11) else 0),
    ):
        return await interaction.response.send_message("Invalid day!", ephemeral=True)

    cursor = await bot.db.execute(
        "SELECT * FROM birthday WHERE uid = ?", (interaction.user.id,)
    )
    user_row = await cursor.fetchone()

    gids: str = ""
    if user_row:
        gids = user_row[2]

        if interaction.user.id in bot.jobs.keys():
            bot.jobs[interaction.user.id].remove()
            del bot.jobs[interaction.user.id]

    await bot.db.execute(
        "INSERT OR REPLACE INTO birthday VALUES (?, ?, ?, ?)",
        (
            interaction.user.id,
            f"{month}-{day}",
            gids,
            timezone,
        ),
    )
    await bot.db.commit()

    if gids:
        bot.jobs[interaction.user.id] = bot.scheduler.add_job(
            send_birthday_message,
            "cron",
            args=(user_row,),
            month=month,
            day=day,
            hour=0,
            minute=0,
            second=1,
            timezone=timezone,
        )

    await interaction.response.send_message("Birthday registered!", ephemeral=True)


class Configure(ui.Modal, title="Configure"):
    channel = ui.Label(
        text="Channel to send birthday announcements",
        component=ui.TextInput(required=True),
    )
    message = ui.Label(
        text="The birthday announcement itself!",
        component=ui.TextInput(required=True, placeholder="Today is ${0}!'s birthday!"),
    )
    icon = ui.Label(
        text="Image in birthday related embeds (optional)",
        component=ui.FileUpload(required=False),
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not bot.db:
            await interaction.response.send_message(
                "Database connection failed!", ephemeral=True
            )
            return

        if not interaction.guild:
            await interaction.response.send_message("Unexpected error!", ephemeral=True)
            return

        wanted_channel: str = (
            self.channel.component.value  # pyright: ignore[reportAttributeAccessIssue]
        )

        message: str = (
            self.message.component.value  # pyright: ignore[reportAttributeAccessIssue]
        )

        icon: str = ""
        try:
            icon: str = (
                self.icon.component.values[  # pyright: ignore[reportAttributeAccessIssue]
                    0
                ].url
            )
        except IndexError:
            pass

        try:
            channel = next(
                channel
                for channel in interaction.guild.text_channels
                if channel.name == wanted_channel
            )
        except StopIteration:
            await interaction.response.send_message(
                f"Couldn't find requested channel `{wanted_channel}`!", ephemeral=True
            )
            return

        cursor = await bot.db.execute(
            "SELECT enabled from guild WHERE gid = ?", (interaction.guild.id,)
        )
        guild_row = await cursor.fetchone()

        enabled: int = 1
        if guild_row:
            enabled = guild_row[0]

        await bot.db.execute(
            "INSERT OR REPLACE INTO guild VALUES (?, ?, ?, ?, ?)",
            (interaction.guild.id, channel.id, message, icon, enabled),
        )
        await bot.db.commit()

        await interaction.response.send_message(
            "Birthday announcements have been configured!", ephemeral=True
        )


@discord.app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
@discord.app_commands.checks.has_permissions(manage_guild=True)
@bot.tree.command(
    description="Configure birthday announcements in the server (admin-only)"
)
async def config(interaction: discord.Interaction):
    if not interaction.guild:
        return

    await interaction.response.send_modal(Configure())


@discord.app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
@discord.app_commands.checks.has_permissions(manage_guild=True)
@bot.tree.command(
    description="Enable/disable birthday announcements in the server (admin-only)"
)
async def toggle(interaction: discord.Interaction):
    if not bot.db:
        return await interaction.response.send_message(
            "Database connection failed!", ephemeral=True
        )

    if not interaction.guild:
        return

    cursor = await bot.db.execute(
        "SELECT * from guild WHERE gid = ?", (interaction.guild.id,)
    )
    guild_row = await cursor.fetchone()

    if not guild_row:
        return await interaction.response.send_message(
            "Configure settings with /config first!", ephemeral=True
        )

    cid: int = guild_row[1]
    message: str = guild_row[2]
    icon: str = guild_row[3]
    enabled: int = guild_row[4]

    for member in interaction.guild.members:
        cursor = await bot.db.execute(
            "SELECT * FROM birthday WHERE uid = ?", (member.id,)
        )
        gids_user_row = await cursor.fetchone()

        date: str = ""
        gids_raw: str = ""
        timezone: str = ""
        if gids_user_row:
            date = gids_user_row[1]
            gids_raw = gids_user_row[2]
            timezone = gids_user_row[3]

        try:
            gids: list[int] = [int(gid) for gid in gids_raw.split(",")]
        except ValueError:
            gids = []

        if enabled:
            gids.remove(interaction.guild.id)
        else:
            gids.append(interaction.guild.id)

        await bot.db.execute(
            "INSERT OR REPLACE INTO birthday VALUES (?, ?, ?, ?)",
            (
                member.id,
                date,
                ",".join([str(gid) for gid in gids]),
                timezone,
            ),
        )

    await bot.db.execute(
        "INSERT OR REPLACE INTO guild VALUES (?, ?, ?, ?, ?)",
        (interaction.guild.id, cid, message, icon, not enabled),
    )

    await bot.db.commit()

    await interaction.response.send_message("Toggled!", ephemeral=True)


def humanize_date(date: str) -> str:
    month_raw, _, day_raw = date.partition("-")
    month, day = int(month_raw), int(day_raw)

    month_human = MONTHS[month - 1]
    day_human = str(day) + DAY_SUFFIXES[day - 1]

    return f"{day_human} of {month_human}"


@discord.app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
@bot.tree.command(description="Lists registered birthdays in your server")
async def birthdays(interaction: discord.Interaction):
    if not bot.db:
        return await interaction.response.send_message(
            "Database connection failed!", ephemeral=True
        )

    if not interaction.guild:
        return

    cursor = await bot.db.execute(
        "SELECT icon from guild WHERE gid = ?", (interaction.guild.id,)
    )
    icon_row = await cursor.fetchone()

    if not icon_row:
        return await interaction.response.send_message(
            "Birthday announcements have not been configured for this server!",
            ephemeral=True,
        )

    mtbd: dict[str, str] = {}
    for member in sorted(interaction.guild.members, key=lambda x: x.display_name):
        cursor = await bot.db.execute(
            "SELECT * from birthday WHERE uid = ?", (member.id,)
        )
        birthday_row = await cursor.fetchone()

        if not birthday_row or not birthday_row[1]:
            continue

        mtbd[member.mention] = humanize_date(birthday_row[1])

    embed = discord.Embed()
    embed.color = discord.Color.from_rgb(70, 200, 230)
    embed.set_author(name=f"{interaction.guild.name} birthdays")

    icon_url: str = (
        (interaction.guild.icon.url if interaction.guild.icon else None)
        or icon_row[0]
        or (bot.user.avatar.url if bot.user and bot.user.avatar else "")
    )
    embed.set_thumbnail(url=icon_url)

    for member, date in mtbd.items():
        if embed.description:
            embed.description = embed.description + f"\n**{member}**: {date}"
        else:
            embed.description = f"\n**{member}**: {date}"

    await interaction.response.send_message(embed=embed)


token = ""
with open("token.txt", "r") as handle:
    token = handle.read().strip()

bot.run(token)
