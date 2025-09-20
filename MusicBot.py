# Importing libraries and modules
from flask import Flask
from threading import Thread
import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import yt_dlp # NEW
from collections import deque # NEW
import asyncio # NEW


app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

# Environment variables for tokens and other sensitive data
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Create the structure for queueing songs - Dictionary of queues
SONG_QUEUES = {}

async def search_ytdlp_async(query, ydl_opts):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _extract(query, ydl_opts))

def _extract(query, ydl_opts):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(query, download=False)


# Setup of intents. Intents are permissions the bot has on the server
intents = discord.Intents.default()
intents.message_content = True

# Bot setup
bot = commands.Bot(command_prefix="!", intents=intents)

# Bot ready-up code
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} снова тут")


@bot.tree.command(name="skip", description="Пропускает текущую песню")
async def skip(interaction: discord.Interaction):
    if interaction.guild.voice_client and (interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused()):
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("Песня пропущена через 5G-каналы.")
    else:
        await interaction.response.send_message("Нечего пропускать — эфир пуст!")


@bot.tree.command(name="pause", description="Ставит на паузу")
async def pause(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    if voice_client is None:
        return await interaction.response.send_message("Я потерял сигнал 5G и ушёл в офлайн…")

    if not voice_client.is_playing():
        return await interaction.response.send_message("Нечего ставить на паузу — эфир пуст!")

    voice_client.pause()
    await interaction.response.send_message("Поток 5G временно заморожен.")


@bot.tree.command(name="resume", description="Продолжим")
async def resume(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    if voice_client is None:
        return await interaction.response.send_message("Сигнал 5G ещё не восстановлен…")

    if not voice_client.is_paused():
        return await interaction.response.send_message("Эфир и так идёт, нечего продолжать.")

    voice_client.resume()
    await interaction.response.send_message("Эфир 5G снова в действии!")


@bot.tree.command(name="stop", description="Остановить все и очистить очередь")
async def stop(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    if not voice_client or not voice_client.is_connected():
        return await interaction.response.send_message("Нет подключения к 5G-башне, нечего отключать.")

    guild_id_str = str(interaction.guild_id)
    if guild_id_str in SONG_QUEUES:
        SONG_QUEUES[guild_id_str].clear()

    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    await voice_client.disconnect()
    await interaction.response.send_message("Отключаемся от 5G… башня больше не отслеживает ваш плейлист.")


@bot.tree.command(name="play", description="Запустить песню или добавить в очередь")
@app_commands.describe(song_query="Search query")
async def play(interaction: discord.Interaction, song_query: str):
    await interaction.response.defer()

    if interaction.user.voice is None or interaction.user.voice.channel is None:
        await interaction.followup.send(
            "Вы не подключены к ближайшей башне 5G! Без сигнала музыка не доходит."
        )
        return

    voice_channel = interaction.user.voice.channel
    voice_client = interaction.guild.voice_client

    if voice_client is None:
        voice_client = await voice_channel.connect()
    elif voice_channel != voice_client.channel:
        await voice_client.move_to(voice_channel)

    ydl_options = {
        "format": "bestaudio[abr<=96]/bestaudio",
        "noplaylist": True,
        "youtube_include_dash_manifest": False,
        "youtube_include_hls_manifest": False,
    }

    query = "ytsearch1: " + song_query

    try:
        results = await search_ytdlp_async(query, ydl_options)
        tracks = results.get("entries")
        if not tracks:
            await interaction.followup.send("Таких не знаю в эфире 5G…")
            return
    except Exception as e:
        # Если yt-dlp не смог получить видео (например, YouTube требует авторизацию)
        await interaction.followup.send(
            "Сигналы 5G заблокировали доступ к этой песне. Кто-то контролирует эфир…"
        )
        print(f"YT-DLP ERROR: {e}")  # Логи для дебага
        return

    first_track = tracks[0]
    audio_url = first_track["url"]
    title = first_track.get("title", "Untitled")

    guild_id = str(interaction.guild_id)
    if SONG_QUEUES.get(guild_id) is None:
        SONG_QUEUES[guild_id] = deque()

    SONG_QUEUES[guild_id].append((audio_url, title))

    if voice_client.is_playing() or voice_client.is_paused():
        await interaction.followup.send(f"Песня **{title}** передана через 5G-частоты, добавлена в очередь.")
    else:
        await interaction.followup.send(f"Сейчас эфир 5G транслирует: **{title}**. Осторожно, сигнал может контролировать мысли… 😉")
        await play_next_song(voice_client, guild_id, interaction.channel)



async def play_next_song(voice_client, guild_id, channel):
    if SONG_QUEUES[guild_id]:
        audio_url, title = SONG_QUEUES[guild_id].popleft()

        ffmpeg_options = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn -c:a libopus -b:a 96k",
        }

        source = discord.FFmpegOpusAudio(audio_url, **ffmpeg_options)

        def after_play(error):
            if error:
                print(f"ОШИБКА {title}: {error}")
            asyncio.run_coroutine_threadsafe(play_next_song(voice_client, guild_id, channel), bot.loop)

        voice_client.play(source, after=after_play)
        asyncio.create_task(channel.send(f"Сейчас играет: **{title}**"))
    else:
        await channel.send("Очередь песен через 5G завершена. Жду новых сигналов!")
        SONG_QUEUES[guild_id] = deque()


# Run the bot
bot.run(TOKEN)
