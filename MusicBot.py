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
import aiohttp
from bs4 import BeautifulSoup
import urllib.parse

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

# Discord intents
intents = discord.Intents.default()
intents.message_content = True

# Bot setup
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"[Bot] {bot.user} v1.7 - Bandcamp only")

# ----------------------
# Helper: search Bandcamp
# ----------------------
async def search_bandcamp(query):
    print(f"[Bandcamp] Searching for: {query}")
    search_url = f"https://bandcamp.com/search?q={urllib.parse.quote(query)}"
    async with aiohttp.ClientSession() as session:
        async with session.get(search_url) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")
            html = await resp.text()
    soup = BeautifulSoup(html, "html.parser")
    # Найдём первый результат трека
    link_tag = soup.select_one('li.searchresult.track a')
    if not link_tag:
        raise Exception("No track found")
    track_url = link_tag.get("href")
    title_tag = link_tag.select_one(".heading")
    title = title_tag.text.strip() if title_tag else track_url
    print(f"[Bandcamp] Found track: {title} -> {track_url}")
    return {"title": title, "url": track_url}

# ----------------------
# Play command
# ----------------------
@bot.tree.command(name="play", description="Запустить песню или добавить в очередь (Bandcamp)")
@app_commands.describe(song_query="Название трека")
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

    # Поиск Bandcamp
    try:
        track_info = await search_bandcamp(song_query)
        audio_url = track_info["url"]
        title = track_info["title"]
    except Exception as e:
        print(f"[Play] Ошибка поиска Bandcamp: {e}")
        await interaction.followup.send(f"[Play] Трек '{song_query}' не найден на Bandcamp.")
        return

    gid = str(interaction.guild_id)
    if gid not in SONG_QUEUES:
        SONG_QUEUES[gid] = deque()
    SONG_QUEUES[gid].append((audio_url, title))

    if vc.is_playing() or vc.is_paused():
        await interaction.followup.send(f"[Queue] {title} добавлен в очередь.")
    else:
        await interaction.followup.send(f"[Play] Активирована ретрансляция: {title}")
        await play_next_song(vc, gid, interaction.channel)

# ----------------------
# Play next song
# ----------------------
async def play_next_song(vc, gid, channel):
    if SONG_QUEUES[gid]:
        audio_url, title = SONG_QUEUES[gid].popleft()
        # Скачиваем трек Bandcamp во временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
            tmp_path = tmp_file.name
        ydl_opts = {"format": "bestaudio/best", "outtmpl": tmp_path, "quiet": True}
        try:
            print(f"[FFmpeg] Скачиваем Bandcamp: {title}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
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
        except Exception as e:
            print(f"[FFmpeg] Ошибка воспроизведения {title}: {e}")
            await play_next_song(vc, gid, channel)
    else:
        await channel.send("[Queue] Очередь завершена.")
        SONG_QUEUES[gid] = deque()

# ----------------------
# Skip / Pause / Resume / Stop
# ----------------------
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
    if not vc or not vc.is_playing():
        return await interaction.response.send_message("[Pause] Сигнал уже неактивен.")
    vc.pause()
    await interaction.response.send_message("[Pause] Сигнал приостановлен.")

@bot.tree.command(name="resume", description="Продолжить")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc or not vc.is_paused():
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

# Run the bot
bot.run(TOKEN)
