import discord
from discord.ext import commands, tasks
from discord import app_commands
from mcstatus import JavaServer
import aiohttp
import json
import asyncio
import os
from dotenv import load_dotenv
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from typing import Optional, Dict
import logging

# ═══════════════════════════════════════════════════════════════════
# 🎯 إعدادات البوت - Niward v1.5
# ═══════════════════════════════════════════════════════════════════
VERSION = "1.5.0"
load_dotenv()
TOKEN = os.getenv("TOKEN")

# إعداد Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('Niward')

# إعدادات البوت
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")

# ملفات البيانات
DATA_FILE = "servers.json"
STATS_FILE = "stats.json"

# Cache النظام
server_cache: Dict[str, dict] = {}
CACHE_DURATION = 30  # ثانية

# ═══════════════════════════════════════════════════════════════════
# 🔧 دوال مساعدة للبيانات
# ═══════════════════════════════════════════════════════════════════
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"خطأ في تحميل البيانات: {e}")
            return {}
    return {}

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"خطأ في حفظ البيانات: {e}")

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
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"خطأ في حفظ الإحصائيات: {e}")

servers_data = load_data()
stats_data = load_stats()

# ═══════════════════════════════════════════════════════════════════
# 🌐 Health Check Server
# ═══════════════════════════════════════════════════════════════════
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(f'Niward Bot v{VERSION} - Online'.encode())
    
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logger.info(f"✅ Health check server running on port {port}")
    server.serve_forever()

# ═══════════════════════════════════════════════════════════════════
# 🎯 نظام الكشف الذكي عن حالة السيرفر
# ═══════════════════════════════════════════════════════════════════
async def check_server_status(ip: str, port: str) -> dict:
    """
    نظام كشف ذكي يميز بين:
    - السيرفر أوفلاين حقيقي
    - السيرفر في وضع Aternos/Standby
    - السيرفر أونلاين مع بيانات اللاعبين
    """
    server_key = f"{ip}:{port}"
    current_time = datetime.now()
    
    # التحقق من الـ Cache
    if server_key in server_cache:
        cached = server_cache[server_key]
        if (current_time - cached['time']).total_seconds() < CACHE_DURATION:
            logger.debug(f"استخدام cache لـ {server_key}")
            return cached['data']
    
    # إعداد الإحصائيات
    if server_key not in stats_data:
        stats_data[server_key] = {
            "total_checks": 0,
            "online_count": 0,
            "offline_count": 0,
            "standby_count": 0,
            "max_players": 0,
            "total_players": 0,
            "last_online": None,
            "last_offline": None,
            "uptime_start": None,
            "longest_uptime": 0,
            "current_uptime": 0,
            "status_changes": []
        }
    
    stats = stats_data[server_key]
    stats["total_checks"] += 1
    
    result = {
        "online": False,
        "players": 0,
        "max_players": 0,
        "latency": 0,
        "reason": "offline",
        "motd": None,
        "favicon": None,
        "player_list": []
    }
    
    # محاولة 1: mcstatus (الأساسية)
    try:
        server = JavaServer.lookup(server_key)
        status = await asyncio.wait_for(
            asyncio.to_thread(server.status),
            timeout=8
        )
        
        players_online = getattr(status.players, "online", 0)
        max_players = getattr(status.players, "max", 0)
        latency = int(getattr(status, "latency", 0))
        motd = str(getattr(status, "description", ""))
        
        # محاولة جلب قائمة اللاعبين
        player_list = []
        if hasattr(status.players, 'sample') and status.players.sample:
            player_list = [p.name for p in status.players.sample[:10]]  # أول 10 لاعبين
        
        # كشف Aternos/Standby
        is_standby = False
        standby_keywords = ["starting", "loading", "preparing", "aternos", "wait"]
        if motd:
            motd_lower = motd.lower()
            is_standby = any(keyword in motd_lower for keyword in standby_keywords)
        
        # تحديث النتيجة
        if is_standby or (players_online == 0 and "aternos" in ip.lower()):
            result.update({
                "online": False,
                "reason": "standby",
                "motd": motd,
                "latency": latency
            })
            stats["standby_count"] += 1
            logger.info(f"🟠 {server_key} في وضع Standby")
        else:
            result.update({
                "online": True,
                "players": players_online,
                "max_players": max_players,
                "latency": latency,
                "motd": motd,
                "player_list": player_list
            })
            stats["online_count"] += 1
            stats["total_players"] += players_online
            stats["max_players"] = max(stats["max_players"], players_online)
            stats["last_online"] = current_time.isoformat()
            
            # حساب Uptime
            if not stats.get("uptime_start"):
                stats["uptime_start"] = current_time.isoformat()
            
            logger.info(f"🟢 {server_key} أونلاين - {players_online}/{max_players} لاعبين")
    
    except asyncio.TimeoutError:
        logger.warning(f"⏱️ Timeout للسيرفر {server_key}")
        result["reason"] = "timeout"
        stats["offline_count"] += 1
    
    except Exception as e:
        logger.warning(f"⚠️ mcstatus فشل لـ {server_key}: {str(e)[:50]}")
        
        # محاولة 2: API بديل
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://api.mcsrvstat.us/3/{ip}:{port}",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if data.get("online"):
                            players = data.get("players", {})
                            result.update({
                                "online": True,
                                "players": players.get("online", 0),
                                "max_players": players.get("max", 0),
                                "motd": data.get("motd", {}).get("clean", [""])[0] if data.get("motd") else None
                            })
                            stats["online_count"] += 1
                            logger.info(f"🟢 {server_key} أونلاين (API backup)")
                        else:
                            stats["offline_count"] += 1
                            logger.info(f"🔴 {server_key} أوفلاين (API backup)")
        except Exception as e2:
            logger.error(f"❌ API backup فشل لـ {server_key}: {e2}")
            stats["offline_count"] += 1
    
    # تحديث آخر حالة أوفلاين
    if not result["online"]:
        stats["last_offline"] = current_time.isoformat()
        
        # حساب أطول uptime
        if stats.get("uptime_start"):
            uptime_duration = (current_time - datetime.fromisoformat(stats["uptime_start"])).total_seconds()
            stats["longest_uptime"] = max(stats["longest_uptime"], uptime_duration)
            stats["uptime_start"] = None
    
    # حفظ في الـ Cache
    server_cache[server_key] = {
        'time': current_time,
        'data': result
    }
    
    save_stats(stats_data)
    return result

