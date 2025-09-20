# Import libraries
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
import shlex

# Flask setup
app = Flask('')
@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run_flask).start()

# Load environment
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Queues
SONG_QUEUES = {}

# Async wrapper for yt-dlp
async def search_ytdlp_async(query, ydl_opts, use_cookies=True):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _extract(query, ydl_opts, use_cookies))

def _extract(query, ydl_opts, use_cookies=True):
    cookie_path = None
    if use_cookies:
        cookie_content = os.getenv("YT_COOKIES")
        if cookie_content:
            with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
                f.write(cookie_content)
                cookie_path = f.name
            ydl_opts["cookiefile"] = cookie_path
    try:
        print(f"[yt-dlp] Extracting info: {query}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(query, download=False)
        print(f"[yt-dlp] Extraction done: {result.get('title', 'Unknown')}")
        return result
    finally:
        if cookie_path and os.path.exists(cookie_path):
            os.remove(cookie_path)

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"[Bot] {bot.user} ready")

# =======================
# Voice Control Commands
# =======================
async def get_vc(interaction):
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.followup.send("[Voice] Вы не подключены к каналу")
        return None
    vc = interaction.guild.voice_client
    if not vc:
        vc = await interaction.user.voice.channel.connect()
    elif vc.channel != interaction.user.voice.channel:
        await vc.move_to(interaction.user.voice.channel)
    return vc

@bot.tree.command(name="skip", description="Пропустить текущую песню")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        await interaction.response.send_message("[Skip] Сигнал переключен")
    else:
        await interaction.response.send_message("[Skip] Эфир пуст")

@bot.tree.command(name="pause", description="Пауза")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc or not vc.is_playing():
        await interaction.response.send_message("[Pause] Нет активного сигнала")
        return
    vc.pause()
    await interaction.response.send_message("[Pause] Сигнал приостановлен")

@bot.tree.command(name="resume", description="Возобновить")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc or not vc.is_paused():
        await interaction.response.send_message("[Resume] Нет сигнала для возобновления")
        return
    vc.resume()
    await interaction.response.send_message("[Resume] Сигнал возобновлен")

@bot.tree.command(name="stop", description="Остановить и очистить очередь")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    gid = str(interaction.guild_id)
    if gid in SONG_QUEUES:
        SONG_QUEUES[gid].clear()
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        await vc.disconnect()
    await interaction.response.send_message("[Stop] Сигнал остановлен, очередь очищена")

# =======================
# Play Command
# =======================
@bot.tree.command(name="play", description="Воспроизвести трек")
@app_commands.describe(song_query="Ссылка или название трека")
async def play(interaction: discord.Interaction, song_query: str):
    await interaction.response.defer()
    vc = await get_vc(interaction)
    if not vc:
        return

    gid = str(interaction.guild_id)
    if gid not in SONG_QUEUES:
        SONG_QUEUES[gid] = deque()

    tracks, source_name = [], ""

    try:
        if song_query.startswith("http"):
            ydl_opts = {"format": "bestaudio/best", "noplaylist": True, "quiet": True}
            result = await search_ytdlp_async(song_query, ydl_opts, use_cookies=False)
            tracks = result.get("entries") or [result]
            source_name = result.get("extractor_key", "Unknown")
        else:
            # YouTube search
            ydl_opts = {"format": "bestaudio[abr<=96]/bestaudio", "noplaylist": True, "quiet": True}
            result = await search_ytdlp_async(f"ytsearch1:{song_query}", ydl_opts, use_cookies=False)
            tracks = result.get("entries", [])
            source_name = "YouTube"
            if not tracks:
                # Bandcamp search
                ydl_opts = {"format": "bestaudio/best", "noplaylist": True, "quiet": True}
                result = await search_ytdlp_async(f"bandcampsearch1:{song_query}", ydl_opts, use_cookies=False)
                tracks = result.get("entries", [])
                source_name = "Bandcamp"
        if not tracks:
            await interaction.followup.send("[Play] Трек не найден")
            return
    except Exception as e:
        print(f"[Play] Ошибка поиска: {e}")
        await interaction.followup.send("[Play] Ошибка поиска")
        return

    # Подготовка к воспроизведению
    first = tracks[0]
    url = first.get("webpage_url") or first.get("url")
    title = first.get("title", "Untitled")
    SONG_QUEUES[gid].append((url, title, source_name))
    print(f"[Queue] Добавлен трек: {title} ({source_name})")

    if not vc.is_playing() and not vc.is_paused():
        await play_next_song(vc, gid, interaction.channel)
        await interaction.followup.send(f"[Play] Воспроизведение: {title} ({source_name})")
    else:
        await interaction.followup.send(f"[Queue] {title} ({source_name}) добавлен в очередь")

# =======================
# Play Next Track
# =======================
async def play_next_song(vc, gid, channel):
    if not SONG_QUEUES[gid]:
        await channel.send("[Queue] Очередь завершена")
        return

    url, title, source_name = SONG_QUEUES[gid].popleft()
    print(f"[PlayNext] Воспроизведение: {title} ({source_name})")

    ffmpeg_opts = {"before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5", "options": "-vn"}

    try:
        if "bandcamp.com" in url:
            # Для Bandcamp скачиваем временный файл
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
                tmp_path = tmp_file.name
            ydl_opts = {"format": "bestaudio/best", "outtmpl": tmp_path, "quiet": True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                print(f"[Download] Bandcamp: {title}")
                ydl.download([url])
            source = discord.FFmpegOpusAudio(tmp_path)
            def cleanup(err):
                try:
                    os.remove(tmp_path)
                except: pass
                asyncio.run_coroutine_threadsafe(play_next_song(vc, gid, channel), bot.loop)
            vc.play(source, after=cleanup)
            await channel.send(f"[Now Playing] {title} ({source_name})")
            return
        else:
            # YouTube или поток
            source = discord.FFmpegOpusAudio(url, **ffmpeg_opts)
            def after_play(err):
                if err:
                    print(f"[FFmpeg] Ошибка: {title} ({err})")
                asyncio.run_coroutine_threadsafe(play_next_song(vc, gid, channel), bot.loop)
            vc.play(source, after=after_play)
            await channel.send(f"[Now Playing] {title} ({source_name})")
    except Exception as e:
        print(f"[FFmpeg] Ошибка воспроизведения: {title} ({e})")
        await play_next_song(vc, gid, channel)

# =======================
# Run Bot
# =======================
bot.run(TOKEN)
