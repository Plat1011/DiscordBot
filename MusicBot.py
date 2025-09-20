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
import requests
from bs4 import BeautifulSoup

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

# Helper functions
def search_bandcamp(query):
    """Ищем первый трек на Bandcamp по запросу"""
    url = f"https://bandcamp.com/search?q={query.replace(' ', '+')}"
    resp = requests.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")
    track = soup.select_one(".searchresult.track > a")
    if track:
        return track['href']
    return None

async def get_bandcamp_info(track_url):
    """Получаем аудио URL с Bandcamp через yt_dlp"""
    ydl_opts = {"format": "bestaudio/best", "quiet": True, "no_warnings": True}
    loop = asyncio.get_running_loop()
    def extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(track_url, download=False)
    return await loop.run_in_executor(None, extract)

# Bot commands: skip, pause, resume, stop
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
@bot.tree.command(name="play", description="Запустить песню с Bandcamp")
@app_commands.describe(song_query="Поиск трека на Bandcamp")
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

    # Поиск трека на Bandcamp
    track_url = search_bandcamp(song_query)
    if not track_url:
        await interaction.followup.send("[Play] Трек не найден на Bandcamp.")
        return

    # Получение информации через yt_dlp
    try:
        info = await get_bandcamp_info(track_url)
        title = info.get("title", "Untitled")
        audio_url = info.get("url")
        print(f"[Play] Подготовка к воспроизведению: {title}")
    except Exception as e:
        print(f"[Play] Ошибка извлечения трека: {e}")
        await interaction.followup.send("[Play] Не удалось получить аудио.")
        return

    gid = str(interaction.guild_id)
    if gid not in SONG_QUEUES:
        SONG_QUEUES[gid] = deque()
    SONG_QUEUES[gid].append((audio_url, title))

    if vc.is_playing() or vc.is_paused():
        await interaction.followup.send(f"[Queue] {title} добавлен в очередь.")
    else:
        await interaction.followup.send(f"[Play] В эфире: {title}")
        await play_next_song(vc, gid, interaction.channel)

# Play next
async def play_next_song(vc, gid, channel):
    if SONG_QUEUES[gid]:
        audio_url, title = SONG_QUEUES[gid].popleft()
        ffmpeg_opts = {"options": "-vn"}
        try:
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
