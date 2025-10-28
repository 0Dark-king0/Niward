import discord
from discord.ext import commands, tasks
from discord import app_commands
from mcstatus import JavaServer
import json
import asyncio
import os
from dotenv import load_dotenv

# تحميل متغيرات البيئة من .env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# إعدادات البوت
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")

# تحميل بيانات السيرفرات
DATA_FILE = "servers.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

servers_data = load_data()

# -------------------------------------------------------------------
# الدالة اللي تتحقق من حالة السيرفر
async def check_server_status(ip, port):
    try:
        server = JavaServer.lookup(f"{ip}:{port}")
        status = server.status()
        return {
            "online": True,
            "players": status.players.online,
            "latency": int(status.latency)
        }
    except Exception:
        return {"online": False}

# -------------------------------------------------------------------
# عند تشغيل البوت
@bot.event
async def on_ready():
    print(f"✅ {bot.user} is online and ready!")
    update_servers.start()

# -------------------------------------------------------------------
# أمر لتحديد سيرفر جديد
@bot.tree.command(name="تحديد", description="تحديد السيرفر الذي تريد مراقبته")
@app_commands.describe(address="أدخل IP والبورت بالشكل: play.server.com:25565")
async def تحديد(interaction: discord.Interaction, address: str):
    if ":" not in address:
        await interaction.response.send_message("❌ يرجى إدخال IP والبورت بهذا الشكل: `play.server.com:25565`", ephemeral=True)
        return

    ip, port = address.split(":")
    if not port.isdigit():
        await interaction.response.send_message("❌ رقم البورت غير صالح!", ephemeral=True)
        return

    user_id = str(interaction.user.id)
    servers_data[user_id] = {
        "ip": ip,
        "port": port,
        "version": "غير محددة",
        "message_id": None,
        "channel_id": interaction.channel_id
    }
    save_data(servers_data)
    await interaction.response.send_message(f"✅ تم حفظ السيرفر: `{ip}:{port}` بنجاح!", ephemeral=True)

# -------------------------------------------------------------------
# أمر لتحديد النسخة المدعومة
@bot.tree.command(name="مدعوم", description="حدد نوع النسخة المدعومة للسيرفر (جافا، بيدروك، أو كلاهما)")
@app_commands.choices(version=[
    app_commands.Choice(name="جافا", value="جافا"),
    app_commands.Choice(name="بيدروك", value="بيدروك"),
    app_commands.Choice(name="كلاهما", value="كلاهما")
])
async def مدعوم(interaction: discord.Interaction, version: app_commands.Choice[str]):
    user_id = str(interaction.user.id)
    if user_id not in servers_data:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر بعد! استخدم أمر `/تحديد` أولاً.", ephemeral=True)
        return

    servers_data[user_id]["version"] = version.value
    save_data(servers_data)
    await interaction.response.send_message(f"✅ تم تحديث النسخة المدعومة إلى: **{version.value}**", ephemeral=True)

# -------------------------------------------------------------------
# رسالة الحالة + زر الانضمام
class JoinButton(discord.ui.View):
    def __init__(self, ip, port):
        super().__init__(timeout=None)
        self.ip = ip
        self.port = port

    @discord.ui.button(label="انضمام", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.user.send(f"🎮 عنوان السيرفر:\n`{self.ip}:{self.port}`")
            await interaction.response.send_message("📩 تم إرسال IP والبورت إلى الخاص!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("⚠️ لا أستطيع إرسال رسالة خاصة لك! فعّل استقبال الرسائل الخاصة.", ephemeral=True)

# -------------------------------------------------------------------
# تحديث الحالة كل دقيقة
@tasks.loop(minutes=1)
async def update_servers():
    for user_id, info in servers_data.items():
        try:
            ip, port = info["ip"], info["port"]
            channel_id = info["channel_id"]
            version = info.get("version", "غير محددة")
            channel = bot.get_channel(channel_id)

            if not channel:
                continue

            status = await check_server_status(ip, port)
            if status["online"]:
                embed = discord.Embed(
                    title=f"🟢 السيرفر أونلاين",
                    description=f"**IP:** `{ip}`\n**Port:** `{port}`\n**Version:** {version}\n**Players:** {status['players']}\n**Ping:** {status['latency']}ms",
                    color=0x00ff00
                )
            else:
                embed = discord.Embed(
                    title=f"🔴 السيرفر أوفلاين",
                    description=f"**IP:** `{ip}`\n**Port:** `{port}`\n**Version:** {version}",
                    color=0xff0000
                )

            view = JoinButton(ip, port)

            if info.get("message_id"):
                try:
                    msg = await channel.fetch_message(info["message_id"])
                    await msg.edit(embed=embed, view=view)
                except:
                    sent = await channel.send(embed=embed, view=view)
                    servers_data[user_id]["message_id"] = sent.id
            else:
                sent = await channel.send(embed=embed, view=view)
                servers_data[user_id]["message_id"] = sent.id

            save_data(servers_data)
            await asyncio.sleep(2)

        except Exception as e:
            print(f"❌ خطأ أثناء تحديث السيرفر {info.get('ip')}: {e}")

# -------------------------------------------------------------------
# تشغيل البوت
bot.run(TOKEN)

