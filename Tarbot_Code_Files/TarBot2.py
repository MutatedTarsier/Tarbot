import discord
import speech_recognition as sr
from yt_dlp import YoutubeDL
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from urllib.parse import urljoin
import re
import csv
import asyncio
from time import sleep
from os import path
from MyQueue import *
import math
import os # for env variables
from dotenv import load_dotenv

# Load environment vars
load_dotenv()

# Spotify authentication
clientSecret = os.getenv("CLIENT_SECRET")
client_credentials_manager = SpotifyClientCredentials(client_id="b2bc6b9bb6ff4e2e82cd2d0d0bf5db6c", client_secret=clientSecret)
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

# Discord initialize
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))
    client.loop.set_debug(enabled=True)

# Bot Code
class FakeMessage: # Make a message shell to send in as NULL
        def __init__(self, content, channel, message):
            self.content = content
            self.channel = channel
            self.message = message

YDL_OPTIONS = {
        'format': 'bestaudio/best',
        'extractaudio': True,
        'audioformat': 'mp3',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': False,
        'extract_flat' : False,
        'no_warnings': False,
        'default_search': 'auto',
        'source_address': '0.0.0.0',
    }
FFMPEG_OPTIONS = {
    'options': '-vn',
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
}

# Global variables
queue = MyQueue()
stop_recording = False
taking_action = False
is_looping = False
prefix = 'tar'
music_is_playing = False
voice_con = None
prev_song = None
embed_message = [None, None]
embed_message_pages = []
embed_page_index = 0
current_thumbnail = None
emojis = ["⏩", "🛑", "🔁", "🗑️", "⬇️"]

@client.event
async def on_voice_state_update(member, before, after):
    # Check for bot leaving vc
    global voice_con, queue, is_looping, prev_song, taking_action, music_is_playing, embed_message, embed_message_pages, embed_page_index, current_thumbnail
    if after.channel is None and member==client.user:
        # Reset variables to initial state if bot leaves
        print("Bot has been Disconnected")
        queue = MyQueue()
        taking_action = False
        current_thumbnail = None
        is_looping = False
        music_is_playing = False
        if voice_con != None:
            voice_con.stop()
        voice_con = None
        prev_song = None
        if embed_message[1] != None:
            await embed_message[1].delete()
        embed_message = [None, None]
        embed_message_pages = []
        embed_page_index = 0

#
async def extract_info(url):
    split_string = url.split('/')
    is_url = False
    if 'www.youtube.com' in split_string:
        url = url[9:]
        is_url = True
    with YoutubeDL(YDL_OPTIONS) as ydl:
        info = None
        try:
            if not is_url:
                info = ydl.extract_info(url, download=False)['entries'][0]
            else:
                info = ydl.extract_info(url, download=False)
                
        except Exception:
            print("Error in extracting info")
        return info
    
async def get_vc(voice_channel, vc):
    global voice_con
    try:
        vc = await voice_channel.connect(reconnect=True)
        voice_con = vc
        return vc
    except discord.ClientException:
        print("Already in vc?")
        return voice_con
    except Exception as e:
        print(repr(e))
        taking_action = False
        return None

# Discord Functions
def Play_Next(message, vc, error):
    global is_looping, music_is_playing, prev_song
    print(error)
    prev_song = queue.dequeue()
    if is_looping:
        queue.enqueue(prev_song)
    asyncio.run_coroutine_threadsafe(update_embed(message.channel), client.loop)
    if queue.empty() == False:
        asyncio.run_coroutine_threadsafe(PlayMusic(message, queue.peek(), None, vc), client.loop)
    else:
        asyncio.run_coroutine_threadsafe(embed_message[1].delete(), client.loop)
        embed_message[0] = None
        embed_message[1] = None
        music_is_playing = False

