import sqlite3
import discord
from discord.ext import commands
from discord import app_commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime

TOKEN = "IDE_A_TOKEN"

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
scheduler = AsyncIOScheduler()

# ======================
# SQLITE
# ======================

db = sqlite3.connect("events.db")
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS events(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    channel_id INTEGER,
    event_name TEXT,
    start_time TEXT,
    repeat_type TEXT
)
""")

db.commit()


# ======================
# EVENT FUNCTIONS
# ======================

async def send_event(channel_id, text):
    channel = bot.get_channel(channel_id)

    if channel:
        await channel.send(f"📌 Esemény: **{text}**")


def register_event(event):

    event_id, guild, channel, name, start, repeat = event

    date = datetime.fromisoformat(start)

    if repeat == "none":

        scheduler.add_job(
            send_event,
            "date",
            run_date=date,
            args=[channel, name],
            id=str(event_id)
        )

    else:

        mapping = {
            "daily": {"days": 1},
            "weekly": {"weeks": 1},
            "monthly": {"days": 30}
        }

        scheduler.add_job(
            send_event,
            "interval",
            start_date=date,
            args=[channel, name],
            id=str(event_id),
            **mapping[repeat]
        )


def load_events():

    cur.execute("SELECT * FROM events")

    for event in cur.fetchall():

        try:
            register_event(event)
        except:
            pass


# ======================
# BOT
# ======================

@bot.event
async def on_ready():

    scheduler.start()

    load_events()

    await bot.tree.sync()

    print(bot.user)


# ======================
# /event add
# ======================

@bot.tree.command(name="event")
@app_commands.describe(
    action="add / remove / list",
    name="esemény neve",
    start="YYYY-MM-DD HH:MM",
    repeat="none/daily/weekly/monthly"
)

async def event(
    interaction: discord.Interaction,
    action: str,
    name: str = None,
    start: str = None,
    repeat: str = "none"
):

    if action == "add":

        if not name or not start:

            await interaction.response.send_message(
                "Adj meg nevet és időpontot!"
            )

            return

        try:

            dt = datetime.strptime(
                start,
                "%Y-%m-%d %H:%M"
            )

        except:

            await interaction.response.send_message(
                "Formátum: 2026-06-15 18:30"
            )

            return

        cur.execute("""
        INSERT INTO events(
        guild_id,
        channel_id,
        event_name,
        start_time,
        repeat_type
        )
        VALUES(?,?,?,?,?)
        """, (

            interaction.guild.id,
            interaction.channel.id,
            name,
            dt.isoformat(),
            repeat

        ))

        db.commit()

        event_id = cur.lastrowid

        cur.execute(
            "SELECT * FROM events WHERE id=?",
            (event_id,)
        )

        register_event(cur.fetchone())

        await interaction.response.send_message(
            f"✅ Létrehozva: {name}"
        )

    elif action == "list":

        cur.execute("""
        SELECT id,event_name,start_time,repeat_type
        FROM events
        WHERE guild_id=?
        """, (

            interaction.guild.id,

        ))

        rows = cur.fetchall()

        if not rows:

            await interaction.response.send_message(
                "Nincs esemény."
            )

            return

        msg = ""

        for r in rows:

            msg += (
                f"ID:{r[0]}\n"
                f"Név:{r[1]}\n"
                f"Idő:{r[2]}\n"
                f"Ism:{r[3]}\n\n"
            )

        await interaction.response.send_message(msg)

    elif action == "remove":

        try:

            event_id = int(name)

        except:

            await interaction.response.send_message(
                "Add meg az esemény ID-ját."
            )

            return

        try:
            scheduler.remove_job(
                str(event_id)
            )
        except:
            pass

        cur.execute(
            "DELETE FROM events WHERE id=?",
            (event_id,)
        )

        db.commit()

        await interaction.response.send_message(
            "🗑️ Törölve"
        )

bot.run(TOKEN)
