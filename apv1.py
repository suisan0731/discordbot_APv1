import discord
import yt_dlp
import asyncio
from discord.ext import commands

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
    self.mode = 'single'
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
    if self.mode == 'list':
      await self.ctx.channel.send('```{} を再生リストに追加しました```'.format(title))
    elif self.ctx.guild.voice_client.is_playing():
      self.ctx.guild.voice_client.stop()
    await self.queue.put([filename, title])

  async def playing_task(self):
    while True:
      self.playing.clear()
      try:
        filename, title = await asyncio.wait_for(self.queue.get(), timeout=300)
      except asyncio.TimeoutError:
        asyncio.create_task(self.leave())
      self.now_title = title
      self.now_filename = filename
      src = discord.FFmpegPCMAudio(self.now_filename, **ffmpeg_options, executable="ffmpeg-6.1-amd64-static/ffmpeg")
      src_adj = discord.PCMVolumeTransformer(src, volume=0.6)
      self.ctx.guild.voice_client.play(src_adj, after=self.play_next)
      await self.ctx.channel.send('```{} を再生します```'.format(self.now_title))
      await self.playing.wait()
      if self.loop == 1:
          await self.queue.put([self.now_filename, self.now_title])

  def play_next(self, err=None):
    self.playing.set()

  async def leave(self):
    self.queue.reset()
    if self.ctx.guild.voice_client:
      await self.ctx.guild.voice_client.disconnect()

  async def stop(self):
    self.queue.reset()
    self.loop = 0
    self.ctx.guild.voice_client.stop()


