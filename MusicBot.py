# Importing libraries and modules
from flask import Flask
from threading import Thread
import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import yt_dlp
from collections import deque
import asyncio
import tempfile

# Flask setup for uptime
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Song queues
SONG_QUEUES = {}

# Async search wrapper
async def search_ytdlp_async(query, ydl_opts, use_cookies: bool = True):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _extract(query, ydl_opts, use_cookies))

def _extract(query, ydl_opts, use_cookies: bool = True):
    cookie_path = None
    if use_cookies:
        cookie_content = os.getenv("YT_COOKIES")
        if not cookie_content:
            raise Exception("YT_COOKIES not set, cannot use cookies for YouTube.")
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            f.write(cookie_content)
            cookie_path = f.name
        ydl_opts["cookiefile"] = cookie_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(query, download=False)
    finally:
        if cookie_path and os.path.exists(cookie_path):
            os.remove(cookie_path)

# Discord intents
intents = discord.Intents.default()
intents.message_content = True

# Bot setup
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} снова тут")

# Skip
@bot.tree.command(name="skip", description="Пропускает текущую песню")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        await interaction.response.send_message(
            "Штаб Charlie squad: ретрансляция переключена. Частота скорректирована, сигнал перенаправлен."
        )
    else:
        await interaction.response.send_message("Штаб: эфир пуст, переключение не требуется.")

# Pause
@bot.tree.command(name="pause", description="Ставит на паузу")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc:
        return await interaction.response.send_message("Штаб: сигнал отсутствует, линии связи не задействованы.")
    if not vc.is_playing():
        return await interaction.response.send_message("Штаб: ретрансляция неактивна, пауза невозможна.")
    vc.pause()
    await interaction.response.send_message(
        "Штаб: частоты временно заморожены, передача данных приостановлена."
    )

# Resume
@bot.tree.command(name="resume", description="Продолжим")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc:
        return await interaction.response.send_message("Штаб: сигнал ещё не восстановлен, линии молчат.")
    if not vc.is_paused():
        return await interaction.response.send_message("Штаб: ретрансляция и так активна, восстановление не требуется.")
    vc.resume()
    await interaction.response.send_message(
        "Штаб Charlie squad: передача данных восстановлена, резервные линии задействованы."
    )

# Stop
@bot.tree.command(name="stop", description="Остановить все и очистить очередь")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc or not vc.is_connected():
        return await interaction.response.send_message("Штаб: нет активного подключения, остановка не требуется.")

    gid = str(interaction.guild_id)
    if gid in SONG_QUEUES:
        SONG_QUEUES[gid].clear()

    if vc.is_playing() or vc.is_paused():
        vc.stop()
    await vc.disconnect()
    await interaction.response.send_message(
        "Штаб: ретрансляция завершена, частоты очищены, контрольные точки сняты."
    )

# Play
@bot.tree.command(name="play", description="Запустить песню или добавить в очередь")
@app_commands.describe(song_query="Search query")
async def play(interaction: discord.Interaction, song_query: str):
    await interaction.response.defer()
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.followup.send("Штаб: вы не подключены к ретрансляционной вышке. Доступ к частотам невозможен.")
        return

    voice_channel = interaction.user.voice.channel
    vc = interaction.guild.voice_client
    if not vc:
        vc = await voice_channel.connect()
    elif voice_channel != vc.channel:
        await vc.move_to(voice_channel)

    # YouTube search
    ydl_opts_yt = {
        "format": "bestaudio[abr<=96]/bestaudio",
        "noplaylist": True,
        "youtube_include_dash_manifest": False,
        "youtube_include_hls_manifest": False,
        "quiet": True,
        "no_warnings": True,
    }

    yt_query = f"ytsearch1:{song_query}"
    tracks = []
    try:
        results = await search_ytdlp_async(yt_query, dict(ydl_opts_yt), use_cookies=True)
        tracks = results.get("entries") or []
        if not tracks:
            raise Exception("No YouTube entries")
    except Exception as e:
        print(f"YT-DLP (YouTube) failed: {e}")
        # SoundCloud fallback
        ydl_opts_sc = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",  # важно для SoundCloud
        }
        sc_query = f"scsearch1:{song_query}"  # без пробела
        try:
            results = await search_ytdlp_async(sc_query, dict(ydl_opts_sc), use_cookies=False)
            tracks = results.get("entries") or []
            if not tracks:
                await interaction.followup.send("Штаб: сигнал не обнаружен, канал связи пуст.")
                return
        except Exception as e2:
            print(f"YT-DLP (SoundCloud) failed: {e2}")
            await interaction.followup.send("Штаб: каналы заблокированы, доступ к частоте невозможен.")
            return

    # Use first track
    first = tracks[0]
    audio_url = first.get("url") or first.get("webpage_url")
    title = first.get("title", "Untitled")

    gid = str(interaction.guild_id)
    if gid not in SONG_QUEUES:
        SONG_QUEUES[gid] = deque()
    SONG_QUEUES[gid].append((audio_url, title))

    if vc.is_playing() or vc.is_paused():
        await interaction.followup.send(f"Штаб: сигнал **{title}** зафиксирован и добавлен в очередь ретрансляции.")
    else:
        await interaction.followup.send(f"Штаб Charlie squad активировал ретрансляцию: **{title}**. Каналы проверены, контрольные точки выставлены.")
        await play_next_song(vc, gid, interaction.channel)

# Play next
async def play_next_song(vc, gid, channel):
    if SONG_QUEUES[gid]:
        audio_url, title = SONG_QUEUES[gid].popleft()
        ffmpeg_opts = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn -c:a libopus -b:a 96k",
        }
        source = discord.FFmpegOpusAudio(audio_url, **ffmpeg_opts)

        def after_play(err):
            if err:
                print(f"ОШИБКА {title}: {err}")
            asyncio.run_coroutine_threadsafe(play_next_song(vc, gid, channel), bot.loop)

        vc.play(source, after=after_play)
        asyncio.create_task(channel.send(f"Штаб: сигнал в эфире — **{title}**. Передача данных шифрована, резервные линии наготове."))
    else:
        await channel.send("Штаб Charlie squad: ретрансляция завершена, все узлы находятся под мониторингом, линии очищены.")
        SONG_QUEUES[gid] = deque()

# Run the bot
bot.run(TOKEN)
