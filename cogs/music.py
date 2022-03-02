import asyncio
import functools
import itertools
import random
import discord
import youtube_dl
from async_timeout import timeout
from discord.ext import commands
from datetime import datetime

youtube_dl.utils.bug_reports_message = lambda: ''

class VoiceError(Exception):
    pass

class YTDLError(Exception):
    pass

class YTDLSource(discord.PCMVolumeTransformer):
    YTDL_OPTIONS = {
        'format': 'bestaudio/best',
        'extractaudio': True,
        'audioformat': 'mp3',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0',
    }

    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn',
    }

    ytdl = youtube_dl.YoutubeDL(YTDL_OPTIONS)

    def __init__(self, ctx: commands.Context, source: discord.FFmpegPCMAudio, *, data: dict, volume: float = 0.5):
        super().__init__(source, volume)

        self.requester = ctx.author
        self.channel = ctx.channel
        self.data = data

        self.uploader = data.get('uploader')
        self.uploader_url = data.get('uploader_url')
        date = data.get('upload_date')
        self.upload_date = date[6:8] + '.' + date[4:6] + '.' + date[0:4]
        self.title = data.get('title')
        self.thumbnail = data.get('thumbnail')
        self.description = data.get('description')
        self.duration = self.parse_duration(int(data.get('duration')))
        self.tags = data.get('tags')
        self.url = data.get('webpage_url')
        self.views = data.get('view_count')
        self.likes = data.get('like_count')
        self.dislikes = data.get('dislike_count')
        self.stream_url = data.get('url')

    def __str__(self):
        return f'**{self.title}** de **{self.uploader}**.'

    @classmethod
    async def create_source(cls, ctx: commands.Context, search: str, *, loop: asyncio.BaseEventLoop = None):
        loop = loop or asyncio.get_event_loop()

        partial = functools.partial(cls.ytdl.extract_info, search, download=False, process=False)
        data = await loop.run_in_executor(None, partial)

        if data is None:
            raise YTDLError(f'No se encontraron resultados para`{search}`')

        if 'entries' not in data:
            process_info = data
        else:
            process_info = None
            for entry in data['entries']:
                if entry:
                    process_info = entry
                    break

            if process_info is None:
                raise YTDLError(f'No se encontraron resultados para `{search}`')

        webpage_url = process_info['webpage_url']
        partial = functools.partial(cls.ytdl.extract_info, webpage_url, download=False)
        processed_info = await loop.run_in_executor(None, partial)

        if processed_info is None:
            raise YTDLError(f'No se pudo oobtener `{webpage_url}`')

        if 'entries' not in processed_info:
            info = processed_info
        else:
            info = None
            while info is None:
                try:
                    info = processed_info['entries'].pop(0)
                except IndexError:
                    raise YTDLError(f'No hay resultados para `{webpage_url}`.')

        return cls(ctx, discord.FFmpegPCMAudio(info['url'], **cls.FFMPEG_OPTIONS), data=info)

    @staticmethod
    def parse_duration(duration: int):
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        duration = []
        if days > 0:
            duration.append('{} dias'.format(days))
        if hours > 0:
            duration.append('{} horas'.format(hours))
        if minutes > 0:
            duration.append('{} minutos'.format(minutes))
        if seconds > 0:
            duration.append('{} segundos'.format(seconds))

        return ', '.join(duration)


class Song:
    __slots__ = ('source', 'requester')

    def __init__(self, source: YTDLSource):
        self.source = source
        self.requester = source.requester

    def create_embed(self):
        embed = (discord.Embed(
            title=f'Reproduciendo ahora',
            description=f'{self.source.title} Pedido por {self.requester.mention} \nDuracion {self.source.duration} \nPublicado por [{self.source.uploader}]({self.source.uploader_url}) \nUrl [Click]({self.source.url})',
            color=discord.Color.random(),
            timestamp=datetime.utcnow())
        .set_thumbnail(url=self.source.thumbnail)
        .set_footer(text='CyopnBot', icon_url='https://avatars.githubusercontent.com/u/77410038'))

        return embed


class SongQueue(asyncio.Queue):
    def __getitem__(self, item):
        if isinstance(item, slice):
            return list(itertools.islice(self._queue, item.start, item.stop, item.step))
        else:
            return self._queue[item]

    def __iter__(self):
        return self._queue.__iter__()

    def __len__(self):
        return self.qsize()

    def clear(self):
        self._queue.clear()

    def shuffle(self):
        random.shuffle(self._queue)

    def remove(self, index: int):
        del self._queue[index]