# ═══════════════════════════════════════════════════════════════════
# 🎨 أنماط التصميم للرسائل
# ═══════════════════════════════════════════════════════════════════
STYLES = {
    "classic": {
        "name": "🎮 كلاسيكي",
        "colors": {"online": 0x00ff00, "offline": 0xff0000, "standby": 0xffa500},
        "emojis": {"online": "🟢", "offline": "🔴", "standby": "🟠"}
    },
    "modern": {
        "name": "⚡ عصري",
        "colors": {"online": 0x2ecc71, "offline": 0xe74c3c, "standby": 0xf39c12},
        "emojis": {"online": "✨", "offline": "💤", "standby": "⏳"}
    },
    "dark": {
        "name": "👾 داكن",
        "colors": {"online": 0x1abc9c, "offline": 0x95a5a6, "standby": 0xe67e22},
        "emojis": {"online": "🌟", "offline": "🌑", "standby": "🌘"}
    }
}

def build_embed(user_data: dict, status_info: dict) -> discord.Embed:
    """بناء Embed مخصص حسب ستايل المستخدم"""
    ip = user_data["ip"]
    port = user_data["port"]
    version = user_data.get("version", "غير محددة")
    board = user_data.get("board", "Vanilla Survival")
    style = user_data.get("style", "classic")
    
    style_config = STYLES.get(style, STYLES["classic"])
    
    # تحديد الحالة
    if status_info.get("online"):
        state = "online"
        title = f"{style_config['emojis']['online']} السيرفر أونلاين"
        desc = (
            f"**IP:** `{ip}`\n"
            f"**Port:** `{port}`\n"
            f"**Version:** {version}\n"
            f"**Players:** {status_info['players']}/{status_info.get('max_players', 0)}\n"
            f"**Ping:** {status_info['latency']}ms"
        )
        
        # إضافة قائمة اللاعبين
        if status_info.get("player_list"):
            players_str = ", ".join(status_info["player_list"][:5])
            desc += f"\n**Online:** {players_str}"
            if len(status_info["player_list"]) > 5:
                desc += f" +{len(status_info['player_list']) - 5} آخرين"
    
    elif status_info.get("reason") == "standby":
        state = "standby"
        title = f"{style_config['emojis']['standby']} السيرفر في وضع الاستعداد"
        desc = (
            f"**IP:** `{ip}`\n"
            f"**Port:** `{port}`\n"
            f"**Version:** {version}\n"
            f"⏳ السيرفر يستيقظ... قد يستغرق دقيقة"
        )
    else:
        state = "offline"
        title = f"{style_config['emojis']['offline']} السيرفر أوفلاين"
        desc = (
            f"**IP:** `{ip}`\n"
            f"**Port:** `{port}`\n"
            f"**Version:** {version}"
        )
    
    embed = discord.Embed(
        title=f"🎮 {board} — {title}",
        description=desc,
        color=style_config["colors"][state]
    )
    
    # الصور المخصصة
    if user_data.get("thumbnail_url"):
        embed.set_thumbnail(url=user_data["thumbnail_url"])
    if user_data.get("image_url"):
        embed.set_image(url=user_data["image_url"])
    
    footer_text = user_data.get("custom_footer", f"Niward v{VERSION} — آخر تحديث")
    embed.set_footer(text=footer_text)
    embed.timestamp = datetime.now()
    
    return embed