async def playSpotify(message, voice_channel):
    global taking_action
    taking_action = True
    link = message.content[9:]
    uri = link.split('/')[-1].split("?")[0]
    try:
        for track in sp.playlist_tracks(uri)["items"]:
            name = track['track']['name']
            artist = track['track']['artists'][0]['name']
            search = name + " " + artist
            fakemessage = FakeMessage("tar play " + search, message.channel, message)
            await Play(fakemessage, 9, message.author.voice.channel)
    except Exception as e:
        print(repr(e))
        await message.channel.send("Couldn't connect to spotify")
    taking_action = False

async def PlayMusic(message, url, voice_channel, vc):
    global music_is_playing, queue, current_thumbnail
    info = url
    if type(url) is str: # Check to see if we can use url instead of extracting again
        info = await extract_info(url) # Extract info
        if info == None:
            await message.channel.send("Error in extracting info")
            return
        if queue.empty():
            queue.enqueue(url)
    current_thumbnail = info['thumbnails'][0]['url']
    # Replace name with video name
    queue.remove(1)
    queue.add(info['title'], 0)
    #
    try:
        if type(message) != FakeMessage:
            voice_channel = message.author.voice.channel
        else:
            voice_channel = message.message.author.voice.channel
    except Exception as e:
        print(repr(e))    

    vc = await get_vc(voice_channel, None)
    music_is_playing = True
    try:
        vc.play(discord.FFmpegOpusAudio(info['url'], **FFMPEG_OPTIONS), after=lambda e: Play_Next(message, vc, e))
    except discord.ClientException as e:
        await message.channel.send("Something went wrong, wait a bit")
        print(repr(e))
    await update_embed(1)

async def Remove(message):
    voice_channel = message.author.voice.channel
    remove_range = message.content[11:].split('-')
    for i in range(int(remove_range[-1]), int(remove_range[0]) - 1, -1): # Exclusive, doesn't reach first music
        if i == 1:
            vc = await get_vc(voice_channel, None)
            if vc == None:
                vc = voice_con
            vc.stop()
            print(queue.get())
            break
        elif i < 1 or i > queue.getSize():
            await message.channel.send("Music out of range")
            break
        queue.remove(i)    
    
    await update_embed(message.channel)       

async def PlayAlbum(filtered_message, message, album_key, voice_channel):
    albumName = "saved_album"
    if len(filtered_message[len(prefix + ' ' + album_key):]) != 0:
        albumName = filtered_message[len(prefix + ' ' + album_key):]
    with open(albumName + ".csv", newline="") as album:
        reader = csv.reader(album)
        for row in reader:
            fakemessage = FakeMessage("tar play " + row[0], message.channel)
            await Play(fakemessage, len("tar play "), voice_channel)

async def update_embed(message_channel):
    global embed_message, queue, current_thumbnail
    if embed_message[0] != None: 
        embed_message[0] = discord.Embed(title="Music Queue",color=discord.Colour.teal())
        embed_message[0].set_thumbnail(url=current_thumbnail)
        for embed in embed_message_pages:
            embed.clear_fields()
        queue_copy = queue.get()
        i = 0
        for music in queue_copy:
            i += 1
            music_name = music[:9] == "ytsearch:" and music[9:] or music
            if i > 10: # Max embed length
                page_number = math.floor((i - 1) / 10) - 1
                if len(embed_message_pages) <= page_number: # Create new page if max
                    embed_message_pages.append(discord.Embed(title="Music Queue",color=discord.Colour.teal()))
                # Add info to corresponding page number
                
                embed_message_pages[page_number].add_field(name=str(i) + ". " + music_name, inline=False, value="")
            else: # Normally add to first embed
                embed_message[0].add_field(name=str(i) + ". " + music_name, inline=False, value="")
        if embed_page_index == 0:
            await embed_message[1].edit(embed=embed_message[0])
        else:
            await embed_message[1].edit(embed=embed_message_pages[embed_page_index - 1])

