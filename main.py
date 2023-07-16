from discord import Intents, Game, Status
from discord.ext import commands
import os
import keep as k
from dotenv import load_dotenv

i = Intents.all()
i.message_content = True

client = commands.Bot(command_prefix='+', intents=i)


@client.event
async def on_ready():
    print(f'Listo \nIniciado en {client.user}')
    g = Game(name='+help | Hola', extra=[1000, 1000 * 5000])
    await client.change_presence(activity=g, status=Status.dnd)


@client.event
async def setup_hook() -> None:  #overwriting a handler
    print(f"\033[31mLogged in as {client.user}\033[39m")
    cogs_folder = f"{os.path.abspath(os.path.dirname(__file__))}/cogs"
    for filename in os.listdir(cogs_folder):
        if filename.endswith(".py"):
            await client.load_extension(f"cogs.{filename[:-3]}")
    await client.tree.sync()
    print("Loaded cogs")


load_dotenv()

k.keep_alive()

client.run(os.getenv("token"))