class VoiceState:
    def __init__(self, bot: commands.Bot, ctx: commands.Context):
        self.bot = bot
        self._ctx = ctx

        self.current = None
        self.voice = None
        self.next = asyncio.Event()
        self.songs = SongQueue()

        self._loop = False
        self._volume = 0.5
        self.skip_votes = set()

        self.audio_player = bot.loop.create_task(self.audio_player_task())

    def __del__(self):
        self.audio_player.cancel()

    @property
    def loop(self):
        return self._loop

    @loop.setter
    def loop(self, value: bool):
        self._loop = value

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, value: float):
        self._volume = value

    @property
    def is_playing(self):
        return self.voice and self.current

    async def audio_player_task(self):
        while True:
            self.next.clear()

            if not self.loop:
                # Try to get the next song within 3 minutes.
                # If no song will be added to the queue in time,
                # the player will disconnect due to performance
                # reasons.
                try:
                    async with timeout(180):  # 3 minutes
                        self.current = await self.songs.get()
                except asyncio.TimeoutError:
                    self.bot.loop.create_task(self.stop())
                    return

            self.current.source.volume = self._volume
            self.voice.play(self.current.source, after=self.play_next_song)
            await self.current.source.channel.send(embed=self.current.create_embed())

            await self.next.wait()

    def play_next_song(self, error=None):
        if error:
            raise VoiceError(str(error))

        self.next.set()

    def skip(self):
        self.skip_votes.clear()

        if self.is_playing:
            self.voice.stop()

    async def stop(self):
        self.songs.clear()

        if self.voice:
            await self.voice.disconnect()
            self.voice = None


