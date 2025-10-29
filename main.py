import discord
from discord.ext import commands, tasks
from discord import app_commands
from mcstatus import JavaServer
import requests
import json
import asyncio
import os
from dotenv import load_dotenv
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

# تحميل متغيرات البيئة من .env
load_dotenv()
TOKEN = os.getenv("TOKEN")

# إعدادات البوت
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")

# ملفات البيانات
DATA_FILE = "servers.json"
STATS_FILE = "stats.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"❌ خطأ في حفظ البيانات: {e}")

def load_stats():
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_stats(data):
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"❌ خطأ في حفظ الإحصائيات: {e}")

servers_data = load_data()
stats_data = load_stats()
offline_counters = {}

# ✅ HTTP Server بسيط لـ Railway Health Check
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Bot is running!')
    
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"✅ Health check server running on port {port}")
    server.serve_forever()

# -------------------------------------------------------------------
# دالة التحقق من صحة URL الصورة
def is_valid_image_url(url):
    try:
        response = requests.head(url, timeout=5)
        content_type = response.headers.get('content-type', '')
        return response.status_code == 200 and content_type.startswith('image/')
    except:
        return False

# -------------------------------------------------------------------
# دالة التحقق الذكية من حالة السيرفر
async def check_server_status(ip, port):
    server_key = f"{ip}:{port}"
    offline_counters.setdefault(server_key, 0)

    # إحصائيات
    stats_data.setdefault(server_key, {
        "total_checks": 0,
        "online_count": 0,
        "offline_count": 0,
        "max_players": 0,
        "total_players": 0,
        "last_online": None,
        "last_offline": None
    })

    try:
        server = JavaServer.lookup(server_key)
        status = await asyncio.wait_for(
            asyncio.to_thread(server.status), 
            timeout=5
        )
        players = getattr(status.players, "online", 0)
        latency = int(getattr(status, "latency", 0))

        # تحديث الإحصائيات
        stats_data[server_key]["total_checks"] += 1
        stats_data[server_key]["online_count"] += 1
        stats_data[server_key]["total_players"] += players
        stats_data[server_key]["max_players"] = max(stats_data[server_key]["max_players"], players)
        stats_data[server_key]["last_online"] = datetime.now().isoformat()

        if players == 0:
            offline_counters[server_key] += 1
        else:
            offline_counters[server_key] = 0

        if offline_counters[server_key] >= 2:
            return {"online": False, "players": 0, "latency": 0, "reason": "standby"}

        save_stats(stats_data)
        return {"online": True, "players": players, "latency": latency}

    except Exception as e:
        print(f"⚠️ mcstatus فشل لـ {server_key}: {e}")
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(requests.get, f"https://api.mcsrvstat.us/2/{ip}"),
                timeout=5
            )
            data = response.json()
            if data.get("online"):
                players = data.get("players", {}).get("online", 0)
                
                stats_data[server_key]["total_checks"] += 1
                stats_data[server_key]["online_count"] += 1
                stats_data[server_key]["total_players"] += players
                stats_data[server_key]["max_players"] = max(stats_data[server_key]["max_players"], players)
                stats_data[server_key]["last_online"] = datetime.now().isoformat()
                
                if players == 0:
                    offline_counters[server_key] += 1
                else:
                    offline_counters[server_key] = 0
                if offline_counters[server_key] >= 2:
                    return {"online": False, "players": 0, "latency": 0, "reason": "standby"}
                
                save_stats(stats_data)
                return {"online": True, "players": players, "latency": 0}
        except Exception as e2:
            print(f"⚠️ API backup فشل لـ {server_key}: {e2}")

    offline_counters[server_key] += 1
    stats_data[server_key]["total_checks"] += 1
    stats_data[server_key]["offline_count"] += 1
    stats_data[server_key]["last_offline"] = datetime.now().isoformat()
    save_stats(stats_data)
    return {"online": False, "players": 0, "latency": 0, "reason": "offline"}

