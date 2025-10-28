import discord
from discord import app_commands
from discord.ext import commands, tasks
import re
import json
import os
from mcstatus import MinecraftServer
from dotenv import load_dotenv

# تحميل توكن البوت
load_dotenv()
TOKEN = os.getenv("TOKEN")

# إنشاء البوت
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ---- ملفات الإعدادات ----
CONFIG_FILE = "servers.json"

# تحميل البيانات أو إنشاء جديد
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        servers = json.load(f)
else:
    servers = {}

# ---- دوال مساعدة ----
def valid_address(address: str) -> bool:
    """يتحقق من أن العنوان بصيغة IP:PORT صحيحة"""
    pattern = r"^[a-zA-Z0-9.-]+\:[0-9]{2,5}$"
    return bool(re.match(pattern, address))

def save_config():
    """يحفظ البيانات في ملف JSON"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(servers, f, ensure_ascii=False, indent=2)

async def get_status(address: str) -> str:
    """يتحقق من حالة السيرفر Online / Offline"""
    try:
        server = MinecraftServer.lookup(address)
        status = server.status()
        return "🟢 Online"
    except:
        return "🔴 Offline"

# ---- حدث تسجيل الدخول ----
@bot.event
async def on_ready():
    print(f"✅ Niward بوت جاهز: {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"تم تفعيل {len(synced)} أمر.")
    except Exception as e:
        print(e)
    # بدء المهمة الدورية لتحديث الرسائل
    update_embeds.start()

# ---- أوامر البوت ----

# 1️⃣ أمر تحديد السيرفر
@bot.tree.command(name="تحديد", description="حدد عنوان السيرفر الخاص بك (IP:PORT)")
@app_commands.describe(العنوان="أدخل الآيبي مع البورت مثل play.mysrv.com:25565")
async def تحديد(interaction: discord.Interaction, العنوان: str):
    if not valid_address(العنوان):
        await interaction.response.send_message(
            "❌ صيغة غير صحيحة! اكتب مثل: `play.mysrv.com:25565`", ephemeral=True
        )
        return

    user_id = str(interaction.user.id)
    if user_id not in servers:
        servers[user_id] = {}

    servers[user_id]["address"] = العنوان
    # القيمة الافتراضية للنسخة
    servers[user_id]["version"] = servers[user_id].get("version", "غير محدد")
    # تخزين الرسالة المثبتة (None الآن)
    servers[user_id]["message_id"] = servers[user_id].get("message_id", None)
    servers[user_id]["channel_id"] = servers[user_id].get("channel_id", None)

    save_config()
    await interaction.response.send_message(f"✅ تم تسجيل السيرفر بنجاح:\n`{العنوان}`", ephemeral=True)

# 2️⃣ أمر تحديد النسخة المدعومة
@bot.tree.command(name="مدعوم", description="حدد نسخة السيرفر المدعومة")
@app_commands.choices(نسخة=[
    app_commands.Choice(name="Java", value="Java"),
    app_commands.Choice(name="Bedrock", value="Bedrock"),
    app_commands.Choice(name="Both", value="Both")
])
async def مدعوم(interaction: discord.Interaction, نسخة: app_commands.Choice[str]):
    user_id = str(interaction.user.id)
    if user_id not in servers or "address" not in servers[user_id]:
        await interaction.response.send_message("❌ حدد السيرفر أولًا باستخدام `/تحديد`", ephemeral=True)
        return

    servers[user_id]["version"] = نسخة.value
    save_config()
    await interaction.response.send_message(f"✅ تم تعيين النسخة المدعومة: `{نسخة.value}`", ephemeral=True)

# 3️⃣ أمر تحديد الروم الذي سترسل فيه الرسالة
@bot.tree.command(name="تحديد_الروم", description="حدد الروم الذي سترسل فيه رسالة السيرفر المثبتة")
@app_commands.describe(channel="اختر الروم")
async def تحديد_الروم(interaction: discord.Interaction, channel: discord.TextChannel):
    user_id = str(interaction.user.id)
    if user_id not in servers or "address" not in servers[user_id]:
        await interaction.response.send_message("❌ حدد السيرفر أولًا باستخدام `/تحديد`", ephemeral=True)
        return

    servers[user_id]["channel_id"] = channel.id
    save_config()
    await interaction.response.send_message(f"✅ تم تحديد الروم: {channel.mention}", ephemeral=True)

# ---- زر الانضمام ----
class JoinButton(discord.ui.View):
    def __init__(self, address, port, board):
        super().__init__(timeout=None)
        self.address = address
        self.port = port
        self.board = board
        self.add_item(discord.ui.Button(label="⚡ Join Now!", style=discord.ButtonStyle.green, custom_id="join_server"))

    @discord.ui.button(label="⚡ Join Now!", style=discord.ButtonStyle.green, custom_id="join_server")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        # إرسال DM فقط مع البورد والآيبي
        try:
            await interaction.user.send(
                f"📌 Board: {self.board}\n🌐 IP: {self.address}\n🔌 Port: {self.port}"
            )
            await interaction.response.send_message("✅ تم إرسال المعلومات لك في رسالة خاصة!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ لم أتمكن من إرسال DM. تحقق من إعدادات الخصوصية.", ephemeral=True)

# ---- تحديث الرسائل تلقائيًا ----
@tasks.loop(seconds=60)
async def update_embeds():
    for user_id, data in servers.items():
        address = data.get("address")
        channel_id = data.get("channel_id")
        version = data.get("version", "غير محدد")
        message_id = data.get("message_id")

        if not address or not channel_id:
            continue

        # تحقق من الحالة
        status = await get_status(address)
        board = "Vanilla Survival"  # يمكن تغييره حسب الحاجة
        port = address.split(":")[1]

        # تجهيز Embed
        embed = discord.Embed(title="🎮 Official Minecraft Server 🎮", color=0x00ff00 if status=="🟢 Online" else 0xff0000)
        embed.add_field(name="📌 Board", value=board, inline=False)
        embed.add_field(name="🌐 IP", value=address.split(":")[0], inline=True)
        embed.add_field(name="🔌 Port", value=port, inline=True)
        embed.add_field(name="💡 Status", value=status, inline=False)
        embed.add_field(name="🖥️ Supported Version", value=version, inline=False)

        view = JoinButton(address.split(":")[0], port, board)

        try:
            channel = bot.get_channel(channel_id)
            if not channel:
                continue

            if message_id:
                # تعديل الرسالة الحالية
                msg = await channel.fetch_message(message_id)
                await msg.edit(embed=embed, view=view)
            else:
                # إرسال رسالة جديدة وتخزين ID
                msg = await channel.send(embed=embed, view=view)
                servers[user_id]["message_id"] = msg.id
                save_config()
        except Exception as e:
            print(f"⚠️ خطأ في تحديث الرسالة: {e}")

# ---- تشغيل البوت ----
bot.run(TOKEN)