class Musica(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_states = {}

    def get_voice_state(self, ctx: commands.Context):
        state = self.voice_states.get(ctx.guild.id)
        if not state:
            state = VoiceState(self.bot, ctx)
            self.voice_states[ctx.guild.id] = state

        return state

    def cog_unload(self):
        for state in self.voice_states.values():
            self.bot.loop.create_task(state.stop())

    def cog_check(self, ctx: commands.Context):
        if not ctx.guild:
            raise commands.NoPrivateMessage('Este mensaje no se puede usar en DM')

        return True

    async def cog_before_invoke(self, ctx: commands.Context):
        ctx.voice_state = self.get_voice_state(ctx)

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        await ctx.send(error)

    @commands.command(name='join', invoke_without_subcommand=True)
    async def _join(self, ctx: commands.Context):
        """Conecta a un canal de voz.
        Si no se especificó ningún canal, se une a su canal."""

        destination = ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(destination)
            return

        ctx.voice_state.voice = await destination.connect()

    @commands.command(name='summon')
    @commands.has_permissions(manage_guild=True)
    async def _summon(self, ctx: commands.Context, *, canal: discord.VoiceChannel = None):
        """Conecta a un canal de voz.
        Si no se especificó ningún canal, se une a su canal.
        """
        channel=canal
        if not channel and not ctx.author.voice:
            raise VoiceError('No esta conectado a un canal de voz ni ha especificado uno')

        destination = channel or ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(destination)
            return

        ctx.voice_state.voice = await destination.connect()

    @commands.command(name='leave', aliases=['disconnect'])
    @commands.has_permissions(manage_guild=True)
    async def _leave(self, ctx: commands.Context):
        """Limpia la lista de reproduccion y abandona el canal de voz."""

        if not ctx.voice_state.voice:
            return await ctx.send('No conectado en un canal de voz')

        await ctx.voice_state.stop()
        del self.voice_states[ctx.guild.id]

    @commands.command(name='volume')
    async def _volume(self, ctx: commands.Context, *, volumen: int):
        """Establece el volumen del reproductor."""

        volume=volumen
        if not ctx.voice_state.is_playing:
            return await ctx.send('No se reproduce nada por ahora')

        if 0 > volume > 100:
            return await ctx.send('Ajusta el volumen del 0 al 100')

        ctx.voice_state.volume = volume / 100
        await ctx.send('El volumen se ajusto a {}%'.format(volume))

    @commands.command(name='now', aliases=['current', 'playing'])
    async def _now(self, ctx: commands.Context):
        """Muestra la canción que se está reproduciendo actualmente."""
        if ctx.voice_state.is_playing:
            await ctx.send(embed=ctx.voice_state.current.create_embed())
        else:
            await ctx.send('No hay nada en reproduccion')

    @commands.command(name='pause', aliases=['ps'])
    @commands.has_permissions(manage_guild=True)
    async def _pause(self, ctx: commands.Context):
        """Pausa la canción que se está reproduciendo actualmente."""

        if  ctx.voice_state.is_playing and ctx.voice_state.voice.is_playing():
            ctx.voice_state.voice.pause()
            await ctx.message.add_reaction('⏯')
        else:
            await ctx.reply('No se esta reproduciendo nada')

    @commands.command(name='resume', aliases=['rs'])
    @commands.has_permissions(manage_guild=True)
    async def _resume(self, ctx: commands.Context):
        """Reanuda una canción actualmente en pausa."""

        if ctx.voice_state.is_playing and ctx.voice_state.voice.is_paused():
            ctx.voice_state.voice.resume()
            await ctx.message.add_reaction('⏯')
        else:
            await ctx.reply('No se esta reproduciendo nada')

    @commands.command(name='stop')
    @commands.has_permissions(manage_guild=True)
    async def _stop(self, ctx: commands.Context):
        """Detiene la reproducción de la canción y borra la lista de reproduccion."""

        ctx.voice_state.songs.clear()

        if ctx.voice_state.is_playing:
            ctx.voice_state.voice.stop()
            await ctx.message.add_reaction('⏹')
        else:
            await ctx.reply('No se esta reproduciendo nada')

    @commands.command(name='skip')
    async def _skip(self, ctx: commands.Context):
        """Vota para saltarte una canción. El solicitante puede omitir automáticamente.
        Se necesitan 3 votos de omisión para omitir la canción.
        """

        if not ctx.voice_state.is_playing:
            return await ctx.send('No se reproduce nada por ahora')

        voter = ctx.message.author
        if voter == ctx.voice_state.current.requester:
            await ctx.message.add_reaction('⏭')
            ctx.voice_state.skip()

        elif voter.id not in ctx.voice_state.skip_votes:
            ctx.voice_state.skip_votes.add(voter.id)
            total_votes = len(ctx.voice_state.skip_votes)

            if total_votes >= 3:
                await ctx.message.add_reaction('⏭')
                ctx.voice_state.skip()
            else:
                await ctx.send('Voto para saltar añadido, **{}/3**'.format(total_votes))

        else:
            await ctx.send('Has votado para saltar esta cancion')

    @commands.command(name='queue', aliases=['q'])
    async def _queue(self, ctx: commands.Context):
        """Muestra la lista de reproduccion del reproductor."""

        if len(ctx.voice_state.songs) == 0:
            embed=(discord.Embed(
                title=f'Lista de reproduccion en {ctx.guild.name}',
                description=f'Lista de reproduccion vacia',
                timestamp=datetime.utcnow())
            .set_footer(text='CyopnBot', icon_url='https://avatars.githubusercontent.com/u/77410038'))
            return await ctx.send(embed=embed)
        page=1
        items_per_page = 10
        start = (page - 1) * items_per_page
        end = start + items_per_page
        queue = ''
        for i, song in enumerate(ctx.voice_state.songs[start:end], start=start):
            queue += f'`{i+1} - ` [**{song.source.title}**]({song.source.url}) pedido por {song.requester.mention})\n'

        embed = (discord.Embed(
            title=f'Lista de reproduccion en {ctx.guild.name}',
            description=f'{len(ctx.voice_state.songs)} pistas en cola\n\n{queue}',
            timestamp=datetime.utcnow())
            .set_footer(text='CyopnBot', icon_url='https://avatars.githubusercontent.com/u/77410038'))
        await ctx.send(embed=embed)

    @commands.command(name='shuffle')
    async def _shuffle(self, ctx: commands.Context):
        """Baraja la lista de reproduccion"""

        if ctx.voice_state.is_playing:
            if len(ctx.voice_state.songs) == 0:
                return await ctx.send('Lista de reproduccion vacia')

            ctx.voice_state.songs.shuffle()
            await ctx.message.add_reaction('✅')    
        else:
            await ctx.reply('No se esta reproduciendo nada')

    @commands.command(name='remove')
    async def _remove(self, ctx: commands.Context, numero: int):
        """Elimina una canción de la lista en un índice determinado."""
        
        index=numero
        if ctx.voice_state.is_playing:
            if len(ctx.voice_state.songs) == 0:
                return await ctx.send('Lista de reproduccion vacia')

            ctx.voice_state.songs.remove(index - 1)
            await ctx.message.add_reaction('✅')
        else:
            await ctx.reply('No se esta reproduciendo nada')

    @commands.command(name='loop')
    async def _loop(self, ctx: commands.Context):
        """Repite la canción que se está reproduciendo actualmente.
        Vuelva a usar este comando para dejar de repetir.
        """

        if not ctx.voice_state.is_playing:
            return await ctx.send('No se reproduce nada por ahora')

        # Inverse boolean value to loop and unloop.
        ctx.voice_state.loop = not ctx.voice_state.loop
        await ctx.message.add_reaction('✅')

    @commands.command(name='play', aliases=['p'])
    async def _play(self, ctx: commands.Context, *, busqueda: str):
        """Reproduce una canción.
        Si hay canciones en la cola, se pondrán en cola hasta que
        otras canciones terminaron de reproducirse.
        Este comando busca automáticamente en varios sitios si no se proporciona una URL.
        """

        search=busqueda
        if not ctx.voice_state.voice:
            await ctx.invoke(self._join)

        async with ctx.typing():
            try:
                source = await YTDLSource.create_source(ctx, search, loop=self.bot.loop)
            except YTDLError as e:
                await ctx.send(e)
            else:
                song = Song(source)

                await ctx.voice_state.songs.put(song)
                await ctx.send(f'Se añadio {str(source)} (Pedido por {ctx.author.mention})')

    @_join.before_invoke
    @_play.before_invoke
    async def ensure_voice_state(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandError('No esta conectado en ningun canal de voz')

        if ctx.voice_client:
            if ctx.voice_client.channel != ctx.author.voice.channel:
                raise commands.CommandError('Ya estoy en un canal de voz')

def setup(bot:commands.Bot):
    bot.add_cog(Musica(bot))