# ═══════════════════════════════════════════════════════════════════
# 🔔 نظام التنبيهات الذكي
# ═══════════════════════════════════════════════════════════════════
async def send_status_notification(user_id: str, old_status: bool, new_status: bool, server_key: str):
    """إرسال إشعار عند تغيير حالة السيرفر"""
    user_data = servers_data.get(user_id)
    if not user_data:
        return
    
    alert_channel_id = user_data.get("alert_channel_id")
    alert_role = user_data.get("alert_role")
    
    if not alert_channel_id:
        return
    
    channel = bot.get_channel(alert_channel_id)
    if not channel:
        return
    
    # تجنب الإشعارات المتكررة
    if old_status == new_status:
        return
    
    # بناء الإشعار
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if new_status:
        embed = discord.Embed(
            title="🟢 السيرفر الآن أونلاين!",
            description=f"**السيرفر:** `{server_key}`\n**الوقت:** {timestamp}",
            color=0x00ff00
        )
        embed.set_footer(text="Niward Alert System")
    else:
        embed = discord.Embed(
            title="🔴 السيرفر الآن أوفلاين",
            description=f"**السيرفر:** `{server_key}`\n**الوقت:** {timestamp}",
            color=0xff0000
        )
        embed.set_footer(text="Niward Alert System")
    
    # إضافة منشن للرول
    content = f"<@&{alert_role}>" if alert_role else None
    
    try:
        await channel.send(content=content, embed=embed)
        logger.info(f"📣 تم إرسال إشعار لـ {user_id} - {server_key}")
    except Exception as e:
        logger.error(f"خطأ في إرسال الإشعار: {e}")

# ═══════════════════════════════════════════════════════════════════
# 📝 الأوامر - Commands
# ═══════════════════════════════════════════════════════════════════

