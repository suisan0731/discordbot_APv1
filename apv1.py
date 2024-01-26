import discord
import yt_dlp
import asyncio
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.message_content = True

TOKEN = os.environ['DISCORD_TOKEN']

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': './audio/%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'options': '-vn',
}


class AudioQueue(asyncio.Queue):

  def __init__(self):
    super().__init__(100)
    self.playing_now = None

  def __getitem__(self, idx):
    return self._queue[idx]

  def reset(self):
    self._queue.clear()


class AudioStatus:

  def __init__(self, ctx):
    self.ctx = ctx
    self.now_title = None
    self.loop = 0
    self.now_filename = None
    self.queue = AudioQueue()
    self.playing = asyncio.Event()
    asyncio.create_task(self.playing_task())

  async def add_audio(self, url):
    ydl = yt_dlp.YoutubeDL(ytdl_format_options)
    res = ydl.extract_info(url)
    filename = ydl.prepare_filename(res)
    title = res['title']
    await self.queue.put([filename, title])
    return title

  async def playing_task(self):
    while True:
      self.playing.clear()
      try:
        filename, title = await asyncio.wait_for(self.queue.get(), timeout=300)
      except asyncio.TimeoutError:
        asyncio.create_task(self.leave())
      self.now_title = title
      self.now_filename = filename
      src = discord.FFmpegPCMAudio(self.now_filename, **ffmpeg_options)
      src_adj = discord.PCMVolumeTransformer(src, volume=0.6)
      self.ctx.guild.voice_client.play(src_adj, after=self.play_next)
      await self.ctx.channel.send('```{} を再生します```'.format(self.now_title))
      await self.playing.wait()
      if self.loop == 1:
        await self.queue.put([self.now_filename, self.now_title])
      elif self.loop == 2:
        self.loop = 0

  def play_next(self, err=None):
    if self.loop == 2:
      src = discord.FFmpegPCMAudio(self.now_filename, **ffmpeg_options)
      src_adj = discord.PCMVolumeTransformer(src, volume=0.6)
      self.ctx.guild.voice_client.play(src_adj, after=self.play_next)
    else:
      self.playing.set()

  async def leave(self):
    self.queue.reset()
    if self.ctx.guild.voice_client:
      await self.ctx.guild.voice_client.disconnect()


#{guild_id: Audiostatus}
audio_status = dict()


class MyhelpCommand(commands.HelpCommand):

  def __init__(self):
    super().__init__(command_attrs={"brief": "ヘルプを表示"})

  async def send_bot_help(self, mapping) -> None:
    cmds = mapping[None]
    cmds_max_length = max([len(cmd.name) for cmd in cmds])
    txt = '```'
    for cmd in cmds:
      brief_list = cmd.brief.splitlines()
      c = 0
      txt += ('${:<' + str(cmds_max_length) + '} {}\n').format(
          cmd.name, brief_list[c])
      c += 1
      while c < len(brief_list):
        txt += ' ' * cmds_max_length + '  {}\n'.format(brief_list[c])
        c += 1
    txt += '```'
    await self.get_destination().send(txt)


bot = commands.Bot(command_prefix='$',
                   intents=intents,
                   help_command=MyhelpCommand())
discord.opus.load_opus('libopus/lib/libopus.so')


@bot.command(name='join', brief='ボイスチャットに参加する')
async def join(ctx):
  if ctx.author.voice is None:
    await ctx.channel.send("```あなたはボイスチャンネルに接続していません```")
    return
  elif ctx.guild.voice_client is not None and ctx.guild.voice_client.channel == ctx.author.voice.channel:
    await ctx.channel.send('```すでに {} チャンネルに参加しています```'.format(
        ctx.author.voice.channel.name))
    return
  await ctx.author.voice.channel.connect()
  await ctx.channel.send('```{} チャンネルに接続しました```'.format(
      ctx.author.voice.channel.name))
  audio_status[ctx.guild.id] = AudioStatus(ctx)


@bot.command(name='leave', brief='ボイスチャットから退出する')
async def leave(ctx):
  status = audio_status.get(ctx.guild.id)
  if ctx.author.voice is None:
    await ctx.channel.send('```あなたはボイスチャンネルに接続していません```')
    return
  elif status is None:
    await ctx.channel.send('```Botがボイスチャンネルに接続していません ```')
    return
  await status.leave()
  await ctx.channel.send('```{} チャンネルを退出しました```'.format(
      ctx.author.voice.channel.name))
  del audio_status[ctx.guild.id]