async def Play(message, prefix_len, voice_channel):
    # Create embed if there is none
    if embed_message[0] == None:
        embed_message[0] = discord.Embed(title="Music Queue", color=discord.Colour.teal(), description="Loading music...")
        embed_message[1] = await message.channel.send(embed=embed_message[0])
        await asyncio.gather(*[embed_message[1].add_reaction(emoji) for emoji in emojis])
    
    # Play music
    url = "ytsearch:%s" % message.content[prefix_len:]
    if queue.empty(): # Only runs if first play
        await PlayMusic(message, url, voice_channel, None)
    else:
        queue.enqueue(url)
    
async def RemoveAlbum(message, filtered_message):
    position = int(message.content[17:])
    temp_album = []
    albumName = "saved_album"
    # if len(filtered_message[len(prefix + ' ' + "remove album"):]) != 0:
    #     albumName = filtered_message[len(prefix + ' ' + "remove album"):]
    with open(albumName + ".csv", newline="") as album:
        reader = csv.reader(album)
        for row in reader:
            temp_album.append(row)
        try:
            removed = temp_album.pop(position - 1)
            await message.channel.send("Removed %s from album" % removed[0])  
        except:
            await message.channel.send("That ain't a number or it's not part of the album")  
    with open(albumName + ".csv", "w", newline="") as album:
        writer = csv.writer(album)
        for song in temp_album:
            writer.writerow(song)

# Menu interaction events
@client.event
async def on_reaction_add(reaction, user):
    global embed_page_index, embed_message, embed_message_pages, is_looping, music_is_playing, queue, taking_action, prev_song, voice_con
    if user == client.user : return
# NEXT PAGE
    if reaction.emoji == '▶️' and reaction.message == embed_message[1]:
        if embed_page_index < len(embed_message_pages):
            embed_page_index += 1
        await embed_message[1].remove_reaction('▶️', user)
        await update_embed(reaction.message.channel)
# LAST PAGE
    elif reaction.emoji == '◀️' and reaction.message == embed_message[1]:
        if embed_page_index > 0:
            embed_page_index += -1
        await embed_message[1].remove_reaction('◀️', user)
        await update_embed(reaction.message.channel)
# SKIP
    elif reaction.emoji == '⏩' and reaction.message == embed_message[1]:
        voice_channel = user.voice.channel
        if voice_channel == None: return
        vc = await get_vc(voice_channel, None)
        if vc == None:
            vc = voice_con
        vc.stop()
        await embed_message[1].remove_reaction('⏩', user)
        await update_embed(reaction.message.channel)
# PAUSE / RESUME
    elif reaction.emoji == '🛑' and reaction.message == embed_message[1]:
        if reaction.count > 2:
            await embed_message[1].remove_reaction('🛑', user)
        else:
            voice_channel = user.voice.channel
            if voice_channel == None: return
            vc = await get_vc(voice_channel, None)
            if vc == None:
                vc = voice_con
            vc.pause()
            
# LOOP
    elif reaction.emoji == '🔁' and reaction.message == embed_message[1]:
        if reaction.count > 2:
            await embed_message[1].remove_reaction('🔁', user)
        else:
            is_looping = True
# CLEAR
    elif reaction.emoji == '🗑️' and reaction.message == embed_message[1]:
        queue = MyQueue()
        voice_channel = user.voice.channel
        vc = await get_vc(voice_channel, None)
        if vc == None:
            vc = voice_con
        else:
            vc.stop()
        is_looping = False
        music_is_playing = False
        await asyncio.sleep(1)
        taking_action = False
        prev_song = None
        embed_message = [None, None]
        embed_message_pages = []
        embed_page_index = 0
# RESEND
    elif reaction.emoji == '⬇️' and reaction.message == embed_message[1]:
        await update_embed(1)
        message_channel = embed_message[1].channel
        await embed_message[1].delete()
        if embed_page_index == 0:
            embed_message[1] = await message_channel.send(embed=embed_message[0])
        else:
            embed_message[1] = await message_channel.send(embed=embed_message_pages[embed_page_index - 1])
        await asyncio.gather(*[embed_message[1].add_reaction(emoji) for emoji in emojis])
        
    await asyncio.sleep(0)

