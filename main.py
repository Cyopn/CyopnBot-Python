from discord import Intents, Game, Status
from discord.ext import commands
import os
import keep as k
from dotenv import load_dotenv

i=Intents.all()

client=commands.Bot(command_prefix='+', intents=i)

@client.event
async def on_ready():
    print(f'Listo \nIniciado en {client.user}')
    
    """ e=[1000, 1000*500] """
    g=Game(name='+help | Hola', extra=[1000, 1000*5000])
    await client.change_presence(activity=g, status=Status.dnd)
    
@client.event
async def on_message(msg):
    if msg.author ==client.user or msg.author.bot:
        return
    await client.process_commands(msg)

client.load_extension(name='cogs.fun')
client.load_extension(name='cogs.music')
client.load_extension(name='cogs.guild')

load_dotenv()

k.keep_alive()

client.run(os.getenv("token"))