# -------------------------------------------------------------------
def build_embed(ip: str, port: str, version: str, status_info: dict, board: str = "Vanilla Survival", 
                image_url: str = None, thumbnail_url: str = None, custom_footer: str = None):
    reason = status_info.get("reason", "")
    if status_info.get("online"):
        title = "🟢 السيرفر أونلاين"
        color = 0x00ff00
        desc = f"**IP:** `{ip}`\n**Port:** `{port}`\n**Version:** {version}\n**Players:** {status_info.get('players', 0)}\n**Ping:** {status_info.get('latency', 0)}ms"
    else:
        if reason == "standby":
            title = "🟠 السيرفر في وضع الاستعداد (Standby)"
            color = 0xffa500
        else:
            title = "🔴 السيرفر أوفلاين"
            color = 0xff0000
        desc = f"**IP:** `{ip}`\n**Port:** `{port}`\n**Version:** {version}"

    embed = discord.Embed(title=f"🎮 Official Minecraft Server 🎮 — {title}", description=desc, color=color)
    embed.add_field(name="📌 Board", value=board, inline=False)
    
    # إضافة الصور
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    if image_url:
        embed.set_image(url=image_url)
    
    footer_text = custom_footer if custom_footer else "Niward — آخر تحديث كل 60 ثانية"
    embed.set_footer(text=footer_text)
    return embed

# -------------------------------------------------------------------
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
    servers_data[user_id] = servers_data.get(user_id, {})
    servers_data[user_id].update({
        "ip": ip,
        "port": port,
        "version": servers_data[user_id].get("version", "غير محددة"),
        "board": servers_data[user_id].get("board", "Vanilla Survival"),
        "channel_id": servers_data[user_id].get("channel_id"),
        "message_id": servers_data[user_id].get("message_id"),
        "image_url": servers_data[user_id].get("image_url"),
        "thumbnail_url": servers_data[user_id].get("thumbnail_url"),
        "custom_footer": servers_data[user_id].get("custom_footer")
    })
    save_data(servers_data)
    await interaction.response.send_message(f"✅ تم حفظ السيرفر: `{ip}:{port}` بنجاح!", ephemeral=True)

# -------------------------------------------------------------------
@bot.tree.command(name="مدعوم", description="حدد نوع النسخة المدعومة للسيرفر")
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
@bot.tree.command(name="تعيين_صورة", description="إضافة صورة مخصصة للرسالة")
@app_commands.describe(
    image_url="رابط الصورة الكبيرة (تظهر أسفل الرسالة)",
    thumbnail_url="رابط الصورة الصغيرة (تظهر في الزاوية اليمنى)"
)
async def تعيين_صورة(interaction: discord.Interaction, image_url: str = None, thumbnail_url: str = None):
    user_id = str(interaction.user.id)
    if user_id not in servers_data or "ip" not in servers_data[user_id]:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر بعد! استخدم أمر `/تحديد` أولاً.", ephemeral=True)
        return

    if not image_url and not thumbnail_url:
        await interaction.response.send_message("❌ يجب إدخال رابط صورة واحدة على الأقل!", ephemeral=True)
        return

    # التحقق من صحة الروابط
    if image_url and not is_valid_image_url(image_url):
        await interaction.response.send_message("❌ رابط الصورة الكبيرة غير صالح أو لا يعمل!", ephemeral=True)
        return
    
    if thumbnail_url and not is_valid_image_url(thumbnail_url):
        await interaction.response.send_message("❌ رابط الصورة الصغيرة غير صالح أو لا يعمل!", ephemeral=True)
        return

    servers_data[user_id]["image_url"] = image_url
    servers_data[user_id]["thumbnail_url"] = thumbnail_url
    save_data(servers_data)

    msg = "✅ تم تحديث الصور:\n"
    if image_url:
        msg += f"• صورة كبيرة: ✓\n"
    if thumbnail_url:
        msg += f"• صورة صغيرة: ✓"
    
    await interaction.response.send_message(msg, ephemeral=True)

