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

# search_ytdlp_async теперь принимает флаг use_cookies
async def search_ytdlp_async(query, ydl_opts, use_cookies: bool = True):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _extract(query, ydl_opts, use_cookies))

def _extract(query, ydl_opts, use_cookies: bool = True):
    cookie_path = None

    # если нужно использовать куки — создаём временный файл из секрета YT_COOKIES
    if use_cookies:
        cookie_content = os.getenv("YT_COOKIES")
        if not cookie_content:
            # если куки не заданы — не продолжаем с YouTube
            raise Exception("YT_COOKIES not set in Replit secrets, cannot use cookies for YouTube.")
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
            f.write(cookie_content)
            cookie_path = f.name
        # временно добавляем cookiefile к опциям
        ydl_opts["cookiefile"] = cookie_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(query, download=False)
    finally:
        # удаляем временный файл cookies, если создали
        if cookie_path and os.path.exists(cookie_path):
            os.remove(cookie_path)


# Setup of intents
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
        await interaction.response.send_message(
            "Штаб Charlie squad: ретрансляция переключена. Частота скорректирована, сигнал перенаправлен."
        )
    else:
        await interaction.response.send_message("Штаб: эфир пуст, переключение не требуется.")

@bot.tree.command(name="pause", description="Ставит на паузу")
async def pause(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client is None:
        return await interaction.response.send_message("Штаб: сигнал отсутствует, линии связи не задействованы.")
    if not voice_client.is_playing():
        return await interaction.response.send_message("Штаб: ретрансляция неактивна, пауза невозможна.")
    voice_client.pause()
    await interaction.response.send_message(
        "Штаб: частоты временно заморожены, передача данных приостановлена."
    )

@bot.tree.command(name="resume", description="Продолжим")
async def resume(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client is None:
        return await interaction.response.send_message("Штаб: сигнал ещё не восстановлен, линии молчат.")
    if not voice_client.is_paused():
        return await interaction.response.send_message("Штаб: ретрансляция и так активна, восстановление не требуется.")
    voice_client.resume()
    await interaction.response.send_message(
        "Штаб Charlie squad: передача данных восстановлена, резервные линии задействованы."
    )

@bot.tree.command(name="stop", description="Остановить все и очистить очередь")
async def stop(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if not voice_client or not voice_client.is_connected():
        return await interaction.response.send_message("Штаб: нет активного подключения, остановка не требуется.")

    guild_id_str = str(interaction.guild_id)
    if guild_id_str in SONG_QUEUES:
        SONG_QUEUES[guild_id_str].clear()

    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    await voice_client.disconnect()
    await interaction.response.send_message(
        "Штаб: ретрансляция завершена, частоты очищены, контрольные точки сняты."
    )

@bot.tree.command(name="play", description="Запустить песню или добавить в очередь")
@app_commands.describe(song_query="Search query")
async def play(interaction: discord.Interaction, song_query: str):
    await interaction.response.defer()

    if interaction.user.voice is None or interaction.user.voice.channel is None:
        await interaction.followup.send(
            "Штаб: вы не подключены к ретрансляционной вышке. Доступ к частотам невозможен."
        )
        return

    voice_channel = interaction.user.voice.channel
    voice_client = interaction.guild.voice_client

    if voice_client is None:
        voice_client = await voice_channel.connect()
    elif voice_channel != voice_client.channel:
        await voice_client.move_to(voice_channel)

    # базовые опции — сначала используем для YouTube (с куками)
    ydl_options_youtube = {
        "format": "bestaudio[abr<=96]/bestaudio",
        "noplaylist": True,
        "youtube_include_dash_manifest": False,
        "youtube_include_hls_manifest": False,
        "quiet": True,
        "no_warnings": True,
    }

    query = "ytsearch1: " + song_query

    # Первый этап: пробуем YouTube (с куками). Если не получилось — падаем на SoundCloud.
    try:
        results = await search_ytdlp_async(query, dict(ydl_options_youtube), use_cookies=True)
        tracks = results.get("entries")
        if not tracks:
            # попробуем SoundCloud дальше
            raise Exception("No YouTube entries")
    except Exception as e:
        print(f"YT-DLP (YouTube) failed: {e}")
        # Попытка SoundCloud
        ydl_options_sc = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
        }
        sc_query = "scsearch1: " + song_query
        try:
            results = await search_ytdlp_async(sc_query, dict(ydl_options_sc), use_cookies=False)
            tracks = results.get("entries")
            if not tracks:
                await interaction.followup.send("Штаб: сигнал не обнаружен, канал связи пуст.")
                return
        except Exception as e2:
            print(f"YT-DLP (SoundCloud) failed: {e2}")
            await interaction.followup.send(
                "Штаб: каналы заблокированы, доступ к частоте невозможен."
            )
            return

    # Если дошли сюда — в tracks есть хотя бы один элемент (YouTube или SoundCloud)
    first_track = tracks[0]
    # Некоторые экстракторы возвращают прямой 'url' для ffmpeg, некоторые — 'webpage_url' и т.д.
    audio_url = first_track.get("url") or first_track.get("webpage_url")
    title = first_track.get("title", "Untitled")

    guild_id = str(interaction.guild_id)
    if SONG_QUEUES.get(guild_id) is None:
        SONG_QUEUES[guild_id] = deque()

    SONG_QUEUES[guild_id].append((audio_url, title))

    if voice_client.is_playing() or voice_client.is_paused():
        await interaction.followup.send(
            f"Штаб: сигнал **{title}** зафиксирован и добавлен в очередь ретрансляции."
        )
    else:
        await interaction.followup.send(
            f"Штаб Charlie squad активировал ретрансляцию: **{title}**. Каналы проверены, контрольные точки выставлены."
        )
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
        asyncio.create_task(channel.send(
            f"Штаб: сигнал в эфире — **{title}**. Передача данных шифрована, резервные линии наготове."
        ))
    else:
        await channel.send(
            "Штаб Charlie squad: ретрансляция завершена, все узлы находятся под мониторингом, линии очищены."
        )
        SONG_QUEUES[guild_id] = deque()

# Run the bot
bot.run(TOKEN)