@client.event
async def on_reaction_remove(reaction, user):
    global embed_page_index, embed_message, embed_message_pages, is_looping, music_is_playing
    if user == client.user : return
    if reaction.emoji == '🛑' and reaction.message == embed_message[1] and reaction.count == 1:
        voice_channel = user.voice.channel
        if voice_channel == None: return
        vc = await get_vc(voice_channel, None)
        if vc == None:
            vc = voice_con
        vc.resume()
    elif reaction.emoji == '🔁' and reaction.message == embed_message[1] and reaction.count == 1:
        is_looping = False
    await asyncio.sleep(0)

@client.event
async def on_message(message):
    global taking_action, music_is_playing, is_looping, queue, embed_message_pages, embed_message, embed_page_index
    if message.author == client.user: # Don't read bot messages
        return
    filtered_message = message.content.lower()
    
    if filtered_message.startswith(prefix): # Check for prefix first before responding
        if taking_action: # Fool proofing
            await message.channel.send("Bitch wait")
            return
        taking_action = True
    else:
        return
    voice_channel = None
    try:
        voice_channel = message.author.voice.channel
    except:
        await message.channel.send("You're not in a voice channel")
        taking_action = False
        return
    
    if filtered_message.startswith(prefix + ' play'):
# PLAY ALBUM  
        album_key = 'play album'      
        if filtered_message.startswith(prefix + ' ' + album_key):
            await PlayAlbum(filtered_message, message, album_key, voice_channel)
# PLAY / PLAY SPOTIFY
        else:
            if "spotify" in filtered_message.split('.'):
                await playSpotify(message, voice_channel)
            else:
                await Play(message, 9, voice_channel)
        if queue.getSize() > 10 and embed_message[1] != None and not ("◀️" in embed_message[1].reactions):
            await asyncio.gather(
                *[
                    embed_message[1].add_reaction("◀️"),
                    embed_message[1].add_reaction("▶️")
                ]
            )
    await update_embed(message.channel)
# SHOW ALBUM
    if filtered_message.startswith(prefix + ' show album'):
        albumName = "saved_album"
        # if len(filtered_message[len(prefix + ' ' + "show album"):]) != 0:
        #     albumName = filtered_message[len(prefix + ' ' + "show album"):]
        with open(albumName + ".csv", newline="") as album:
            reader = csv.reader(album)
            index = 1
            for row in reader:
                
                await message.channel.send(str(index) + ". " + str(row[0]))
                index += 1
# SHOW QUEUE  
    # if filtered_message.startswith(prefix + ' show queue'):
    #     await ShowQueue(message)
# RESTART
    if filtered_message.startswith(prefix + ' restart'):
        if music_is_playing:
            queue.add(queue.peek(), 1)
            vc = await get_vc(voice_channel, None)
            if vc == None:
                vc = voice_con
            vc.stop()
# REPLAY
    if filtered_message.startswith(prefix + ' replay'):
        if prev_song == None:
            await message.channel.send("Song isn't over yet")
        else:
            queue.enqueue(prev_song)
            await update_embed(message.channel)
# RESUME
    if filtered_message.startswith(prefix + ' resume'):
        vc = await get_vc(voice_channel, None)
        if vc == None:
            vc = voice_con
        try:
            if vc != None:
                vc.resume()
                await embed_message[1].clear_reaction("🛑")
        except Exception:
            pass
# PAUSE
    if filtered_message.startswith(prefix + ' pause'):
        vc = await get_vc(voice_channel, None)
        if vc == None:
            vc = voice_con
        if music_is_playing == True:
            vc.pause()
            await embed_message[1].add_reaction("🛑")
        else:
            await message.channel.send("Music isn't playing")
