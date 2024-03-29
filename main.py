import discord
from discord.ext import commands
import os
from keep_alive import keep_alive
from apv1 import AudioCog

TOKEN = os.environ['DISCORD_TOKEN']

intents = discord.Intents.default()
intents.message_content = True

class MyhelpCommand(commands.HelpCommand):

  def __init__(self):
    super().__init__(command_attrs={"brief": "ヘルプを表示"})

  async def send_bot_help(self, mapping) -> None:
    cmds = []
    for cogs in mapping.values():
      for cmd in cogs:
        cmds.append(cmd) 

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

@bot.event
async def setup_hook():
  await bot.load_extension("apv1")

keep_alive()
bot.run(TOKEN)