import os
from discord.ext import commands
import praw
from dotenv import load_dotenv

load_dotenv()

class Varios(commands.Cog):
    def __init__(self, client:commands.Bot):
        self.client=client
    
    @commands.command(name='meme', aliases=['m'])
    async def _meme(self, ctx):
        """ Mira unos de los momazos publicados en r/ChingaTuMadreNoko """
        rd=praw.Reddit(
            client_id=os.getenv("c_id"),
            client_secret=os.getenv("c_st"),
            user_agent='CyopnBot by u/Cyopn',
            check_for_async=False
        )
        
        r=rd.subreddit('ChingaTuMadreNoko').random()
        await ctx.reply(r.url)
        
def setup(client:commands.Bot):
    client.add_cog(Varios(client))
        
        