# ADD
    if filtered_message.startswith(prefix + ' add'):
        await message.channel.send("Adding to album...")
        albumName = "saved_album"
        with open(albumName + ".csv", "a", newline="") as album:
            writer = csv.writer(album)
            info = await extract_info("ytsearch:%s" % message.content[8:])
            writer.writerow([info['title'], info['url']])
        await message.channel.send("Added to saved album")
# REMOVE ALBUM
    if filtered_message.startswith(prefix + ' remove album'):
        await RemoveAlbum(message, filtered_message)
# REMOVE
    elif filtered_message.startswith(prefix + ' remove'):
        if not queue.empty():
            await Remove(message)
        else:
            await message.channel.send("No music to remove")
# SWAP ALBUM
    if filtered_message.startswith(prefix + ' swap album'):
        positions = [int(s) - 1 for s in re.findall(r'\b\d+\b', message.content[15:])]
        temp_album = []
        albumName = "saved_album"
        with open(albumName + ".csv", newline="") as album:
            reader = csv.reader(album)
            for row in reader:
                temp_album.append(row)
            try:
                first_song = temp_album[positions[0]]
                second_song = temp_album[positions[1]]
                dummy = first_song
                temp_album[positions[0]] = second_song
                temp_album[positions[1]] = dummy
                await message.channel.send("Swapped %s with %s" % (first_song[0], second_song[0]))  
            except:
                await message.channel.send("That ain't a number or it's not part of the queue")  
        with open(albumName + ".csv", "w", newline="") as album:
            writer = csv.writer(album)
            for song in temp_album:
                writer.writerow(song)
# SWAP
    if filtered_message.startswith(prefix + ' swap'):
        positions = [int(s) - 1 for s in re.findall(r'\b\d+\b', message.content[9:])]
        if queue.getSize() >= 2 and positions[0] >= 1 and positions[1] <= queue.getSize():
            if positions[0] == 1 or positions[1] == 1:
                await message.channel.send("Can't swap the current song")
            else:
                queue.add(queue.remove(positions[0]), positions[1] - 1)
                queue.add(queue.remove(positions[1] - 1), positions[0] - 1)
                await update_embed(message.channel)
# JOIN
    if filtered_message.startswith(prefix + ' join'):
        global stop_recording
        vc = await get_vc(voice_channel, None)
        stop_recording = False
        asyncio.run_coroutine_threadsafe(StartRecordingGlob(vc), client.loop)

# HELP
    if filtered_message.startswith(prefix + ' help'):
        await message.channel.send(
'''```ansi
 [2;33m%(key)s [0m[2;34mplay [0m          [2;32m[song name / link][0m    :  [2;36mAdds to music queue [0m
 [2;33m%(key)s [0m[2;34madd [0m           [2;32m[song name / link][0m    :  [2;36mAdds to saved album [0m
 [2;33m%(key)s [0m[2;34mplay album [0m                          :  [2;36mAdds  album to current queue [0m
 [2;33m%(key)s [0m[2;34mswap [0m          [2;32m[position] [position] [0m:  [2;36mSwap queue positions [0m
 [2;33m%(key)s [0m[2;34mswap album[0m     [2;32m[position] [position] [0m:  [2;36mSwap album positions [0m
 [2;33m%(key)s [0m[2;34mremove [0m        [2;32m[queue position] [0m     :  [2;36mRemoves song at position [0m
 [2;33m%(key)s [0m[2;34mremove album [0m  [2;32m[album position] [0m     :  [2;36mRemoves song in album [0m
 [2;33m%(key)s [0m[2;34mshow album [0m                          :  [2;36mShow current album [0m
 [2;33m%(key)s [0m[2;34mrestart [0m                             :  [2;36mReplay current song [0m
 [2;33m%(key)s [0m[2;34mreplay  [0m                             :  [2;36mAdd previous song to queue[0m
```''' % {"key": prefix})
        await asyncio.sleep(0)
    taking_action = False


token = os.getenv("TOKEN")
client.run(token)