@bot.tree.command(name="إعداد_تلقائي", description="إعداد السيرفر بشكل تلقائي وسريع")
@app_commands.describe(
    address="IP:Port مثال: play.server.com:25565",
    channel="القناة المخصصة للرسالة المثبتة",
    version="نوع النسخة المدعومة"
)
@app_commands.choices(version=[
    app_commands.Choice(name="جافا", value="جافا"),
    app_commands.Choice(name="بيدروك", value="بيدروك"),
    app_commands.Choice(name="كلاهما", value="كلاهما")
])
async def إعداد_تلقائي(
    interaction: discord.Interaction,
    address: str,
    channel: discord.TextChannel,
    version: app_commands.Choice[str]
):
    """إعداد كامل في أمر واحد"""
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
    
    await interaction.response.defer(ephemeral=True)
    
    user_id = str(interaction.user.id)
    
    # حفظ البيانات
    servers_data[user_id] = {
        "ip": ip,
        "port": port,
        "version": version.value,
        "board": "Vanilla Survival",
        "channel_id": channel.id,
        "style": "classic",
        "last_status": None
    }
    save_data(servers_data)
    
    # فحص السيرفر
    status = await check_server_status(ip, port)
    embed = build_embed(servers_data[user_id], status)
    view = JoinButton(ip, port)
    
    try:
        sent = await channel.send(embed=embed, view=view)
        await sent.pin()
        servers_data[user_id]["message_id"] = sent.id
        servers_data[user_id]["last_status"] = status.get("online", False)
        save_data(servers_data)
        
        await interaction.followup.send(
            f"✅ تم الإعداد بنجاح!\n"
            f"• السيرفر: `{ip}:{port}`\n"
            f"• النسخة: {version.value}\n"
            f"• القناة: {channel.mention}\n"
            f"• الحالة: {'🟢 أونلاين' if status.get('online') else '🔴 أوفلاين'}",
            ephemeral=True
        )
        logger.info(f"✅ {interaction.user} أكمل الإعداد التلقائي لـ {ip}:{port}")
    
    except discord.Forbidden:
        await interaction.followup.send(
            "⚠️ لا أملك صلاحية كافية في هذه القناة.",
            ephemeral=True
        )
    except Exception as e:
        await interaction.followup.send(f"❌ حدث خطأ: {e}", ephemeral=True)
        logger.error(f"خطأ في الإعداد التلقائي: {e}")

# ═══════════════════════════════════════════════════════════════════

@bot.tree.command(name="تخصيص_الرسالة", description="تخصيص ستايل الرسالة المثبتة")
@app_commands.choices(style=[
    app_commands.Choice(name="🎮 كلاسيكي", value="classic"),
    app_commands.Choice(name="⚡ عصري", value="modern"),
    app_commands.Choice(name="👾 داكن", value="dark")
])
async def تخصيص_الرسالة(interaction: discord.Interaction, style: app_commands.Choice[str]):
    user_id = str(interaction.user.id)
    if user_id not in servers_data:
        await interaction.response.send_message(
            "❌ لم يتم تحديد سيرفر بعد! استخدم `/إعداد_تلقائي` أولاً.",
            ephemeral=True
        )
        return
    
    servers_data[user_id]["style"] = style.value
    save_data(servers_data)
    
    await interaction.response.send_message(
        f"✅ تم تحديث الستايل إلى: **{STYLES[style.value]['name']}**",
        ephemeral=True
    )
    logger.info(f"{interaction.user} غيّر الستايل إلى {style.value}")

# ═══════════════════════════════════════════════════════════════════

