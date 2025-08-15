import discord
from discord.ext import commands
from yt_dlp import YoutubeDL
import asyncio
import shutil
import os
from flask import Flask
from threading import Thread

# -----------------------------
# Flask web server (keep-alive)
# -----------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running on Render!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# -----------------------------
# Discord Bot setup
# -----------------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

token = os.environ.get('DISCORD_TOKEN')
if not token:
    raise ValueError("No DISCORD_TOKEN found in environment variables")

# YTDL + FFmpeg options
ytdl_format_options = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'ignoreerrors': True,
    'geo_bypass': True,  # bypass region
}

ffmpeg_path = shutil.which("ffmpeg")
if not ffmpeg_path:
    raise EnvironmentError("FFmpeg not found. Make sure it is installed.")

ffmpeg_options = {
    'options': '-vn',
    'executable': ffmpeg_path
}

ytdl = YoutubeDL(ytdl_format_options)

# -----------------------------
# YTDLSource class
# -----------------------------
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
            if not data:
                print("[YTDL Error] No data returned")
                return None
            if 'entries' in data:
                data = data['entries'][0]
            filename = data['url']
            print("[YTDL Debug] Streaming URL:", filename)
            return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)
        except Exception as e:
            print("[YTDL Error] Could not extract info:", e)
            return None

# -----------------------------
# Bot events and commands
# -----------------------------
@bot.event
async def on_ready():
    print("FFmpeg path:", ffmpeg_options['executable'])
    print(f'Bot is ready. Logged in as {bot.user}')

@bot.command()
async def join(ctx):
    if ctx.author.voice:
        await ctx.author.voice.channel.connect()
        await ctx.send(f"Joined {ctx.author.voice.channel.name}")
    else:
        await ctx.send("You are not in a voice channel!")

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected from voice channel.")
    else:
        await ctx.send("I am not in a voice channel!")

@bot.command()
async def play(ctx, *, url):
    try:
        if not ctx.voice_client:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                return await ctx.send("You are not in a voice channel!")

        player = await YTDLSource.from_url(url, loop=bot.loop)
        if not player:
            return await ctx.send("Failed to retrieve or play the URL!")

        print("[DEBUG] Streaming URL:", player.url)
        ctx.voice_client.play(player, after=lambda e: print(f'[Player error] {e}') if e else None)
        await ctx.send(f'Now playing: {player.title}')
        print("[DEBUG] is_playing:", ctx.voice_client.is_playing())

    except Exception as e:
        print("[ERROR in play command]", e)
        await ctx.send(f"An error occurred: {e}")

@bot.command()
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("Paused the music.")

@bot.command()
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("Resumed the music.")

@bot.command()
async def stop(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("Stopped the music.")

# -----------------------------
# Main run
# -----------------------------
if __name__ == "__main__":
    # รันเว็บเซิร์ฟเวอร์ใน background thread
    Thread(target=run_web).start()
    # รัน Discord bot
    bot.run(token)
