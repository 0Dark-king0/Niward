import discord
from discord.ext import commands, tasks
from discord import app_commands
from mcstatus import JavaServer
import requests
import json
import asyncio
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
import time
from typing import Optional, Dict, Any

# تحميل متغيرات البيئة
load_dotenv()
TOKEN = os.getenv("TOKEN")

# إعدادات البوت
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")

# ملفات البيانات
DATA_FILE = "servers.json"
STATS_FILE = "stats.json"

# نظام Cache للتحقق من حالة السيرفر
status_cache = {}
CACHE_DURATION = 30  # 30 ثانية

# ألوان الـ Logs
class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    RESET = "\033[0m"

def log(message: str, color: str = Colors.RESET):
    """طباعة رسالة ملونة في الـ logs"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{color}[{timestamp}] {message}{Colors.RESET}")

# -------------------------------------------------------------------
# نظام الاستايلات المحدث
STYLES = {
    "classic": {
        "name": "🎮 Classic",
        "colors": {
            "online": 0x00ff00,
            "offline": 0xff0000,
            "standby": 0xffa500,
            "maintenance": 0x808080
        },
        "emojis": {
            "online": "🟢",
            "offline": "🔴",
            "standby": "🟠",
            "maintenance": "🚧"
        }
    },
    "modern": {
        "name": "✨ Modern",
        "colors": {
            "online": 0x2ecc71,
            "offline": 0xe74c3c,
            "standby": 0xf39c12,
            "maintenance": 0x95a5a6
        },
        "emojis": {
            "online": "✅",
            "offline": "❌",
            "standby": "⏳",
            "maintenance": "🛠️"
        }
    },
    "dark": {
        "name": "🌙 Dark",
        "colors": {
            "online": 0x1abc9c,
            "offline": 0x992d22,
            "standby": 0xe67e22,
            "maintenance": 0x7f8c8d
        },
        "emojis": {
            "online": "💚",
            "offline": "💔",
            "standby": "💛",
            "maintenance": "⚙️"
        }
    },
    "cyber": {
        "name": "⚡ Cyber",
        "colors": {
            "online": 0x00ffff,
            "offline": 0xff00ff,
            "standby": 0xffff00,
            "maintenance": 0x808080
        },
        "emojis": {
            "online": "⚡",
            "offline": "💥",
            "standby": "🔄",
            "maintenance": "🔧"
        }
    },
    "pixel": {
        "name": "🎯 Pixel",
        "colors": {
            "online": 0x00cc00,
            "offline": 0xcc0000,
            "standby": 0xccaa00,
            "maintenance": 0x666666
        },
        "emojis": {
            "online": "▣",
            "offline": "▢",
            "standby": "▤",
            "maintenance": "▥"
        }
    },
    "sunset": {
        "name": "🌅 Sunset",
        "colors": {
            "online": 0xfd79a8,
            "offline": 0x6c5ce7,
            "standby": 0xfdcb6e,
            "maintenance": 0xb2bec3
        },
        "emojis": {
            "online": "🌸",
            "offline": "🌑",
            "standby": "🌤️",
            "maintenance": "🌫️"
        }
    },
    "aurora": {
        "name": "🌌 Aurora",
        "colors": {
            "online": 0x55efc4,
            "offline": 0xff7675,
            "standby": 0xffeaa7,
            "maintenance": 0xdfe6e9
        },
        "emojis": {
            "online": "⭐",
            "offline": "💫",
            "standby": "✨",
            "maintenance": "🌟"
        }
    }
}

# -------------------------------------------------------------------
# إدارة البيانات
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            log("❌ خطأ في تحميل servers.json", Colors.RED)
            return {}
    return {}

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        log("✅ تم حفظ servers.json بنجاح", Colors.GREEN)
    except Exception as e:
        log(f"❌ خطأ في حفظ البيانات: {e}", Colors.RED)

def load_stats():
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            log("❌ خطأ في تحميل stats.json", Colors.RED)
            return {}
    return {}

def save_stats(data):
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        log(f"❌ خطأ في حفظ الإحصائيات: {e}", Colors.RED)

servers_data = load_data()
stats_data = load_stats()

# ✅ HTTP Server للـ Railway Health Check
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Niward v1.6 is running!')
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    log(f"✅ Health check server running on port {port}", Colors.GREEN)
    server.serve_forever()

# -------------------------------------------------------------------
# 🧠 نظام التحقق الذكي من حالة السيرفر (Smart Server Detection)
async def check_server_status_smart(ip: str, port: str) -> Dict[str, Any]:
    """
    نظام فحص ذكي يميز بين:
    - online: السيرفر متصل وجاهز 100%
    - standby: السيرفر في حالة تحميل أو Aternos
    - offline: السيرفر مغلق تماماً
    - maintenance: تحت الصيانة (من المستخدم)
    """
    server_key = f"{ip}:{port}"
    
    # التحقق من الـ Cache
    if server_key in status_cache:
        cache_time, cache_data = status_cache[server_key]
        if time.time() - cache_time < CACHE_DURATION:
            return cache_data
    
    result = {
        "online": False,
        "players": 0,
        "latency": 0,
        "status": "offline",
        "motd": "",
        "max_players": 0
    }
    
    # المحاولة الأولى: mcstatus
    mcstatus_ok = False
    try:
        server = JavaServer.lookup(server_key)
        status = await asyncio.wait_for(
            asyncio.to_thread(server.status), 
            timeout=8
        )
        
        players = getattr(status.players, "online", 0)
        max_players = getattr(status.players, "max", 0)
        latency = int(getattr(status, "latency", 0))
        motd = str(getattr(status, "description", ""))
        
        mcstatus_ok = True
        
        # تحليل MOTD للكشف عن حالة Standby
        motd_lower = motd.lower()
        standby_keywords = ["starting", "preparing", "aternos", "loading", "booting"]
        is_standby = any(keyword in motd_lower for keyword in standby_keywords)
        
        if is_standby or (players == 0 and max_players == 0):
            result["status"] = "standby"
            result["online"] = False
        else:
            result["status"] = "online"
            result["online"] = True
            result["players"] = players
            result["max_players"] = max_players
        
        result["latency"] = latency
        result["motd"] = motd
        
    except Exception as e:
        log(f"⚠️ mcstatus فشل لـ {server_key}: {e}", Colors.YELLOW)
    
    # المحاولة الثانية: API Backup
    if not mcstatus_ok:
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(requests.get, f"https://api.mcsrvstat.us/2/{ip}"),
                timeout=8
            )
            data = response.json()
            
            if data.get("online"):
                players = data.get("players", {}).get("online", 0)
                max_players = data.get("players", {}).get("max", 0)
                motd = str(data.get("motd", {}).get("clean", [""])[0])
                
                motd_lower = motd.lower()
                standby_keywords = ["starting", "preparing", "aternos", "loading"]
                is_standby = any(keyword in motd_lower for keyword in standby_keywords)
                
                if is_standby or (players == 0 and max_players == 0):
                    result["status"] = "standby"
                else:
                    result["status"] = "online"
                    result["online"] = True
                    result["players"] = players
                    result["max_players"] = max_players
                
                result["motd"] = motd
                
        except Exception as e:
            log(f"⚠️ API backup فشل لـ {server_key}: {e}", Colors.YELLOW)
    
    # إذا فشلت كل المحاولات
    if not result["online"] and result["status"] != "standby":
        result["status"] = "offline"
    
    # حفظ في الـ Cache
    status_cache[server_key] = (time.time(), result)
    
    return result

# -------------------------------------------------------------------
# تسجيل تغيير الحالة في الإحصائيات
def log_status_change(user_id: str, old_status: str, new_status: str):
    """تسجيل تغيير حالة السيرفر"""
    if user_id not in stats_data:
        stats_data[user_id] = {
            "total_checks": 0,
            "uptime_sessions": [],
            "downtime_sessions": [],
            "status_changes": [],
            "maintenance_count": 0,
            "total_maintenance_time": 0,
            "last_maintenance_start": None
        }
    
    stats_data[user_id]["status_changes"].append({
        "from": old_status,
        "to": new_status,
        "time": datetime.now().isoformat()
    })
    
    # الاحتفاظ بآخر 100 تغيير فقط
    if len(stats_data[user_id]["status_changes"]) > 100:
        stats_data[user_id]["status_changes"] = stats_data[user_id]["status_changes"][-100:]
    
    save_stats(stats_data)

# -------------------------------------------------------------------
# بناء الـ Embed مع دعم الصيانة
def build_embed(ip: str, port: str, version: str, status_info: Dict[str, Any], 
                board: str = "Vanilla Survival", image_url: str = None, 
                image_pos: str = None, style: str = "classic",
                custom_title: str = None, custom_desc: str = None,
                is_maintenance: bool = False):
    
    style_data = STYLES.get(style, STYLES["classic"])
    status = "maintenance" if is_maintenance else status_info.get("status", "offline")
    
    # العنوان والوصف
    if is_maintenance:
        title = f"{style_data['emojis']['maintenance']} السيرفر تحت الصيانة"
        desc = "🚧 الرجاء العودة لاحقاً - جاري تحديث السيرفر"
    elif status == "online":
        title = f"{style_data['emojis']['online']} السيرفر أونلاين"
        desc = f"**IP:** `{ip}`\n**Port:** `{port}`\n**Version:** {version}\n**Players:** {status_info.get('players', 0)}/{status_info.get('max_players', 0)}\n**Ping:** {status_info.get('latency', 0)}ms"
    elif status == "standby":
        title = f"{style_data['emojis']['standby']} السيرفر في وضع الاستعداد"
        desc = f"**IP:** `{ip}`\n**Port:** `{port}`\n**Version:** {version}\n⏳ السيرفر يتحمل أو في وضع Starting..."
    else:
        title = f"{style_data['emojis']['offline']} السيرفر أوفلاين"
        desc = f"**IP:** `{ip}`\n**Port:** `{port}`\n**Version:** {version}\n❌ السيرفر غير متصل حالياً"
    
    # استخدام العنوان والوصف المخصص إذا موجود
    if custom_title:
        title = custom_title.replace("{status}", title)
    if custom_desc:
        desc = custom_desc.replace("{ip}", ip).replace("{port}", port).replace("{version}", version)
    
    embed = discord.Embed(
        title=f"{style_data['name']} — {title}",
        description=desc,
        color=style_data["colors"][status]
    )
    
    embed.add_field(name="📌 Board", value=board, inline=False)
    
    # إضافة MOTD إذا موجود
    if status_info.get("motd") and not is_maintenance:
        motd = status_info["motd"][:100]  # أول 100 حرف فقط
        embed.add_field(name="📝 MOTD", value=f"```{motd}```", inline=False)
    
    # إضافة الصور
    if image_url and image_pos:
        if image_pos in ["فوق", "كلاهما"]:
            embed.set_thumbnail(url=image_url)
        if image_pos in ["تحت", "كلاهما"]:
            embed.set_image(url=image_url)
    
    # Footer مع الوقت
    now = datetime.now().strftime("%I:%M %p")
    embed.set_footer(text=f"Niward v1.6 | آخر تحديث: اليوم {now}")
    
    return embed

# -------------------------------------------------------------------
# زر الانضمام
class JoinButton(discord.ui.View):
    def __init__(self, ip, port, board):
        super().__init__(timeout=None)
        self.ip = ip
        self.port = port
        self.board = board

    @discord.ui.button(label="انضمام", style=discord.ButtonStyle.green, custom_id="join_server_btn")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.user.send(
                f"📌 **Board:** {self.board}\n"
                f"🌐 **IP:** `{self.ip}`\n"
                f"🔌 **Port:** `{self.port}`\n\n"
                f"انسخ الـ IP والبورت والصقهم في Minecraft!"
            )
            await interaction.response.send_message("📩 تم إرسال معلومات السيرفر!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                "⚠️ لا أستطيع إرسال رسالة خاصة!\nافتح الرسائل الخاصة من إعدادات الخصوصية.", 
                ephemeral=True
            )

# -------------------------------------------------------------------
# الأوامر
@bot.tree.command(name="تحديد", description="تحديد السيرفر")
@app_commands.describe(address="IP:Port مثل: play.server.com:25565")
async def تحديد(interaction: discord.Interaction, address: str):
    if ":" not in address:
        await interaction.response.send_message(
            "❌ يرجى إدخال IP والبورت بهذا الشكل: `play.server.com:25565`", 
            ephemeral=True
        )
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
        "image_pos": servers_data[user_id].get("image_pos"),
        "style": servers_data[user_id].get("style", "classic"),
        "maintenance": False,
        "last_status": "unknown"
    })
    save_data(servers_data)
    await interaction.response.send_message(f"✅ تم حفظ السيرفر: `{ip}:{port}`", ephemeral=True)

# -------------------------------------------------------------------
@bot.tree.command(name="صيانة", description="تفعيل/تعطيل وضع الصيانة")
@app_commands.describe(enabled="تفعيل أو تعطيل الصيانة")
@app_commands.choices(enabled=[
    app_commands.Choice(name="تفعيل", value="true"),
    app_commands.Choice(name="تعطيل", value="false")
])
async def صيانة(interaction: discord.Interaction, enabled: app_commands.Choice[str]):
    user_id = str(interaction.user.id)
    if user_id not in servers_data or "ip" not in servers_data[user_id]:
        await interaction.response.send_message(
            "❌ لم يتم تحديد سيرفر! استخدم `/تحديد` أولاً.", 
            ephemeral=True
        )
        return
    
    is_enabled = enabled.value == "true"
    servers_data[user_id]["maintenance"] = is_enabled
    
    # تحديث الإحصائيات
    if user_id not in stats_data:
        stats_data[user_id] = {"maintenance_count": 0, "last_maintenance_start": None}
    
    if is_enabled:
        stats_data[user_id]["maintenance_count"] = stats_data[user_id].get("maintenance_count", 0) + 1
        stats_data[user_id]["last_maintenance_start"] = datetime.now().isoformat()
        log_status_change(user_id, servers_data[user_id].get("last_status", "unknown"), "maintenance")
    else:
        # حساب مدة الصيانة
        if stats_data[user_id].get("last_maintenance_start"):
            start = datetime.fromisoformat(stats_data[user_id]["last_maintenance_start"])
            duration = (datetime.now() - start).total_seconds()
            stats_data[user_id]["total_maintenance_time"] = stats_data[user_id].get("total_maintenance_time", 0) + duration
    
    save_data(servers_data)
    save_stats(stats_data)
    
    status = "مفعّلة 🚧" if is_enabled else "معطّلة ✅"
    await interaction.response.send_message(f"✅ الصيانة الآن {status}", ephemeral=True)

# -------------------------------------------------------------------
@bot.tree.command(name="مدعوم", description="حدد النسخة المدعومة")
@app_commands.choices(version=[
    app_commands.Choice(name="جافا", value="جافا"),
    app_commands.Choice(name="بيدروك", value="بيدروك"),
    app_commands.Choice(name="كلاهما", value="كلاهما")
])
async def مدعوم(interaction: discord.Interaction, version: app_commands.Choice[str]):
    user_id = str(interaction.user.id)
    if user_id not in servers_data or "ip" not in servers_data[user_id]:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر!", ephemeral=True)
        return

    servers_data[user_id]["version"] = version.value
    save_data(servers_data)
    await interaction.response.send_message(f"✅ النسخة: **{version.value}**", ephemeral=True)

# -------------------------------------------------------------------
@bot.tree.command(name="تعيين_اسم", description="تغيير اسم الـ Board")
@app_commands.describe(name="اسم الـ Board الجديد")
async def تعيين_اسم(interaction: discord.Interaction, name: str):
    user_id = str(interaction.user.id)
    if user_id not in servers_data or "ip" not in servers_data[user_id]:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر!", ephemeral=True)
        return

    servers_data[user_id]["board"] = name
    save_data(servers_data)
    await interaction.response.send_message(f"✅ اسم الـ Board: **{name}**", ephemeral=True)

# -------------------------------------------------------------------
@bot.tree.command(name="تعيين_صورة", description="إضافة صورة للرسالة")
@app_commands.describe(url="رابط الصورة (https://)", position="موقع الصورة")
@app_commands.choices(position=[
    app_commands.Choice(name="فوق", value="فوق"),
    app_commands.Choice(name="تحت", value="تحت"),
    app_commands.Choice(name="كلاهما", value="كلاهما")
])
async def تعيين_صورة(interaction: discord.Interaction, url: str, position: app_commands.Choice[str]):
    user_id = str(interaction.user.id)
    if user_id not in servers_data or "ip" not in servers_data[user_id]:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر!", ephemeral=True)
        return

    if not url.startswith("https://"):
        await interaction.response.send_message("❌ الرابط يجب أن يبدأ بـ `https://`", ephemeral=True)
        return

    servers_data[user_id]["image_url"] = url
    servers_data[user_id]["image_pos"] = position.value
    save_data(servers_data)
    await interaction.response.send_message(f"✅ تم تعيين الصورة! الموقع: **{position.value}**", ephemeral=True)

# -------------------------------------------------------------------
@bot.tree.command(name="حذف_صورة", description="حذف الصورة")
async def حذف_صورة(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if user_id not in servers_data:
        await interaction.response.send_message("❌ لا توجد بيانات!", ephemeral=True)
        return

    servers_data[user_id]["image_url"] = None
    servers_data[user_id]["image_pos"] = None
    save_data(servers_data)
    await interaction.response.send_message("✅ تم حذف الصورة!", ephemeral=True)

# -------------------------------------------------------------------
@bot.tree.command(name="تخصيص_الرسالة", description="تخصيص شكل الرسالة المثبتة")
@app_commands.describe(
    style="اختر الاستايل",
    custom_title="عنوان مخصص (اختياري)",
    custom_description="وصف مخصص (اختياري)"
)
@app_commands.choices(style=[
    app_commands.Choice(name="🎮 Classic", value="classic"),
    app_commands.Choice(name="✨ Modern", value="modern"),
    app_commands.Choice(name="🌙 Dark", value="dark"),
    app_commands.Choice(name="⚡ Cyber", value="cyber"),
    app_commands.Choice(name="🎯 Pixel", value="pixel"),
    app_commands.Choice(name="🌅 Sunset", value="sunset"),
    app_commands.Choice(name="🌌 Aurora", value="aurora")
])
async def تخصيص_الرسالة(interaction: discord.Interaction, style: app_commands.Choice[str],
                         custom_title: Optional[str] = None, custom_description: Optional[str] = None):
    user_id = str(interaction.user.id)
    if user_id not in servers_data or "ip" not in servers_data[user_id]:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر!", ephemeral=True)
        return

    servers_data[user_id]["style"] = style.value
    if custom_title:
        servers_data[user_id]["custom_title"] = custom_title
    if custom_description:
        servers_data[user_id]["custom_desc"] = custom_description
    
    save_data(servers_data)
    await interaction.response.send_message(
        f"✅ تم تطبيق الاستايل: **{style.name}**\n"
        f"استخدم `/تحديد_الروم` لتحديث الرسالة",
        ephemeral=True
    )

# -------------------------------------------------------------------
@bot.tree.command(name="معلوماتي", description="عرض معلوماتك")
async def معلوماتي(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if user_id not in servers_data or "ip" not in servers_data[user_id]:
        await interaction.response.send_message("❌ لا توجد بيانات!", ephemeral=True)
        return

    info = servers_data[user_id]
    stats = stats_data.get(user_id, {})
    channel = bot.get_channel(info.get("channel_id")) if info.get("channel_id") else None
    
    embed = discord.Embed(title="📊 معلوماتك", color=0x3498db)
    embed.add_field(name="🌐 IP", value=f"`{info.get('ip')}`", inline=True)
    embed.add_field(name="🔌 Port", value=f"`{info.get('port')}`", inline=True)
    embed.add_field(name="📦 Version", value=info.get('version', 'غير محددة'), inline=True)
    embed.add_field(name="📌 Board", value=info.get('board', 'Vanilla Survival'), inline=True)
    embed.add_field(name="🎨 Style", value=STYLES.get(info.get('style', 'classic'), STYLES['classic'])['name'], inline=True)
    embed.add_field(name="📺 القناة", value=channel.mention if channel else "غير محددة", inline=True)
    embed.add_field(name="🖼️ صورة", value="✅" if info.get('image_url') else "❌", inline=True)
    embed.add_field(name="🚧 صيانة", value="✅" if info.get('maintenance') else "❌", inline=True)
    
    # إحصائيات
    if stats:
        maintenance_count = stats.get("maintenance_count", 0)
        status_changes = len(stats.get("status_changes", []))
        embed.add_field(name="📈 الإحصائيات", 
                       value=f"🔄 تغييرات الحالة: {status_changes}\n🚧 مرات الصيانة: {maintenance_count}", 
                       inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# -------------------------------------------------------------------
@bot.tree.command(name="حذف_السيرفر", description="حذف جميع البيانات")
async def حذف_السيرفر(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if user_id not in servers_data:
        await interaction.response.send_message("❌ لا توجد بيانات!", ephemeral=True)
        return

    del servers_data[user_id]
    if user_id in stats_data:
        del stats_data[user_id]
    save_data(servers_data)
    save_stats(stats_data)
    await interaction.response.send_message("✅ تم حذف جميع البيانات!", ephemeral=True)

# -------------------------------------------------------------------
@bot.tree.command(name="حالة_سريعة", description="عرض حالة السيرفر بشكل مختصر")
async def حالة_سريعة(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if user_id not in servers_data or "ip" not in servers_data[user_id]:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر!", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    info = servers_data[user_id]
    ip = info["ip"]
    port = info["port"]
    
    if info.get("maintenance"):
        await interaction.followup.send("🚧 السيرفر تحت الصيانة", ephemeral=True)
        return
    
    status = await check_server_status_smart(ip, port)
    
    if status["status"] == "online":
        msg = f"🟢 **أونلاين** | {status['players']} لاعب | Ping: {status['latency']}ms"
    elif status["status"] == "standby":
        msg = f"🟠 **Standby** | السيرفر يتحمل..."
    else:
        msg = f"🔴 **أوفلاين**"
    
    await interaction.followup.send(msg, ephemeral=True)

# -------------------------------------------------------------------
@bot.tree.command(name="الإحصائيات", description="عرض إحصائيات مفصلة")
async def الإحصائيات(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if user_id not in stats_data:
        await interaction.response.send_message("❌ لا توجد إحصائيات!", ephemeral=True)
        return
    
    stats = stats_data[user_id]
    
    embed = discord.Embed(title="📊 الإحصائيات المفصلة", color=0x9b59b6)
    
    # تغييرات الحالة
    changes = stats.get("status_changes", [])
    embed.add_field(name="🔄 تغييرات الحالة", value=f"**{len(changes)}** تغيير", inline=True)
    
    # الصيانة
    maintenance_count = stats.get("maintenance_count", 0)
    total_maintenance = stats.get("total_maintenance_time", 0)
    maintenance_hours = int(total_maintenance // 3600)
    embed.add_field(name="🚧 الصيانة", 
                   value=f"**{maintenance_count}** مرة\n⏱️ {maintenance_hours}س إجمالي", 
                   inline=True)
    
    # آخر 5 تغييرات
    if changes:
        recent = changes[-5:]
        recent_text = "\n".join([
            f"{c['from']} → {c['to']}" for c in recent
        ])
        embed.add_field(name="📝 آخر التغييرات", value=recent_text, inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# -------------------------------------------------------------------
@bot.tree.command(name="مساعدة", description="قائمة الأوامر")
async def مساعدة(interaction: discord.Interaction):
    embed = discord.Embed(title="📚 قائمة الأوامر - Niward v1.6", color=0x9b59b6)
    
    embed.add_field(
        name="⚙️ الإعداد",
        value=(
            "`/تحديد` - حدد السيرفر\n"
            "`/مدعوم` - حدد النسخة\n"
            "`/تحديد_الروم` - اختر القناة"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🎨 التخصيص",
        value=(
            "`/تعيين_اسم` - اسم Board\n"
            "`/تعيين_صورة` - أضف صورة\n"
            "`/تخصيص_الرسالة` - غيّر الاستايل"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🛠️ الإدارة",
        value=(
            "`/صيانة` - وضع الصيانة\n"
            "`/حالة_سريعة` - فحص سريع\n"
            "`/الإحصائيات` - إحصائيات مفصلة"
        ),
        inline=False
    )
    
    embed.add_field(
        name="📊 المعلومات",
        value=(
            "`/معلوماتي` - بياناتك\n"
            "`/حذف_السيرفر` - حذف كل شيء\n"
            "`/مساعدة` - هذه الرسالة"
        ),
        inline=False
    )
    
    embed.set_footer(text="Niward v1.6 | Smart Precision Update")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# -------------------------------------------------------------------
@bot.tree.command(name="تحديد_الروم", description="تحديد القناة للتحديثات")
@app_commands.describe(channel="اختر القناة")
async def تحديد_الروم(interaction: discord.Interaction, channel: discord.TextChannel):
    user_id = str(interaction.user.id)

    if user_id not in servers_data or "ip" not in servers_data[user_id]:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر!", ephemeral=True)
        return

    servers_data[user_id]["channel_id"] = channel.id
    save_data(servers_data)

    await interaction.response.defer(ephemeral=True)

    info = servers_data[user_id]
    ip = info["ip"]
    port = info["port"]
    version = info.get("version", "غير محددة")
    board = info.get("board", "Vanilla Survival")
    image_url = info.get("image_url")
    image_pos = info.get("image_pos")
    style = info.get("style", "classic")
    custom_title = info.get("custom_title")
    custom_desc = info.get("custom_desc")
    is_maintenance = info.get("maintenance", False)

    if is_maintenance:
        status = {"status": "maintenance", "players": 0, "latency": 0}
    else:
        status = await check_server_status_smart(ip, port)
    
    embed = build_embed(ip, port, version, status, board, image_url, image_pos, 
                       style, custom_title, custom_desc, is_maintenance)
    view = JoinButton(ip, port, board)

    try:
        message_id = info.get("message_id")
        if message_id:
            try:
                msg = await channel.fetch_message(message_id)
                await msg.edit(embed=embed, view=view)
                await interaction.followup.send(f"✅ تم التحديث في {channel.mention}", ephemeral=True)
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
        await interaction.followup.send(f"✅ تم إنشاء الرسالة في {channel.mention}", ephemeral=True)

    except discord.Forbidden:
        await interaction.followup.send("⚠️ لا أملك صلاحية!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ خطأ: {e}", ephemeral=True)

# -------------------------------------------------------------------
# نظام التحديث التلقائي المحسّن
@tasks.loop(minutes=1)
async def update_servers():
    await bot.wait_until_ready()
    log("🔄 بدء دورة التحديث التلقائي...", Colors.BLUE)
    
    for user_id, info in list(servers_data.items()):
        try:
            ip = info.get("ip")
            port = info.get("port")
            channel_id = info.get("channel_id")
            message_id = info.get("message_id")
            version = info.get("version", "غير محددة")
            board = info.get("board", "Vanilla Survival")
            image_url = info.get("image_url")
            image_pos = info.get("image_pos")
            style = info.get("style", "classic")
            custom_title = info.get("custom_title")
            custom_desc = info.get("custom_desc")
            is_maintenance = info.get("maintenance", False)
            last_status = info.get("last_status", "unknown")

            if not ip or not port or not channel_id:
                continue

            channel = bot.get_channel(channel_id)
            if not channel:
                continue

            if is_maintenance:
                status = {"status": "maintenance", "players": 0, "latency": 0}
            else:
                status = await check_server_status_smart(ip, port)
            
            # تسجيل تغيير الحالة
            current_status = status.get("status", "unknown")
            if current_status != last_status and last_status != "unknown":
                log_status_change(user_id, last_status, current_status)
                log(f"📊 {ip}:{port} تغيرت من {last_status} إلى {current_status}", Colors.YELLOW)
            
            servers_data[user_id]["last_status"] = current_status
            
            embed = build_embed(ip, port, version, status, board, image_url, image_pos,
                              style, custom_title, custom_desc, is_maintenance)
            view = JoinButton(ip, port, board)

            if message_id:
                try:
                    msg = await channel.fetch_message(message_id)
                    await msg.edit(embed=embed, view=view)
                    log(f"✅ تم تحديث {ip}:{port} - الحالة: {current_status}", Colors.GREEN)
                except discord.NotFound:
                    sent = await channel.send(embed=embed, view=view)
                    try:
                        await sent.pin()
                    except:
                        pass
                    servers_data[user_id]["message_id"] = sent.id
                    log(f"📝 تم إنشاء رسالة جديدة لـ {ip}:{port}", Colors.BLUE)
                except Exception as e:
                    log(f"⚠️ خطأ في تحديث {ip}:{port}: {e}", Colors.RED)
            else:
                sent = await channel.send(embed=embed, view=view)
                try:
                    await sent.pin()
                except:
                    pass
                servers_data[user_id]["message_id"] = sent.id
                log(f"📝 تم إنشاء رسالة جديدة لـ {ip}:{port}", Colors.BLUE)

            await asyncio.sleep(1)

        except Exception as e:
            log(f"❌ خطأ أثناء تحديث {info.get('ip')}: {e}", Colors.RED)
    
    # حفظ البيانات بعد كل دورة
    save_data(servers_data)

# -------------------------------------------------------------------
# مهمة الحفظ التلقائي (كل دقيقة)
@tasks.loop(minutes=1)
async def auto_save():
    save_data(servers_data)
    save_stats(stats_data)
    log("💾 تم الحفظ التلقائي للبيانات", Colors.BLUE)

# -------------------------------------------------------------------
# تنظيف الـ Cache (كل 5 دقائق)
@tasks.loop(minutes=5)
async def clean_cache():
    global status_cache
    current_time = time.time()
    old_keys = [k for k, (t, _) in status_cache.items() if current_time - t > CACHE_DURATION * 2]
    for k in old_keys:
        del status_cache[k]
    if old_keys:
        log(f"🧹 تم تنظيف {len(old_keys)} عنصر من الـ Cache", Colors.YELLOW)

# -------------------------------------------------------------------
@bot.event
async def on_ready():
    log(f"✅ {bot.user} is online and ready!", Colors.GREEN)
    log(f"📊 Servers: {len(servers_data)} | Stats: {len(stats_data)}", Colors.BLUE)
    
    try:
        synced = await bot.tree.sync()
        log(f"🔁 Synced {len(synced)} command(s)", Colors.GREEN)
    except Exception as e:
        log(f"❌ Error syncing commands: {e}", Colors.RED)

    # تسجيل الـ View
    bot.add_view(JoinButton("", "", ""))

    # بدء المهام
    if not update_servers.is_running():
        update_servers.start()
        log("🔄 Auto-update task started", Colors.GREEN)
    
    if not auto_save.is_running():
        auto_save.start()
        log("💾 Auto-save task started", Colors.GREEN)
    
    if not clean_cache.is_running():
        clean_cache.start()
        log("🧹 Cache cleaner started", Colors.GREEN)

# -------------------------------------------------------------------
if __name__ == "__main__":
    health_thread = Thread(target=run_health_server, daemon=True)
    health_thread.start()
    
    try:
        bot.run(TOKEN)
    except Exception as e:
        log(f"❌ خطأ في تشغيل البوت: {e}", Colors.RED)