@bot.command(name='play', brief='$play <YouTbe URL> で音楽を再生する')
async def play(ctx, *, url):
  if ctx.author.voice is None:
    await ctx.channel.send('```あなたはボイスチャンネルに接続していません```')
    return
  status = audio_status.get(ctx.guild.id)
  if status is None:
    await ctx.invoke(join)
    status = audio_status.get(ctx.guild.id)
  title = await status.add_audio(url)
  await ctx.channel.send('```{} を再生リストに追加しました```'.format(title))


@bot.command(name='pause', brief='音楽を一時中断する $resumeで再開可能')
async def pause(ctx):
  if ctx.author.voice is None:
    await ctx.channel.send('```あなたはボイスチャンネルに接続していません```')
    return
  elif ctx.guild.voice_client is None:
    await ctx.channel.send('```Botがボイスチャンネルに接続していません```')
    return
  elif not ctx.guild.voice_client.is_playing():
    await ctx.channel.send('```音楽を再生していません```')
    return
  ctx.guild.voice_client.pause()
  status = audio_status.get(ctx.guild.id)
  await ctx.channel.send("```{} の再生を中止しました $resumeで再開可能です```".format(
      status.now_title))


@bot.command(name='resume', brief='$pauseした音楽を再開する')
async def resume(ctx):
  if ctx.author.voice is None:
    await ctx.channel.send('```あなたはボイスチャンネルに接続していません```')
    return
  elif ctx.guild.voice_client is None:
    await ctx.channel.send('```Botがボイスチャンネルに接続していません```')
    return
  elif ctx.guild.voice_client.is_playing():
    await ctx.channel.send('```音楽を停止していません```')
    return
  ctx.guild.voice_client.resume()
  status = audio_status.get(ctx.guild.id)
  await ctx.channel.send("```{} の再生を再開しました```".format(status.now_title))


@bot.command(name='stop', brief='音楽を停止する 再開はできない')
async def stop(ctx):
  if ctx.author.voice is None:
    await ctx.channel.send('```あなたはボイスチャンネルに接続していません```')
    return
  elif ctx.guild.voice_client is None:
    await ctx.channel.send('```Botがボイスチャンネルに接続していません```')
    return
  elif not ctx.guild.voice_client.is_playing():
    await ctx.channel.send('```音楽を再生していません```')
    return
  ctx.guild.voice_client.stop()
  status = audio_status.get(ctx.guild.id)
  await ctx.channel.send("```{} の再生を中止しました```".format(status.now_title))


@bot.command(name='loop',
             brief='$loop <this, list>\n- this この曲をループ\n- list 再生リストをループ')
async def loop(ctx, *, loop_type):
  if ctx.author.voice is None:
    await ctx.channel.send('```あなたはボイスチャンネルに接続していません```')
    return
  elif ctx.guild.voice_client is None:
    await ctx.channel.send('```Botがボイスチャンネルに接続していません```')
    return
  status = audio_status.get(ctx.guild.id)
  if not ctx.guild.voice_client.is_playing():
    await ctx.channel.send('```音楽を再生していません```')
    return
  elif loop_type == 'list':
    if status.loop == 1:
      await ctx.channel.send('```すでに再生リストをループ再生しています```')
      return
    status.loop = 1
    await ctx.channel.send('```再生リストをループ再生します```')
  elif loop_type == 'this':
    if status.loop == 2:
      await ctx.channel.send('```すでに{} をループ再生しています```'.format(status.now_title)
                             )
      return
    status.loop = 2
    await ctx.channel.send('```{} をループ再生します```'.format(status.now_title))
  else:
    await ctx.channel.send('```コマンドが不正です```')


@bot.command(name='unloop', brief='ループを停止する')
async def unloop(ctx):
  if ctx.author.voice is None:
    await ctx.channel.send('```あなたはボイスチャンネルに接続していません```')
    return
  elif ctx.guild.voice_client is None:
    await ctx.channel.send('```Botがボイスチャンネルに接続していません```')
    return
  status = audio_status.get(ctx.guild.id)
  if not ctx.guild.voice_client.is_playing():
    await ctx.channel.send('```音楽を再生していません```')
    return
  elif not status.loop:
    await ctx.channel.send('```ループ再生していません```'.format(status.now_title))
    return
  status.loop = 0
  await ctx.channel.send('```ループ解除します```'.format(status.now_title))


bot.run(TOKEN)