@bot.tree.command(name="احصائيات_السيرفر", description="عرض إحصائيات متقدمة للسيرفر")
async def احصائيات_السيرفر(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if user_id not in servers_data:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر بعد!", ephemeral=True)
        return
    
    ip = servers_data[user_id]["ip"]
    port = servers_data[user_id]["port"]
    server_key = f"{ip}:{port}"
    
    if server_key not in stats_data:
        await interaction.response.send_message("❌ لا توجد إحصائيات لهذا السيرفر بعد!", ephemeral=True)
        return
    
    stats = stats_data[server_key]
    
    # حساب المعدلات
    total = stats["total_checks"]
    online_pct = round((stats["online_count"] / total * 100), 1) if total > 0 else 0
    avg_players = round(stats["total_players"] / stats["online_count"], 1) if stats["online_count"] > 0 else 0
    
    # حساب أطول uptime
    longest_uptime_str = "لا يوجد"
    if stats.get("longest_uptime"):
        hours = int(stats["longest_uptime"] // 3600)
        minutes = int((stats["longest_uptime"] % 3600) // 60)
        longest_uptime_str = f"{hours}س {minutes}د"
    
    # حساب uptime الحالي
    current_uptime_str = "غير متصل"
    if stats.get("uptime_start"):
        uptime_duration = (datetime.now() - datetime.fromisoformat(stats["uptime_start"])).total_seconds()
        hours = int(uptime_duration // 3600)
        minutes = int((uptime_duration % 3600) // 60)
        current_uptime_str = f"{hours}س {minutes}د"
    
    embed = discord.Embed(
        title=f"📊 إحصائيات السيرفر",
        description=f"**السيرفر:** `{server_key}`",
        color=0x3498db
    )
    
    embed.add_field(name="🔍 إجمالي الفحوصات", value=f"`{total:,}`", inline=True)
    embed.add_field(name="🟢 مرات الأونلاين", value=f"`{stats['online_count']:,}`", inline=True)
    embed.add_field(name="🔴 مرات الأوفلاين", value=f"`{stats['offline_count']:,}`", inline=True)
    
    embed.add_field(name="⏱️ نسبة التشغيل", value=f"`{online_pct}%`", inline=True)
    embed.add_field(name="👥 أعلى لاعبين", value=f"`{stats['max_players']}`", inline=True)
    embed.add_field(name="📈 متوسط اللاعبين", value=f"`{avg_players}`", inline=True)
    
    embed.add_field(name="🏆 أطول تشغيل متواصل", value=f"`{longest_uptime_str}`", inline=True)
    embed.add_field(name="⏰ التشغيل الحالي", value=f"`{current_uptime_str}`", inline=True)
    embed.add_field(name="🟠 Standby", value=f"`{stats.get('standby_count', 0)}`", inline=True)
    
    if stats.get("last_online"):
        last_online = datetime.fromisoformat(stats["last_online"]).strftime("%Y-%m-%d %H:%M")
        embed.add_field(name="🕐 آخر أونلاين", value=f"`{last_online}`", inline=False)
    
    embed.set_footer(text=f"Niward v{VERSION} Statistics")
    embed.timestamp = datetime.now()
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ═══════════════════════════════════════════════════════════════════

@bot.tree.command(name="تفعيل_تنبيهات", description="تفعيل التنبيهات عند تغيير حالة السيرفر")
@app_commands.describe(
    channel="القناة التي سترسل فيها الإشعارات",
    role="الرول الذي سيتم منشنته (اختياري)"
)
async def تفعيل_تنبيهات(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    role: Optional[discord.Role] = None
):
    user_id = str(interaction.user.id)
    if user_id not in servers_data:
        await interaction.response.send_message(
            "❌ لم يتم تحديد سيرفر بعد!",
            ephemeral=True
        )
        return
    
    servers_data[user_id]["alert_channel_id"] = channel.id
    servers_data[user_id]["alert_role"] = role.id if role else None
    save_data(servers_data)
    
    msg = f"✅ تم تفعيل التنبيهات في {channel.mention}"
    if role:
        msg += f"\n• سيتم منشنة {role.mention} عند كل تغيير"
    
    await interaction.response.send_message(msg, ephemeral=True)
    logger.info(f"{interaction.user} فعّل التنبيهات في {channel.name}")

# ═══════════════════════════════════════════════════════════════════

@bot.tree.command(name="تعطيل_تنبيهات", description="تعطيل نظام التنبيهات")
async def تعطيل_تنبيهات(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if user_id not in servers_data:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر!", ephemeral=True)
        return
    
    servers_data[user_id]["alert_channel_id"] = None
    servers_data[user_id]["alert_role"] = None
    save_data(servers_data)
    
    await interaction.response.send_message("✅ تم تعطيل التنبيهات", ephemeral=True)

# ═══════════════════════════════════════════════════════════════════

@bot.tree.command(name="مساعدة", description="عرض جميع الأوامر المتاحة")
async def مساعدة(interaction: discord.Interaction):
    embed = discord.Embed(
        title=f"📚 دليل أوامر Niward v{VERSION}",
        description="جميع الأوامر المتاحة لإدارة سيرفر Minecraft",
        color=0x9b59b6
    )
    
    embed.add_field(
        name="🚀 الإعداد السريع",
        value=(
            "**`/إعداد_تلقائي`** - إعداد كامل في أمر واحد\n"
            "يشمل: IP، النسخة، القناة، والرسالة المثبتة"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🎨 التخصيص",
        value=(
            "**`/تخصيص_الرسالة`** - اختيار ستايل العرض (كلاسيكي/عصري/داكن)\n"
            "**`/تعيين_صورة`** - إضافة صور مخصصة\n"
            "**`/تعيين_بورد`** - تخصيص اسم البورد\n"
            "**`/تخصيص_فوتر`** - تخصيص نص الفوتر"
        ),
        inline=False
    )
    
    embed.add_field(
        name="📊 الإحصائيات",
        value=(
            "**`/احصائيات_السيرفر`** - عرض إحصائيات متقدمة\n"
            "يشمل: Uptime، عدد اللاعبين، نسبة التشغيل"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🔔 التنبيهات",
        value=(
            "**`/تفعيل_تنبيهات`** - تفعيل الإشعارات عند تغيير الحالة\n"
            "**`/تعطيل_تنبيهات`** - إيقاف التنبيهات"
        ),
        inline=False
    )
    
    embed.add_field(
        name="⚙️ الإدارة",
        value=(
            "**`/معلومات`** - عرض معلومات السيرفر المحفوظة\n"
            "**`/حذف`** - حذف السيرفر وجميع بياناته\n"
            "**`/حذف_صورة`** - حذف الصور المخصصة"
        ),
        inline=False
    )
    
    embed.set_footer(text=f"Niward v{VERSION} by MTPS")
    embed.timestamp = datetime.now()
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ═══════════════════════════════════════════════════════════════════
# الأوامر المتبقية (محدّثة للنظام الجديد)
# ═══════════════════════════════════════════════════════════════════

@bot.tree.command(name="تعيين_صورة", description="إضافة صورة مخصصة للرسالة")
@app_commands.describe(
    image_url="رابط الصورة الكبيرة",
    thumbnail_url="رابط الصورة الصغيرة"
)
async def تعيين_صورة(interaction: discord.Interaction, image_url: str = None, thumbnail_url: str = None):
    user_id = str(interaction.user.id)
    if user_id not in servers_data:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر بعد!", ephemeral=True)
        return
    
    if image_url:
        servers_data[user_id]["image_url"] = image_url
    if thumbnail_url:
        servers_data[user_id]["thumbnail_url"] = thumbnail_url
    
    save_data(servers_data)
    await interaction.response.send_message("✅ تم تحديث الصور!", ephemeral=True)

@bot.tree.command(name="حذف_صورة", description="حذف الصور المخصصة")
async def حذف_صورة(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if user_id not in servers_data:
        await interaction.response.send_message("❌ لا يوجد سيرفر محفوظ!", ephemeral=True)
        return
    
    servers_data[user_id]["image_url"] = None
    servers_data[user_id]["thumbnail_url"] = None
    save_data(servers_data)
    await interaction.response.send_message("✅ تم حذف الصور!", ephemeral=True)

@bot.tree.command(name="تعيين_بورد", description="تخصيص اسم البورد")
@app_commands.describe(board_name="اسم البورد الجديد")
async def تعيين_بورد(interaction: discord.Interaction, board_name: str):
    user_id = str(interaction.user.id)
    if user_id not in servers_data:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر بعد!", ephemeral=True)
        return
    
    servers_data[user_id]["board"] = board_name
    save_data(servers_data)
    await interaction.response.send_message(f"✅ تم تحديث البورد إلى: **{board_name}**", ephemeral=True)

@bot.tree.command(name="تخصيص_فوتر", description="تخصيص نص الفوتر")
@app_commands.describe(footer_text="النص الجديد")
async def تخصيص_فوتر(interaction: discord.Interaction, footer_text: str):
    user_id = str(interaction.user.id)
    if user_id not in servers_data:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر بعد!", ephemeral=True)
        return
    
    servers_data[user_id]["custom_footer"] = footer_text
    save_data(servers_data)
    await interaction.response.send_message(f"✅ تم تحديث الفوتر!", ephemeral=True)

@bot.tree.command(name="معلومات", description="عرض معلومات السيرفر المحفوظة")
async def معلومات(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if user_id not in servers_data:
        await interaction.response.send_message("❌ لم يتم تحديد سيرفر!", ephemeral=True)
        return
    
    info = servers_data[user_id]
    embed = discord.Embed(title="📋 معلومات السيرفر", color=0x9b59b6)
    
    embed.add_field(name="🌐 IP", value=f"`{info['ip']}`", inline=True)
    embed.add_field(name="🔌 Port", value=f"`{info['port']}`", inline=True)
    embed.add_field(name="📦 Version", value=info.get("version", "غير محددة"), inline=True)
    embed.add_field(name="📌 Board", value=info.get("board", "Vanilla Survival"), inline=True)
    embed.add_field(name="🎨 Style", value=STYLES[info.get("style", "classic")]["name"], inline=True)
    
    channel_id = info.get("channel_id")
    if channel_id:
        embed.add_field(name="📺 القناة", value=f"<#{channel_id}>", inline=True)
    
    alert_channel = info.get("alert_channel_id")
    if alert_channel:
        embed.add_field(name="🔔 قناة التنبيهات", value=f"<#{alert_channel}>", inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="حذف", description="حذف السيرفر وجميع بياناته")
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
    await interaction.response.send_message("✅ تم حذف السيرفر وجميع بياناته!", ephemeral=True)
    logger.info(f"{interaction.user} حذف سيرفره")

# ═══════════════════════════════════════════════════════════════════
# زر الانضمام
# ═══════════════════════════════════════════════════════════════════
class JoinButton(discord.ui.View):
    def __init__(self, ip, port):
        super().__init__(timeout=None)
        self.ip = ip
        self.port = port

    @discord.ui.button(label="انضمام", style=discord.ButtonStyle.green, custom_id="join_server_btn")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            board = "Vanilla Survival"
            for user_id, info in servers_data.items():
                if info.get("ip") == self.ip and info.get("port") == self.port:
                    board = info.get("board", "Vanilla Survival")
                    break
            
            await interaction.user.send(f"📌 Board: {board}\n🌐 IP: {self.ip}\n🔌 Port: {self.port}")
            await interaction.response.send_message("📩 تم إرسال المعلومات إلى الخاص!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("⚠️ لا أستطيع إرسال رسالة خاصة!", ephemeral=True)

# ═══════════════════════════════════════════════════════════════════
# 🔄 نظام التحديث التلقائي
# ═══════════════════════════════════════════════════════════════════
@tasks.loop(minutes=1)
async def update_servers():
    await bot.wait_until_ready()
    
    for user_id, info in list(servers_data.items()):
        try:
            ip = info.get("ip")
            port = info.get("port")
            channel_id = info.get("channel_id")
            message_id = info.get("message_id")

            if not all([ip, port, channel_id]):
                continue

            channel = bot.get_channel(channel_id)
            if not channel:
                continue

            # فحص الحالة
            status = await check_server_status(ip, port)
            current_status = status.get("online", False)
            last_status = info.get("last_status")
            
            # إرسال إشعار عند تغيير الحالة
            if last_status is not None and last_status != current_status:
                await send_status_notification(user_id, last_status, current_status, f"{ip}:{port}")
            
            # تحديث الحالة
            servers_data[user_id]["last_status"] = current_status
            save_data(servers_data)
            
            # بناء الرسالة
            embed = build_embed(info, status)
            view = JoinButton(ip, port)

            # تحديث الرسالة
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
                    logger.error(f"خطأ في تحديث الرسالة: {e}")
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
            logger.error(f"خطأ في تحديث {info.get('ip')}: {e}")

# ═══════════════════════════════════════════════════════════════════
# 🎯 حدث البدء
# ═══════════════════════════════════════════════════════════════════
@bot.event
async def on_ready():
    logger.info(f"✅ {bot.user} is online!")
    logger.info(f"📊 Version: {VERSION}")
    logger.info(f"📦 Servers in database: {len(servers_data)}")
    
    try:
        synced = await bot.tree.sync()
        logger.info(f"🔁 Synced {len(synced)} command(s)")
    except Exception as e:
        logger.error(f"❌ Error syncing commands: {e}")

    bot.add_view(JoinButton("", ""))

    if not update_servers.is_running():
        update_servers.start()
        logger.info("🔄 Auto-update task started")

# ═══════════════════════════════════════════════════════════════════
# 🚀 تشغيل البوت
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    health_thread = Thread(target=run_health_server, daemon=True)
    health_thread.start()
    
    try:
        bot.run(TOKEN)
    except Exception as e:
        logger.critical(f"❌ خطأ حرج في تشغيل البوت: {e}")
