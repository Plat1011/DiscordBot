# Discord Music Bot

## Overview
This is a Discord music bot written in Python that allows users to play music from YouTube in voice channels. The bot uses discord.py for Discord integration, yt-dlp for YouTube audio extraction, and FFmpeg for audio processing.

## Features
- Play music from YouTube using search queries or URLs
- Queue system for multiple songs
- Basic playback controls (play, pause, resume, skip, stop)
- Automatic disconnection when queue is empty
- Russian language interface

## Recent Changes (September 20, 2025)
- Set up Python 3.11 environment in Replit
- Installed all required dependencies (discord.py, yt-dlp, python-dotenv, PyNaCl)
- Fixed FFmpeg path for Linux environment (removed Windows-specific path)
- Created .env.example template for Discord token configuration
- Set up Discord Bot workflow for running the bot
- Verified bot successfully connects to Discord

## Project Architecture
- **MusicBot.py**: Main bot file containing all Discord commands and music functionality
- **requirements.txt**: Python dependencies list
- **bin/ffmpeg/**: FFmpeg binaries (no longer used, system FFmpeg is used instead)
- **.env**: Environment variables (Discord token) - not tracked in git
- **.env.example**: Template for environment configuration

## Dependencies
- discord.py: Discord API wrapper
- yt-dlp: YouTube video/audio downloader
- python-dotenv: Environment variable management
- PyNaCl: Voice support for Discord
- FFmpeg: Audio processing (system-installed)

## Environment Setup
The bot requires a Discord token to function:
1. Create a Discord application at https://discord.com/developers/applications
2. Create a bot user and copy the token
3. The token is already configured in the Replit environment as DISCORD_TOKEN

## Commands
All commands use Discord slash commands (/):
- `/play <query>`: Play or queue a song from YouTube
- `/pause`: Pause current playback
- `/resume`: Resume paused playback
- `/skip`: Skip current song
- `/stop`: Stop playback and clear queue

## Running the Bot
The bot runs automatically via the Discord Bot workflow. It can be manually started with:
```bash
python MusicBot.py
```

## User Preferences
- Language: Russian interface (can be modified in MusicBot.py)
- Audio quality: Optimized for 96k bitrate opus audio
- Queue system: FIFO (first in, first out)

## Technical Notes
- Bot uses FFmpeg opus audio for optimal Discord compatibility
- Supports reconnection for stream reliability
- Queue is stored in memory (resets on restart)
- Automatically disconnects from voice channels when idle