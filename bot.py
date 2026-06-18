import sqlite3
import discord
from discord.ext import commands
from discord import app_commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timezone
import logging
logging.basicConfig(level=logging.INFO)

# ======================
# BOT SETUP
# ======================

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
scheduler = AsyncIOScheduler()

import os

TOKEN = "MTUxNjQ3Njc1MTY0MTk3MjkxNg.GUn3ys.fUdOMDwaog-d3zK2ndO1XpmuSL-PLVIHtCzb_U"

ALLOWED_ROLE_IDS = {
    # Ide ird be a hasznalatra jogosult Discord rang ID-ket.
    # Pelda: 123456789012345678,
}

EVENT_COLORS = {
    "blue": 0x3498DB,
    "green": 0x2ECC71,
    "red": 0xE74C3C,
    "yellow": 0xF1C40F,
    "purple": 0x9B59B6,
    "orange": 0xE67E22,
}

@bot.tree.error
async def on_app_command_error(interaction, error):
    print("APP COMMAND ERROR:", error)

async def user_has_allowed_role(user_id, guild_id):
    guild = bot.get_guild(guild_id)
    if not guild:
        return False

    member = guild.get_member(user_id)
    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except discord.DiscordException:
            return False

    if member.guild_permissions.administrator:
        return True

    return any(role.id in ALLOWED_ROLE_IDS for role in member.roles)

async def ensure_allowed(interaction, guild_id=None):
    target_guild_id = guild_id
    if target_guild_id is None and interaction.guild:
        target_guild_id = interaction.guild.id

    if target_guild_id and await user_has_allowed_role(interaction.user.id, target_guild_id):
        return True

    message = "Nincs jogosultsagod ehhez a muvelethez."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)

    return False

# ======================
# DATABASE
# ======================

