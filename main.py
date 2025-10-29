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
TOKEN = os.getenv("DISCORD_TOKEN")  # تأكد أن اسم المتغير في Railway أو .env هو DISCORD_TOKEN

# إعدادات البوت
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")

# ملفات البيانات
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
# دالة التحقق من حالة السيرفر
async def check_server_status(ip, port):
    try:
        server = JavaServer.lookup(f"{ip}:{port}")
        status = server.status()
        return {
            "online": True,
            "players": getattr(status.players, "online", 0),
            "latency": int(getattr(status, "latency", 0))
        }
    except Exception:
        return {"online": False}

# -------------------------------------------------------------------
# دالة بناء الـ Embed المعروض في الرسالة المثبتة
def build_embed(ip: str, port: str, version: str, status_info: dict, board: str = "Vanilla Survival"):
    if status_info.get("online"):
        title = "🟢 السيرفر أونلاين"
        color = 0x00ff00
        desc = f"**IP:** `{ip}`\n**Port:** `{port}`\n**Version:** {version}\n**Players:** {status_info.get('players', 0)}\n**Ping:** {status_info.get('latency', 0)}ms"
    else:
        title = "🔴 السيرفر أوفلاين"
        color = 0xff0000
        desc = f"**IP:** `{ip}`\n**Port:** `{port}`\n**Version:** {version}"

    embed = discord.Embed(title=f"🎮 Official Minecraft Server 🎮 — {title}", description=desc, color=color)
    embed.add_field(name="📌 Board", value=board, inline=False)
    embed.set_footer(text="Niward — آخر تحديث كل 60 ثانية")
    return embed

# -------------------------------------------------------------------
# امر لتحديد سيرفر جديد
@bot.tree.command(name="تحديد", description="تحديد السيرفر الذي تريد مراقبته")
@app_commands.describe(address="أدخل IP والبورت بالشكل: play.server.com:25565")
async def تحديد(interaction: discord.Interaction, address: str):
    if ":" not in address:
        await interaction.response.send_message("❌ يرجى إدخال IP والبورت بهذا الشكل: `play.server.com:25565`", ephemeral=True)
        return

    ip, port = address.split(":", 1)
    if not port.isdigit():
        await interaction.response.send_message("❌ رقم البورت غير صالح!", ephemeral=True)
        return

    user_id = str(interaction.user.id)
    # إذا تريد تخزين لكل guild بدل user عدّل المفتاح
    servers_data[user_id] = servers_data.get(user_id, {})
    servers_data[user_id].update({
        "ip": ip,
        "port": port,
        "version": servers_data[user_id].get("version", "غير محددة"),
        # channel_id & message_id يحتفظوا إن وجدوا سابقًا
        "channel_id": servers_data[user_id].get("channel_id"),
        "message_id": servers_data[user_id].get("message_id")
    })
    save_data(servers_data)
    await interaction.response.send_message(f"✅ تم حفظ السيرفر: `{ip}:{port}` بنجاح!", ephemeral=True)

# -------------------------------------------------------------------
# امر لتحديد النسخة المدعومة
@bot.tree.command(name="مدعوم", description="حدد نوع النسخة المدعومة للسيرفر (جافا، بيدروك، أو كلاهما)")
@app_commands.choices(version=[
    app_commands.Choice(name="جافا", value="جافا"),
    app_commands.Choice(name="بيدروك", value="بيدروك"),
    app_commands.Choice(name="كلاهما", value="كلاهما")
])
async def مدعوم(interaction: discord.Interaction, version: app_commands.Choice[str]):
    user_id = str(interaction.user.id)
    if user_id not in servers_data or "ip" not in servers_data[user_id]:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر بعد! استخدم أمر `/تحديد` أولاً.", ephemeral=True)
        return

    servers_data[user_id]["version"] = version.value
    save_data(servers_data)
    await interaction.response.send_message(f"✅ تم تحديث النسخة المدعومة إلى: **{version.value}**", ephemeral=True)

