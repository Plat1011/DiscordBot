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
import shlex

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

def _extract(query, ydl_opts, use_cookies: bool = True):
    cookie_path = None
    if use_cookies:
        cookie_content = os.getenv("YT_COOKIES")
        if cookie_content:
            with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
                f.write(cookie_content)
                cookie_path = f.name
            ydl_opts["cookiefile"] = cookie_path

    try:
        print(f"[yt-dlp] Extracting info for: {query}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(query, download=False)
        print(f"[yt-dlp] Extraction done: {result.get('title', 'Unknown')}")
        return result
    finally:
        if cookie_path and os.path.exists(cookie_path):
            os.remove(cookie_path)


# Async search wrapper
async def search_ytdlp_async(query, ydl_opts, use_cookies: bool = True):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _extract(query, ydl_opts, use_cookies))


# Discord intents
intents = discord.Intents.default()
intents.message_content = True

# Bot setup
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"[Bot] {bot.user} v1.6")

# Helper commands: skip, pause, resume, stop
@bot.tree.command(name="skip", description="Пропускает текущую песню")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        await interaction.response.send_message("[Skip] Сигнал переключен.")
    else:
        await interaction.response.send_message("[Skip] Эфир пуст.")

@bot.tree.command(name="pause", description="Ставит на паузу")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc:
        return await interaction.response.send_message("[Pause] Нет активного сигнала.")
    if not vc.is_playing():
        return await interaction.response.send_message("[Pause] Сигнал уже неактивен.")
    vc.pause()
    await interaction.response.send_message("[Pause] Сигнал приостановлен.")

@bot.tree.command(name="resume", description="Продолжить")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc:
        return await interaction.response.send_message("[Resume] Сигнал не восстановлен.")
    if not vc.is_paused():
        return await interaction.response.send_message("[Resume] Сигнал уже активен.")
    vc.resume()
    await interaction.response.send_message("[Resume] Сигнал восстановлен.")

@bot.tree.command(name="stop", description="Остановить все и очистить очередь")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc or not vc.is_connected():
        return await interaction.response.send_message("[Stop] Нет активного подключения.")
    gid = str(interaction.guild_id)
    if gid in SONG_QUEUES:
        SONG_QUEUES[gid].clear()
    if vc.is_playing() or vc.is_paused():
        vc.stop()
    await vc.disconnect()
    await interaction.response.send_message("[Stop] Сигнал остановлен, очередь очищена.")

# Play command
@bot.tree.command(name="play", description="Запустить песню или добавить в очередь")
@app_commands.describe(song_query="Search query")
async def play(interaction: discord.Interaction, song_query: str):
    await interaction.response.defer()
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.followup.send("[Play] Вы не подключены к голосовому каналу.")
        return

    voice_channel = interaction.user.voice.channel
    vc = interaction.guild.voice_client
    if not vc:
        vc = await voice_channel.connect()
    elif voice_channel != vc.channel:
        await vc.move_to(voice_channel)

    tracks = []
    source_name = ""

    is_url = song_query.startswith(('http://', 'https://'))

    try:
        if is_url:
            print(f"[Play] Прямая ссылка: {song_query}")
            ydl_opts = {"format": "bestaudio/best", "noplaylist": True, "quiet": True, "no_warnings": True}
            results = await search_ytdlp_async(song_query, ydl_opts, use_cookies=False)
            tracks = results.get("entries") or [results]
            source_name = results.get("extractor_key", "Unknown")
        else:
            # YouTube search
            ydl_opts_yt = {"format": "bestaudio[abr<=96]/bestaudio", "noplaylist": True, "quiet": True, "no_warnings": True}
            results = await search_ytdlp_async(f"ytsearch1:{song_query}", ydl_opts_yt, use_cookies=False)
            tracks = results.get("entries", [])
            source_name = "YouTube"
            if not tracks:
                # Bandcamp search
                ydl_opts_bc = {"format": "bestaudio/best", "noplaylist": True, "quiet": True, "no_warnings": True}
                results = await search_ytdlp_async(f"bandcampsearch1:{song_query}", ydl_opts_bc, use_cookies=False)
                tracks = results.get("entries", [])
                source_name = "Bandcamp"
            if not tracks:
                await interaction.followup.send("[Play] Трек не найден на YouTube или Bandcamp.")
                return
    except Exception as e:
        print(f"[Play] Ошибка поиска: {e}")
        await interaction.followup.send("[Play] Ошибка поиска трека.")
        return

    # Use first track
    first = tracks[0]
    webpage_url = first.get("webpage_url") or first.get("url")
    extract_opts = {"format": "bestaudio/best", "quiet": True, "no_warnings": True}

    try:
        detailed_info = await search_ytdlp_async(webpage_url, extract_opts, use_cookies=False)
        title = detailed_info.get("title", "Untitled")
        audio_url = detailed_info.get("url")
        http_headers = detailed_info.get("http_headers", {})
        print(f"[Play] Подготовка к воспроизведению: {title} ({source_name})")
    except Exception as e:
        print(f"[Play] Ошибка извлечения деталей: {e}")
        title = first.get("title", "Untitled")
        audio_url = first.get("url")
        http_headers = {}

    gid = str(interaction.guild_id)
    if gid not in SONG_QUEUES:
        SONG_QUEUES[gid] = deque()
    SONG_QUEUES[gid].append((audio_url, title, http_headers))

    if vc.is_playing() or vc.is_paused():
        await interaction.followup.send(f"[Queue] {title} ({source_name}) добавлен в очередь.")
    else:
        await interaction.followup.send(f"[Play] Активирована ретрансляция: {title} ({source_name})")
        await play_next_song(vc, gid, interaction.channel)

# Play next
async def play_next_song(vc, gid, channel):
    if SONG_QUEUES[gid]:
        audio_url, title, http_headers = SONG_QUEUES[gid].popleft()
        before_options = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
        if http_headers:
            header_pairs = [f"{k}: {v}" for k, v in http_headers.items()]
            headers_str = "\r\n".join(header_pairs) + "\r\n"
            before_options += f" -headers {shlex.quote(headers_str)}"

        ffmpeg_opts = {"before_options": before_options, "options": "-vn"}

        try:
            # Bandcamp - скачиваем во временный файл
            if "bandcamp.com" in audio_url:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
                    tmp_path = tmp_file.name
                ydl_opts = {"format": "bestaudio/best", "outtmpl": tmp_path, "quiet": True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    print(f"[FFmpeg] Скачиваем Bandcamp: {title}")
                    ydl.download([audio_url])
                source = discord.FFmpegOpusAudio(tmp_path)

                def cleanup(err):
                    try:
                        os.remove(tmp_path)
                    except:
                        pass
                    asyncio.run_coroutine_threadsafe(play_next_song(vc, gid, channel), bot.loop)

                vc.play(source, after=cleanup)
                await channel.send(f"[Now Playing] {title}")
                return
            else:
                # YouTube или поток
                source = discord.FFmpegOpusAudio(audio_url, **ffmpeg_opts)
                def after_play(err):
                    if err:
                        print(f"[FFmpeg] Ошибка воспроизведения {title}: {err}")
                    asyncio.run_coroutine_threadsafe(play_next_song(vc, gid, channel), bot.loop)
                vc.play(source, after=after_play)
                await channel.send(f"[Now Playing] {title}")
        except Exception as e:
            print(f"[FFmpeg] Ошибка воспроизведения {title}: {e}")
            await play_next_song(vc, gid, channel)
    else:
        await channel.send("[Queue] Очередь завершена.")
        SONG_QUEUES[gid] = deque()

# Run the bot
bot.run(TOKEN)