db = sqlite3.connect("/cross/discord-bot/events.db")
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS events(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    channel_id INTEGER,
    event_name TEXT,
    event_desc TEXT,
    event_color TEXT,
    start_time TEXT,
    repeat_type TEXT
)
""")

cur.execute("PRAGMA table_info(events)")
columns = {row[1] for row in cur.fetchall()}
if "event_desc" not in columns:
    cur.execute("ALTER TABLE events ADD COLUMN event_desc TEXT DEFAULT ''")
if "event_color" not in columns:
    cur.execute("ALTER TABLE events ADD COLUMN event_color TEXT DEFAULT 'blue'")

db.commit()

# ======================
# EVENT SENDER
# ======================

async def send_event(channel_id, name, desc, color="blue", mode="Auto"):
    channel = bot.get_channel(channel_id)
    if not channel:
        return

    embed = discord.Embed(
        title=f"📌 **{name}**",
        description=f"{desc}",
        color=discord.Color(EVENT_COLORS.get(color, EVENT_COLORS["blue"]))
    )

    #embed.add_field(name="Típus", value=mode, inline=True)
    embed.timestamp = datetime.now(timezone.utc)

    await channel.send(embed=embed)

# ======================
# SCHEDULER
# ======================

def register_event(event):
    event_id, guild, channel, name, desc, color, start, repeat = event
    date = datetime.fromisoformat(start)
    desc = desc or ""
    color = color or "blue"

    if repeat == "none":

        scheduler.add_job(
            send_event,
            trigger=DateTrigger(run_date=date),
            args=[channel, name, desc, color],
            id=str(event_id),
            replace_existing=True
        )

    else:

        mapping = {
            "daily": {"days": 1},
            "weekly": {"weeks": 1},
            "monthly": {"days": 30}
        }

        scheduler.add_job(
            send_event,
            trigger=IntervalTrigger(start_date=date, **mapping[repeat]),
            args=[channel, name, desc, color],
            id=str(event_id),
            replace_existing=True
        )

def load_events():
    cur.execute("""
        SELECT
        id,
        guild_id,
        channel_id,
        event_name,
        event_desc,
        event_color,
        start_time,
        repeat_type
        FROM events
        """)
    for event in cur.fetchall():
        try:
            register_event(event)
        except:
            pass

# ======================
# EDIT MODAL
# ======================

class EditEventModal(discord.ui.Modal, title="Event szerkesztése"):

    new_name = discord.ui.TextInput(label="Új név", required=False)
    new_desc = discord.ui.TextInput(label="Új leírás", required=False)
    new_time = discord.ui.TextInput(label="Új idő (YYYY-MM-DD HH:MM)", required=False)
    new_repeat = discord.ui.TextInput(label="Ismétlés (none/daily/weekly/monthly)", required=False)

    new_color = discord.ui.TextInput(label="Szin (blue/green/red/yellow/purple/orange)", required=False)

    def __init__(self, event_id):
        super().__init__()
        self.event_id = event_id

    async def on_submit(self, interaction: discord.Interaction):

        cur.execute("""
        SELECT id, guild_id, channel_id, event_name, event_desc, event_color, start_time, repeat_type
        FROM events
        WHERE id=?
        """, (self.event_id,))
        event = cur.fetchone()

        if not event:
            await interaction.response.send_message("❌ Nincs event.", ephemeral=True)
            return

        guild_id, channel_id, name, desc, color, start_time, repeat_type = event[1], event[2], event[3], event[4], event[5], event[6], event[7]

        if not await ensure_allowed(interaction, guild_id):
            return

        name = self.new_name.value or name
        desc = self.new_desc.value or desc
        repeat_type = (self.new_repeat.value or repeat_type).strip().lower()
        color = (self.new_color.value or color).strip().lower()

        if repeat_type not in {"none", "daily", "weekly", "monthly"}:
            await interaction.response.send_message(
                "Hibas ismetles! Hasznald: none, daily, weekly, monthly",
                ephemeral=True
            )
            return

        if color not in EVENT_COLORS:
            await interaction.response.send_message(
                "Hibas szin! Hasznald: blue, green, red, yellow, purple, orange",
                ephemeral=True
            )
            return

        if self.new_time.value:
            try:
                dt = datetime.strptime(self.new_time.value, "%Y-%m-%d %H:%M")
                start_time = dt.isoformat()
            except:
                await interaction.response.send_message("❌ Hibás dátum!", ephemeral=True)
                return

        cur.execute("""
        UPDATE events
        SET event_name=?, event_desc=?, event_color=?, start_time=?, repeat_type=?
        WHERE id=?
        """, (name, desc, color, start_time, repeat_type, self.event_id))

        db.commit()

        try:
            scheduler.remove_job(str(self.event_id))
        except:
            pass

        register_event((self.event_id, guild_id, channel_id, name, desc, color, start_time, repeat_type))

        await interaction.response.send_message("✏️ Event frissítve!", ephemeral=True)

class EditEventChannelModal(discord.ui.Modal, title="Event csatorna modositasa"):

    new_channel = discord.ui.TextInput(
        label="Uj csatorna (#nev vagy ID)",
        required=True
    )

    def __init__(self, event_id):
        super().__init__()
        self.event_id = event_id

    async def on_submit(self, interaction: discord.Interaction):
        cur.execute("""
        SELECT id, guild_id, channel_id, event_name, event_desc, event_color, start_time, repeat_type
        FROM events
        WHERE id=?
        """, (self.event_id,))
        event = cur.fetchone()

        if not event:
            await interaction.response.send_message("Nincs event.", ephemeral=True)
            return

        event_id, guild_id, old_channel_id, name, desc, color, start_time, repeat_type = event

        if not await ensure_allowed(interaction, guild_id):
            return

        guild = bot.get_guild(guild_id)
        if not guild:
            await interaction.response.send_message("Nem talalom a szervert.", ephemeral=True)
            return

        channel_text = self.new_channel.value.strip()
        if channel_text.startswith("<#") and channel_text.endswith(">"):
            channel_text = channel_text[2:-1]

        channel = None
        if channel_text.isdigit():
            channel = guild.get_channel(int(channel_text))
        else:
            normalized = channel_text.lstrip("#").lower()
            channel = discord.utils.get(guild.text_channels, name=normalized)

        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "Nem talalom ezt a szoveges csatornat. Adj meg csatorna emlitest, nevet vagy ID-t.",
                ephemeral=True
            )
            return

        cur.execute(
            "UPDATE events SET channel_id=? WHERE id=?",
            (channel.id, self.event_id)
        )
        db.commit()

        try:
            scheduler.remove_job(str(self.event_id))
        except:
            pass

        register_event((event_id, guild_id, channel.id, name, desc, color, start_time, repeat_type))

        await interaction.response.send_message(
            f"Event csatorna frissitve: {channel.mention}",
            ephemeral=True
        )

# ======================
# EVENT VIEW (BUTTONS)
# ======================

class EventView(discord.ui.View):

    def __init__(self, event_id):
        super().__init__(timeout=None)
        self.event_id = event_id

    @discord.ui.button(label="⚡ Indítás", style=discord.ButtonStyle.green)
    async def trigger(self, interaction: discord.Interaction, button: discord.ui.Button):

        cur.execute("SELECT guild_id, channel_id, event_name, event_desc, event_color FROM events WHERE id=?", (self.event_id,))
        row = cur.fetchone()

        if not row:
            await interaction.response.send_message("❌ Nincs event.", ephemeral=True)
            return

        guild_id, channel_id, name, desc, color = row

        if not await ensure_allowed(interaction, guild_id):
            return

        await send_event(channel_id, name, desc, color)

        await interaction.response.send_message("⚡ Triggerelve!", ephemeral=True)

    @discord.ui.button(label="✏️ Módosítás", style=discord.ButtonStyle.blurple)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):

        cur.execute("SELECT guild_id FROM events WHERE id=?", (self.event_id,))
        row = cur.fetchone()

        if not row:
            await interaction.response.send_message("âťŚ Nincs event.", ephemeral=True)
            return

        if not await ensure_allowed(interaction, row[0]):
            return

        await interaction.response.send_modal(EditEventModal(self.event_id))

    @discord.ui.button(label="Csatorna", style=discord.ButtonStyle.gray)
    async def edit_channel(self, interaction: discord.Interaction, button: discord.ui.Button):

        cur.execute("SELECT guild_id FROM events WHERE id=?", (self.event_id,))
        row = cur.fetchone()

        if not row:
            await interaction.response.send_message("Nincs event.", ephemeral=True)
            return

        if not await ensure_allowed(interaction, row[0]):
            return

        await interaction.response.send_modal(EditEventChannelModal(self.event_id))

    @discord.ui.button(label="🗑 Törlés", style=discord.ButtonStyle.red)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):

        cur.execute("SELECT guild_id FROM events WHERE id=?", (self.event_id,))
        row = cur.fetchone()

        if not row:
            await interaction.response.send_message("âťŚ Nincs event.", ephemeral=True)
            return

        if not await ensure_allowed(interaction, row[0]):
            return

        cur.execute("DELETE FROM events WHERE id=?", (self.event_id,))
        db.commit()

        try:
            scheduler.remove_job(str(self.event_id))
        except:
            pass

        await interaction.response.send_message("🗑 Törölve!", ephemeral=True)

# ======================
# /event_add
# ======================

@bot.tree.command(name="event_add")
@app_commands.describe(
    name="Event neve",
    desc="Leírás",
    channel="Csatorna, ahova az event kiiras menjen",
    start="YYYY-MM-DD HH:MM",
    repeat="none/daily/weekly/monthly",
    color="Kiiras szine"
)
@app_commands.choices(
    repeat=[
        app_commands.Choice(name="Nincs", value="none"),
        app_commands.Choice(name="Napi", value="daily"),
        app_commands.Choice(name="Heti", value="weekly"),
        app_commands.Choice(name="Havi", value="monthly"),
    ],
    color=[
        app_commands.Choice(name="Kek", value="blue"),
        app_commands.Choice(name="Zold", value="green"),
        app_commands.Choice(name="Piros", value="red"),
        app_commands.Choice(name="Sarga", value="yellow"),
        app_commands.Choice(name="Lila", value="purple"),
        app_commands.Choice(name="Narancs", value="orange"),
    ],
)
async def event_add(interaction: discord.Interaction, name: str, desc: str, channel: discord.TextChannel, start: str, repeat: str, color: str):
    if not await ensure_allowed(interaction):
        return

    try:
        dt = datetime.strptime(start, "%Y-%m-%d %H:%M")

        cur.execute("""
        INSERT INTO events (guild_id, channel_id, event_name, event_desc, event_color, start_time, repeat_type)
        VALUES (?,?,?,?,?,?,?)
        """, (
            interaction.guild.id,
            channel.id,
            name,
            desc,
            color,
            dt.isoformat(),
            repeat
        ))

        db.commit()
        event_id = cur.lastrowid

        cur.execute("""
        SELECT id, guild_id, channel_id, event_name, event_desc, event_color, start_time, repeat_type
        FROM events WHERE id=?
        """, (event_id,))

        register_event(cur.fetchone())

        await interaction.response.send_message(f"✅ Event létrehozva! (#{event_id})", ephemeral=True)

    except Exception as e:
        import traceback
        traceback.print_exc()
        await interaction.response.send_message(f"❌ Hiba: {e}", ephemeral=True)

# ======================
# /event_list (UI)
# ======================

@bot.tree.command(name="event_list")
async def event_list(interaction: discord.Interaction):
    if not await ensure_allowed(interaction):
        return

    cur.execute(
        "SELECT id, channel_id, event_name, event_desc, event_color, start_time, repeat_type FROM events WHERE guild_id=?",
        (interaction.guild.id,)
    )

    rows = cur.fetchall()

    if not rows:
        await interaction.response.send_message("❌ Nincs event.", ephemeral=True)
        return

    await interaction.response.send_message("📋 Event lista elküldve privátban!", ephemeral=True)

    for r in rows:
        event_id, channel_id, name, desc, color, start_time, repeat_type = r

        embed = discord.Embed(
            title=f"📌 {name} #{event_id}",
            description=desc,
            color=discord.Color(EVENT_COLORS.get(color, EVENT_COLORS["blue"]))
        )

        embed.add_field(name="Ido", value=start_time, inline=False)
        embed.add_field(name="Csatorna", value=f"<#{channel_id}>", inline=False)
        embed.add_field(name="Ismetles", value=repeat_type, inline=True)
        embed.add_field(name="Szin", value=color, inline=True)

        try:
            await interaction.user.send(embed=embed, view=EventView(event_id))
        except:
            await interaction.followup.send(
                "❌ Nem tudtam DM-et küldeni, engedélyezd a privát üzeneteket.",
                ephemeral=True
    )

# ======================
# /trigger
# ======================

@bot.tree.command(name="trigger")
@app_commands.describe(event_id="Event ID")
async def trigger(interaction: discord.Interaction, event_id: int):
    if not await ensure_allowed(interaction):
        return

    cur.execute(
        "SELECT channel_id, event_name, event_desc, event_color FROM events WHERE id=? AND guild_id=?",
        (event_id, interaction.guild.id)
    )
    row = cur.fetchone()

    if not row:
        await interaction.response.send_message("❌ Nincs ilyen event.", ephemeral=True)
        return

    channel_id, name, desc, color = row

    await send_event(channel_id, name, desc, color)

    await interaction.response.send_message("⚡ Triggerelve!", ephemeral=True)

# ======================
# START
# ======================



synced = False

@bot.event
async def on_ready():
    global synced

    if not synced:
        for guild in bot.guilds:
            guild_object = discord.Object(id=guild.id)
            bot.tree.copy_global_to(guild=guild_object)
            await bot.tree.sync(guild=guild_object)
            print(f"Slash commandok frissitve ezen a szerveren: {guild.name} ({guild.id})")

        synced = True

    if not scheduler.running:
        scheduler.start()

    load_events()

    print(f"Online: {bot.user}")

bot.run(TOKEN)