class AudioCog(commands.Cog):
  def __init__(self, bot):
    self.bot = bot

    #{guild_id: Audiostatus}
    self.audio_status = dict()
  
  async def check_connect_channel(self, ctx, playing_check):
    if ctx.author.voice is None:
      await ctx.channel.send('```あなたはボイスチャンネルに接続していません```')
      return 1
    elif ctx.guild.voice_client is None:
      await ctx.channel.send('```Botがボイスチャンネルに接続していません```')
      return 1
    elif ctx.guild.voice_client.channel != ctx.author.voice.channel:
      await ctx.channel.send('```Botと同じボイスチャンネルに接続する必要があります```')
      return 1
    if playing_check:
      if not ctx.guild.voice_client.is_playing():
        await ctx.channel.send('```音楽を再生していません```')
        return 1
    return 0


  @commands.command(name='join', brief='このコマンドを打ったユーザが参加しているボイスチャンネルに参加する。')
  async def join(self, ctx):
    if ctx.author.voice is None:
      await ctx.channel.send("```あなたはボイスチャンネルに接続していません```")
      return
    elif ctx.guild.voice_client is not None and ctx.guild.voice_client.channel == ctx.author.voice.channel:
      await ctx.channel.send('```すでに {} チャンネルに参加しています```'.format(
          ctx.author.voice.channel.name))
      return
    elif ctx.guild.voice_client is not None and ctx.guild.voice_client.channel != ctx.author.voice.channel:
      await ctx.guild.voice_client.disconnect()
    await ctx.author.voice.channel.connect()
    await ctx.channel.send('```{} チャンネルに接続しました```'.format(ctx.author.voice.channel.name))
    self.audio_status[ctx.guild.id] = AudioStatus(ctx)


  @commands.command(name='leave', brief='ボイスチャンネルから退出する。')
  async def leave(self, ctx):
    status = self.audio_status.get(ctx.guild.id)
    if await self.check_connect_channel(ctx, False):
      return
    await status.leave()
    await ctx.channel.send('```{} チャンネルを退出しました```'.format(ctx.author.voice.channel.name))
    del self.audio_status[ctx.guild.id]


  @commands.command(name='mode', brief=
                    '''$mode <mode>で再生リストモードかシングルモードかを指定する。初期値はsingle。
list - 再生リストモード。$loopコマンドは再生リスト全体でループ、$playコマンドは再生リストに追加し、順番になったら再生される。
single - シングルモード。$loopコマンドは一つの曲をループ、$playコマンドは今の曲を停止し、直ちに再生される。''')
  async def mode(self, ctx, mode='single'):
    status = self.audio_status.get(ctx.guild.id)
    if await self.check_connect_channel(ctx, False):
      return
    elif status.mode == mode:
      await ctx.channel.send('```すでに{} モードです```'.format(status.mode))
    elif mode in ['single', 'list']:
      status.mode = mode
      if ctx.guild.voice_client.is_playing:
        await status.stop()
      await ctx.channel.send('```{} モードに切り替えました```'.format(status.mode))
    else:
      await ctx.channel.send('```コマンドが不正です```')


  @commands.command(name='play', brief='$play <url>でYouTubeの音楽を再生する。')
  async def play(self, ctx, url):
    status = self.audio_status.get(ctx.guild.id)
    if status is None or ctx.guild.voice_client.channel != ctx.author.voice.channel:
      await ctx.invoke(self.join)
      status = self.audio_status.get(ctx.guild.id)
    await status.add_audio(url)


  @commands.command(name='pause', brief='音楽を一時中断する。$resumeで再開可能。')
  async def pause(self, ctx):
    if await self.check_connect_channel(ctx, True):
      return
    ctx.guild.voice_client.pause()
    status = self.audio_status.get(ctx.guild.id)
    await ctx.channel.send("```{} の再生を中止しました $resumeで再開可能です```".format(status.now_title))


  @commands.command(name='resume', brief='$pauseした音楽を再開する')
  async def resume(self, ctx):
    if await self.check_connect_channel(ctx, False):
      return
    elif not ctx.guild.voice_client.is_paused():
      await ctx.channel.send("```再生を一時中断していません```")
      return
    ctx.guild.voice_client.resume()
    status = self.audio_status.get(ctx.guild.id)
    await ctx.channel.send("```{} の再生を再開しました```".format(status.now_title))


  @commands.command(name='stop', brief='音楽を停止する。再開はできない。')
  async def stop(self, ctx):
    if await self.check_connect_channel(ctx, True):
      return
    status = self.audio_status.get(ctx.guild.id)
    await status.stop()
    await ctx.channel.send("```再生を中止しました```")


  @commands.command(name='next', brief='再生リストモードの場合、今の曲をスキップし、再生リスト中の次の曲を再生する。')
  async def next(self, ctx):
    if await self.check_connect_channel(ctx, True):
      return
    status = self.audio_status.get(ctx.guild.id)
    if status.mode == 'single':
      await ctx.channel.send("```シングルモードです```")
      return
    ctx.guild.voice_client.stop()


  @commands.command(name='loop', brief='ループ再生する。')
  async def loop(self, ctx):
    if await self.check_connect_channel(ctx, False):
      return
    status = self.audio_status.get(ctx.guild.id)
    if status.loop:
      if status.mode == 'single':
        await ctx.channel.send('```すでに{} をループ再生しています```'.format(status.now_title))
      else:
        await ctx.channel.send('```すでに再生リストをループ再生しています```')
      return
    status.loop = 1
    if status.mode == 'single':
      await ctx.channel.send('```{} をループ再生します```'.format(status.now_title))
    else:
      await ctx.channel.send('```再生リストをループ再生します```')


  @commands.command(name='unloop', brief='ループを停止する。')
  async def unloop(self, ctx):
    if await self.check_connect_channel(ctx, False):
      return 
    status = self.audio_status.get(ctx.guild.id)
    if not status.loop:
      await ctx.channel.send('```ループ再生していません```'.format(status.now_title))
      return
    status.loop = 0
    await ctx.channel.send('```ループ解除します```'.format(status.now_title))


async def setup(bot):
  await bot.add_cog(AudioCog(bot))