# -------------------------------------------------------------------
# أمر تحديد الروم (القناة) — يرسل رسالة مثبتة في القناة أو يعدل الموجودة
@bot.tree.command(name="تحديد_الروم", description="تحديد الروم الذي يرسل فيه البوت التحديثات المثبتة.")
@app_commands.describe(channel="اختر القناة التي تريد أن يرسل فيها البوت التحديث المثبت")
async def تحديد_الروم(interaction: discord.Interaction, channel: discord.TextChannel):
    user_id = str(interaction.user.id)

    if user_id not in servers_data or "ip" not in servers_data[user_id]:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر بعد! استخدم أمر `/تحديد` أولاً.", ephemeral=True)
        return

    # خزّن القناة
    servers_data[user_id]["channel_id"] = channel.id
    save_data(servers_data)

    # الآن نحاول نوجد رسالة مثبتة للبوت أو نخلق واحدة ونثبتها
    message_id = servers_data[user_id].get("message_id")

    ip = servers_data[user_id]["ip"]
    port = servers_data[user_id]["port"]
    version = servers_data[user_id].get("version", "غير محددة")
    # board ثابت الآن، تقدر تسمح للمستخدم بتغييره لاحقًا
    board = servers_data[user_id].get("board", "Vanilla Survival")

    embed = build_embed(ip, port, version, await check_server_status(ip, port), board)

    try:
        # حاول نحصل على القناة (قد تكون في Guild مختلف لكن عادة نفس الشخص)
        target_channel = channel
        if message_id:
            try:
                msg = await target_channel.fetch_message(message_id)
                # لو لاقينا الرسالة، نعدلها ونرد للمستخدم
                await msg.edit(embed=embed)
                await interaction.response.send_message(f"✅ تم تحديث الرسالة المثبتة في {channel.mention}", ephemeral=True)
            except Exception:
                # لو ما لقينا الرسالة (انتحذفت أو تم تغييرها)، أنشئ رسالة جديدة وصنع pin
                sent = await target_channel.send(embed=embed)
                try:
                    await sent.pin()
                except Exception:
                    # لو ما نقدر نثبت، نستمر بدون تثبيت
                    pass
                servers_data[user_id]["message_id"] = sent.id
                save_data(servers_data)
                await interaction.response.send_message(f"✅ تم إنشاء رسالة مثبتة جديدة في {channel.mention}", ephemeral=True)
        else:
            # لا يوجد message_id سابق — نرسل و نثبت
            sent = await target_channel.send(embed=embed)
            try:
                await sent.pin()
            except Exception:
                # لا توجد صلاحية لتثبيت الرسائل؛ لا مشكلة، نحتفظ بالرسالة بدون تثبيت
                pass
            servers_data[user_id]["message_id"] = sent.id
            save_data(servers_data)
            await interaction.response.send_message(f"✅ تم إنشاء رسالة مثبتة في {channel.mention}", ephemeral=True)

    except discord.Forbidden:
        await interaction.response.send_message("⚠️ لا أملك صلاحية كافية في هذه القناة. أحتاج صلاحية Send Messages وManage Messages (للتثبيت).", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ حدث خطأ أثناء محاولة إنشاء/تحديث الرسالة: {e}", ephemeral=True)

# -------------------------------------------------------------------
# زر الانضمام (يرسل DM فقط IP:PORT)
class JoinButton(discord.ui.View):
    def __init__(self, ip, port):
        super().__init__(timeout=None)
        self.ip = ip
        self.port = port

    @discord.ui.button(label="انضمام", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.user.send(f"📌 Board: Vanilla Survival\n🌐 IP: {self.ip}\n🔌 Port: {self.port}")
            await interaction.response.send_message("📩 تم إرسال IP والبورت إلى الخاص!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("⚠️ لا أستطيع إرسال رسالة خاصة لك! فعّل استقبال الرسائل الخاصة.", ephemeral=True)

# -------------------------------------------------------------------
# تحديث الحالة كل دقيقة — يحدّث الرسالة المثبتة نفسها فقط
@tasks.loop(minutes=1)
async def update_servers():
    for user_id, info in list(servers_data.items()):
        try:
            ip = info.get("ip")
            port = info.get("port")
            channel_id = info.get("channel_id")
            message_id = info.get("message_id")
            version = info.get("version", "غير محددة")
            board = info.get("board", "Vanilla Survival")

            if not ip or not port or not channel_id:
                continue  # لا شيء هنا للمعالجة

            channel = bot.get_channel(channel_id)
            if not channel:
                print(f"⚠️ القناة {channel_id} غير موجودة للوصول (user {user_id}).")
                continue

            status = await check_server_status(ip, port)
            embed = build_embed(ip, port, version, status, board)
            view = JoinButton(ip, port)

            if message_id:
                try:
                    msg = await channel.fetch_message(message_id)
                    await msg.edit(embed=embed, view=view)
                except Exception as e:
                    # الرسالة انحذفت أو ما قدرنا نجيبها -> نرسل رسالة جديدة ونخزن id
                    print(f"ℹ️ لم أستطع تحديث الرسالة ({message_id}) في القناة {channel_id}: {e}. سيتم إرسال رسالة جديدة.")
                    sent = await channel.send(embed=embed, view=view)
                    try:
                        await sent.pin()
                    except Exception:
                        pass
                    servers_data[user_id]["message_id"] = sent.id
                    save_data(servers_data)
            else:
                # ما في رسالة محفوظة -> نرسل ونخزن
                sent = await channel.send(embed=embed, view=view)
                try:
                    await sent.pin()
                except Exception:
                    pass
                servers_data[user_id]["message_id"] = sent.id
                save_data(servers_data)

            await asyncio.sleep(1)  # فاصل صغير بين تحديث كل رسالة لتقليل الضغط

        except Exception as e:
            print(f"❌ خطأ أثناء تحديث السيرفر {servers_data.get(user_id, {}).get('ip')}: {e}")

# -------------------------------------------------------------------
# حدث التشغيل — يسجل الأوامر ويبدأ التاسك
@bot.event
async def on_ready():
    print(f"✅ {bot.user} is online and ready!")
    try:
        synced = await bot.tree.sync()
        print(f"🔁 Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")

    # نبدأ تحديث السيرفرات لو مو شغال
    if not update_servers.is_running():
        update_servers.start()

# -------------------------------------------------------------------
# تشغيل البوت
bot.run(TOKEN)

