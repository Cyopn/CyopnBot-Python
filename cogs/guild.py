from discord.ext import commands
import discord
from datetime import datetime
''' from pymongo import MongoClient '''
import os

class Servidor(commands.Cog):
    def __init__(self, bot:commands.Bot) :
        self.bot=bot
    
    @commands.command(name='ping')
    async def _ping(self, ctx):
        """Conoce la velocidad de respuesta del bot."""
        await ctx.reply(f'Pong! {round(self.bot.latency*1000)}ms')
        
    @commands.command(name='ban')
    @commands.has_permissions(ban_members = True)
    async def _ban(self, ctx, usuario: discord.Member, *, razon:str):
        """Banea a un miembro del servidor."""
        user=usuario
        reason=razon
        await ctx.guild.ban(user, reason=reason)
        await user.send(f'Fuiste baneado del servidor {ctx.guild}, razon: {reason}')
        await ctx.send(f'El usuario {user} fue baneado')
        
    @commands.command(name='unban')
    async def _unban(self, ctx, *, miembro:str):
        """Desbanea a un miembro del servidor."""
        member=miembro
        banned_users = await ctx.guild.bans()
        member_name, member_discriminator = member.split('#')

        for ban_entry in banned_users:
            user = ban_entry.user
  
        if (user.name, user.discriminator) == (member_name, member_discriminator):
            await ctx.guild.unban(user)
            await ctx.send(f"El usuario {user} fue desbaneado")
            
    @commands.command(name='suport', aliases=['sp'])
    async def _suport(self, ctx):
        """Recibe ayuda en caso de un mal funcionamiento del bot."""
        embed=(discord.Embed(
            title='Soporte',
            description=f'Si tienes alguna duda sobre el bot, usa `+help`\nSi existe algun problema [contactame](https://instagram.com/Cyopn_), si no, unete al servidor de [soporte](https://discord.gg/qDBEhdskJP)',
            color=discord.Color.random(),
            timestamp=datetime.utcnow())
            .set_footer(text='CyopnBot', icon_url='https://avatars.githubusercontent.com/u/77410038'))
        await ctx.send(embed=embed)
        ''' 
    @commands.command(name='pin')
    async def _pin(self, ctx, *, valor:str):
        """Comando en desarrollo(No tiene funcion especifica)"""
        value=valor
        mongo_url=os.environ['mongo_uri']
        cluster=MongoClient(mongo_url)
        db=cluster['cbdata']
        collection=db['database']
        pin_cm={'id':str(ctx.author.id), 'value':value}
        collection.insert(pin_cm)
        await ctx.reply('Pin registrado') '''

def setup(bot:commands.Bot):
    bot.add_cog(Servidor(bot))  