# -------------------------------------------------------------------
@bot.tree.command(name="حذف_صورة", description="حذف الصور المخصصة من الرسالة")
async def حذف_صورة(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if user_id not in servers_data:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر بعد!", ephemeral=True)
        return

    servers_data[user_id]["image_url"] = None
    servers_data[user_id]["thumbnail_url"] = None
    save_data(servers_data)
    await interaction.response.send_message("✅ تم حذف جميع الصور المخصصة!", ephemeral=True)

# -------------------------------------------------------------------
@bot.tree.command(name="تعيين_بورد", description="تخصيص اسم البورد (Board) الخاص بك")
@app_commands.describe(board_name="اسم البورد الجديد (مثال: Survival Plus، SkyBlock)")
async def تعيين_بورد(interaction: discord.Interaction, board_name: str):
    user_id = str(interaction.user.id)
    if user_id not in servers_data or "ip" not in servers_data[user_id]:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر بعد! استخدم أمر `/تحديد` أولاً.", ephemeral=True)
        return

    servers_data[user_id]["board"] = board_name
    save_data(servers_data)
    await interaction.response.send_message(f"✅ تم تحديث اسم البورد إلى: **{board_name}**", ephemeral=True)

# -------------------------------------------------------------------
@bot.tree.command(name="تخصيص_فوتر", description="تخصيص نص الفوتر في الرسالة")
@app_commands.describe(footer_text="النص الذي سيظهر في أسفل الرسالة")
async def تخصيص_فوتر(interaction: discord.Interaction, footer_text: str):
    user_id = str(interaction.user.id)
    if user_id not in servers_data or "ip" not in servers_data[user_id]:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر بعد! استخدم أمر `/تحديد` أولاً.", ephemeral=True)
        return

    servers_data[user_id]["custom_footer"] = footer_text
    save_data(servers_data)
    await interaction.response.send_message(f"✅ تم تحديث نص الفوتر إلى: **{footer_text}**", ephemeral=True)

# -------------------------------------------------------------------
@bot.tree.command(name="إحصائيات", description="عرض إحصائيات السيرفر")
async def إحصائيات(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if user_id not in servers_data or "ip" not in servers_data[user_id]:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر بعد!", ephemeral=True)
        return

    ip = servers_data[user_id]["ip"]
    port = servers_data[user_id]["port"]
    server_key = f"{ip}:{port}"

    if server_key not in stats_data:
        await interaction.response.send_message("❌ لا توجد إحصائيات لهذا السيرفر بعد!", ephemeral=True)
        return

    stats = stats_data[server_key]
    total_checks = stats.get("total_checks", 0)
    online_count = stats.get("online_count", 0)
    offline_count = stats.get("offline_count", 0)
    max_players = stats.get("max_players", 0)
    total_players = stats.get("total_players", 0)
    
    avg_players = round(total_players / online_count, 2) if online_count > 0 else 0
    uptime_percentage = round((online_count / total_checks * 100), 2) if total_checks > 0 else 0

    embed = discord.Embed(
        title=f"📊 إحصائيات السيرفر: `{ip}:{port}`",
        color=0x3498db
    )
    embed.add_field(name="🔍 إجمالي الفحوصات", value=f"`{total_checks}`", inline=True)
    embed.add_field(name="🟢 مرات الأونلاين", value=f"`{online_count}`", inline=True)
    embed.add_field(name="🔴 مرات الأوفلاين", value=f"`{offline_count}`", inline=True)
    embed.add_field(name="👥 أعلى عدد لاعبين", value=f"`{max_players}`", inline=True)
    embed.add_field(name="📈 متوسط اللاعبين", value=f"`{avg_players}`", inline=True)
    embed.add_field(name="⏱️ نسبة التشغيل", value=f"`{uptime_percentage}%`", inline=True)
    
    if stats.get("last_online"):
        last_online = datetime.fromisoformat(stats["last_online"]).strftime("%Y-%m-%d %H:%M")
        embed.add_field(name="🕐 آخر مرة أونلاين", value=f"`{last_online}`", inline=False)

    embed.set_footer(text="Niward Statistics")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# -------------------------------------------------------------------
@bot.tree.command(name="حذف", description="حذف السيرفر من البيانات")
async def حذف(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if user_id not in servers_data:
        await interaction.response.send_message("❌ لا يوجد سيرفر محفوظ!", ephemeral=True)
        return

    # حذف الرسالة المثبتة
    channel_id = servers_data[user_id].get("channel_id")
    message_id = servers_data[user_id].get("message_id")
    
    if channel_id and message_id:
        try:
            channel = bot.get_channel(channel_id)
            if channel:
                msg = await channel.fetch_message(message_id)
                await msg.delete()
        except:
            pass

    del servers_data[user_id]
    save_data(servers_data)
    await interaction.response.send_message("✅ تم حذف السيرفر وجميع بياناته بنجاح!", ephemeral=True)

# -------------------------------------------------------------------
@bot.tree.command(name="تحديد_الروم", description="تحديد الروم الذي يرسل فيه البوت التحديثات المثبتة")
@app_commands.describe(channel="اختر القناة التي تريد أن يرسل فيها البوت التحديث المثبت")
async def تحديد_الروم(interaction: discord.Interaction, channel: discord.TextChannel):
    user_id = str(interaction.user.id)

    if user_id not in servers_data or "ip" not in servers_data[user_id]:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر بعد! استخدم أمر `/تحديد` أولاً.", ephemeral=True)
        return

    servers_data[user_id]["channel_id"] = channel.id
    save_data(servers_data)

    await interaction.response.defer(ephemeral=True)

    ip = servers_data[user_id]["ip"]
    port = servers_data[user_id]["port"]
    version = servers_data[user_id].get("version", "غير محددة")
    board = servers_data[user_id].get("board", "Vanilla Survival")
    image_url = servers_data[user_id].get("image_url")
    thumbnail_url = servers_data[user_id].get("thumbnail_url")
    custom_footer = servers_data[user_id].get("custom_footer")

    status = await check_server_status(ip, port)
    embed = build_embed(ip, port, version, status, board, image_url, thumbnail_url, custom_footer)
    view = JoinButton(ip, port)

    try:
        message_id = servers_data[user_id].get("message_id")
        if message_id:
            try:
                msg = await channel.fetch_message(message_id)
                await msg.edit(embed=embed, view=view)
                await interaction.followup.send(f"✅ تم تحديث الرسالة المثبتة في {channel.mention}", ephemeral=True)
                return
            except:
                pass

        sent = await channel.send(embed=embed, view=view)
        try:
            await sent.pin()
        except:
            pass
        servers_data[user_id]["message_id"] = sent.id
        save_data(servers_data)
        await interaction.followup.send(f"✅ تم إنشاء رسالة مثبتة في {channel.mention}", ephemeral=True)

    except discord.Forbidden:
        await interaction.followup.send("⚠️ لا أملك صلاحية كافية في هذه القناة.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ حدث خطأ: {e}", ephemeral=True)

# -------------------------------------------------------------------
@bot.tree.command(name="معلومات", description="عرض جميع معلومات السيرفر المحفوظة")
async def معلومات(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if user_id not in servers_data or "ip" not in servers_data[user_id]:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر بعد!", ephemeral=True)
        return

    info = servers_data[user_id]
    embed = discord.Embed(title="📋 معلومات السيرفر المحفوظة", color=0x9b59b6)
    
    embed.add_field(name="🌐 IP", value=f"`{info.get('ip')}`", inline=True)
    embed.add_field(name="🔌 Port", value=f"`{info.get('port')}`", inline=True)
    embed.add_field(name="📦 Version", value=info.get("version", "غير محددة"), inline=True)
    embed.add_field(name="📌 Board", value=info.get("board", "Vanilla Survival"), inline=True)
    
    channel_id = info.get("channel_id")
    if channel_id:
        embed.add_field(name="📺 القناة", value=f"<#{channel_id}>", inline=True)
    
    embed.add_field(name="🖼️ صورة كبيرة", value="✓" if info.get("image_url") else "✗", inline=True)
    embed.add_field(name="🖼️ صورة صغيرة", value="✓" if info.get("thumbnail_url") else "✗", inline=True)
    embed.add_field(name="📝 فوتر مخصص", value="✓" if info.get("custom_footer") else "✗", inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# -------------------------------------------------------------------
class JoinButton(discord.ui.View):
    def __init__(self, ip, port):
        super().__init__(timeout=None)
        self.ip = ip
        self.port = port

    @discord.ui.button(label="انضمام", style=discord.ButtonStyle.green, custom_id="join_server_btn")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # البحث عن البورد من البيانات
            board = "Vanilla Survival"
            for user_id, info in servers_data.items():
                if info.get("ip") == self.ip and info.get("port") == self.port:
                    board = info.get("board", "Vanilla Survival")
                    break
            
            await interaction.user.send(f"📌 Board: {board}\n🌐 IP: {self.ip}\n🔌 Port: {self.port}")
            await interaction.response.send_message("📩 تم إرسال IP والبورت إلى الخاص!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("⚠️ لا أستطيع إرسال رسالة خاصة لك! تأكد من فتح الرسائل الخاصة.", ephemeral=True)

# -------------------------------------------------------------------
@tasks.loop(minutes=1)
async def update_servers():
    await bot.wait_until_ready()
    
    for user_id, info in list(servers_data.items()):
        try:
            ip = info.get("ip")
            port = info.get("port")
            channel_id = info.get("channel_id")
            message_id = info.get("message_id")
            version = info.get("version", "غير محددة")
            board = info.get("board", "Vanilla Survival")
            image_url = info.get("image_url")
            thumbnail_url = info.get("thumbnail_url")
            custom_footer = info.get("custom_footer")

            if not ip or not port or not channel_id:
                continue

            channel = bot.get_channel(channel_id)
            if not channel:
                continue

            status = await check_server_status(ip, port)
            embed = build_embed(ip, port, version, status, board, image_url, thumbnail_url, custom_footer)
            view = JoinButton(ip, port)

            if message_id:
                try:
                    msg = await channel.fetch_message(message_id)
                    await msg.edit(embed=embed, view=view)
                except discord.NotFound:
                    sent = await channel.send(embed=embed, view=view)
                    try:
                        await sent.pin()
                    except:
                        pass
                    servers_data[user_id]["message_id"] = sent.id
                    save_data(servers_data)
                except Exception as e:
                    print(f"⚠️ خطأ في تحديث الرسالة: {e}")
            else:
                sent = await channel.send(embed=embed, view=view)
                try:
                    await sent.pin()
                except:
                    pass
                servers_data[user_id]["message_id"] = sent.id
                save_data(servers_data)

            await asyncio.sleep(1)

        except Exception as e:
            print(f"❌ خطأ أثناء تحديث السيرفر {info.get('ip')}: {e}")

# -------------------------------------------------------------------
@bot.event
async def on_ready():
    print(f"✅ {bot.user} is online and ready!")
    print(f"📊 Servers in database: {len(servers_data)}")
    
    try:
        synced = await bot.tree.sync()
        print(f"🔁 Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")

    # تسجيل الـ View للأزرار
    bot.add_view(JoinButton("", ""))

    if not update_servers.is_running():
        update_servers.start()
        print("🔄 Auto-update task started")

# -------------------------------------------------------------------
if __name__ == "__main__":
    # بدء الـ health check server في thread منفصل
    health_thread = Thread(target=run_health_server, daemon=True)
    health_thread.start()
    
    # بدء البوت
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ خطأ في تشغيل البوت: {e}")
