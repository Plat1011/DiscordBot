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

# Async search wrapper
async def search_ytdlp_async(query, ydl_opts, use_cookies: bool = True):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _extract(query, ydl_opts, use_cookies))

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

    tracks = []
    source_name = ""
    
    # Check if input is a direct URL
    is_url = song_query.startswith(('http://', 'https://'))
    
    if is_url:
        # Handle direct URLs
        ydl_opts = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
        }
        
        try:
            results = await search_ytdlp_async(song_query, ydl_opts, use_cookies=False)
            if results.get("entries"):
                tracks = results["entries"]
            else:
                tracks = [results]  # Single track
            source_name = results.get("extractor_key", "Unknown")
        except Exception as e:
            print(f"Direct URL failed: {e}")
            await interaction.followup.send("Штаб: ошибка обработки ссылки.")
            return
    else:
        # Search logic - try YouTube first, then SoundCloud
        ydl_opts_yt = {
            "format": "bestaudio[abr<=96]/bestaudio",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
        }
        
        try:
            results = await search_ytdlp_async(f"ytsearch1:{song_query}", ydl_opts_yt, use_cookies=False)
            tracks = results.get("entries", [])
            source_name = "YouTube"
            if not tracks:
                raise Exception("No YouTube results")
        except Exception as e:
            print(f"YouTube search failed: {e}")
            
            # Try SoundCloud as fallback
            ydl_opts_sc = {
                "format": "bestaudio/best", 
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
            }
            
            try:
                results = await search_ytdlp_async(f"scsearch1:{song_query}", ydl_opts_sc, use_cookies=False)
                tracks = results.get("entries", [])
                source_name = "SoundCloud"
                if not tracks:
                    await interaction.followup.send("Штаб: сигнал не обнаружен на всех частотах.")
                    return
            except Exception as e2:
                print(f"SoundCloud search failed: {e2}")
                await interaction.followup.send("Штаб: все каналы заблокированы, поиск невозможен.")
                return

    # Use first track and extract detailed info with headers
    first = tracks[0]
    webpage_url = first.get("webpage_url") or first.get("url")
    
    # Re-extract to get headers and final URL
    extract_opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
    }
    
    try:
        detailed_info = await search_ytdlp_async(webpage_url, extract_opts, use_cookies=False)
        title = detailed_info.get("title", "Untitled")
        audio_url = detailed_info.get("url")
        http_headers = detailed_info.get("http_headers", {})
    except Exception as e:
        print(f"Header extraction failed: {e}")
        title = first.get("title", "Untitled")
        audio_url = first.get("url")
        http_headers = {}

    gid = str(interaction.guild_id)
    if gid not in SONG_QUEUES:
        SONG_QUEUES[gid] = deque()
    SONG_QUEUES[gid].append((audio_url, title, http_headers))

    if vc.is_playing() or vc.is_paused():
        await interaction.followup.send(f"Штаб: сигнал **{title}** ({source_name}) добавлен в очередь ретрансляции.")
    else:
        await interaction.followup.send(f"Штаб: активирована ретрансляция **{title}** ({source_name})")
        await play_next_song(vc, gid, interaction.channel)

# Play next
async def play_next_song(vc, gid, channel):
    if SONG_QUEUES[gid]:
        audio_url, title, http_headers = SONG_QUEUES[gid].popleft()

        # Build headers string for FFmpeg
        before_options = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
        if http_headers:
            header_pairs = [f"{k}: {v}" for k, v in http_headers.items()]
            headers_str = "\r\n".join(header_pairs) + "\r\n"
            before_options += f" -headers {shlex.quote(headers_str)}"

        ffmpeg_opts = {
            "before_options": before_options,
            "options": "-vn",
        }
        
        try:
            source = discord.FFmpegOpusAudio(audio_url, **ffmpeg_opts)

            def after_play(err):
                if err:
                    print(f"ОШИБКА {title}: {err}")
                asyncio.run_coroutine_threadsafe(play_next_song(vc, gid, channel), bot.loop)

            vc.play(source, after=after_play)
            asyncio.create_task(channel.send(f"Штаб: сигнал в эфире — **{title}**"))
        except Exception as e:
            print(f"Ошибка воспроизведения {title}: {e}")
            await play_next_song(vc, gid, channel)  # Try next song
    else:
        await channel.send("Штаб Charlie squad: ретрансляция завершена.")
        SONG_QUEUES[gid] = deque()

# Run the bot
bot.run(TOKEN)
