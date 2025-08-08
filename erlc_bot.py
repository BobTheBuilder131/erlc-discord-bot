import requests
import discord
import asyncio
import time
import os
from aiohttp import web
import datetime

# --- CONFIGURATION ---
DISCORD_BOT_TOKEN = os.environ['DISCORD_BOT_TOKEN']
DISCORD_CHANNEL_ID = int(os.environ['DISCORD_CHANNEL_ID'])
ERLC_API_KEY = os.environ['ERLC_API_KEY']
JOIN_SERVER_URL = "https://policeroleplay.community/join/NSRPLive"

# --- URLs for your images ---
SESSIONS_BANNER_URL = "https://media.discordapp.net/attachments/1377899647993122842/1403170076307492985/image.png"
FOOTER_IMAGE_URL = "https://media.discordapp.net/attachments/1377899647993122842/1397599002991530157/NSRP_Line_ending-Photoroom.png"
# ----------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# The web server to keep the port open
async def handle(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    # Get the port from Render's environment variable, default to 8080 if not found
    port = int(os.environ.get('PORT', 8080))
    print(f"Attempting to start web server on 0.0.0.0:{port}") # NEW: Debugging print
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server started successfully on port {port}") # NEW: Debugging print

class JoinButtonView(discord.ui.View):
    def __init__(self, url):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Join Server", style=discord.ButtonStyle.link, url=url))

def get_data(endpoint):
    url = f"https://api.policeroleplay.community/v1/server/{endpoint}"
    headers = {"server-key": ERLC_API_KEY}
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            return res.json()
    except requests.exceptions.RequestException as e:
        print(f"API request failed for {endpoint}: {e}")
    return None

def build_embeds():
    banner_embed = discord.Embed(color=discord.Color.from_rgb(237, 29, 36))
    banner_embed.set_image(url=SESSIONS_BANNER_URL)

    players = get_data("players") or []
    queue = get_data("queue") or []
    staff = get_data("staff") or {}

    mod_names = set(staff.get("Mods", {}).values())
    admin_names = set(staff.get("Admins", {}).values())
    all_mods = mod_names.union(admin_names)

    mods_online = [p["Player"].split(":")[0] for p in players if p["Player"].split(":")[0] in all_mods]

    status_embed = discord.Embed(
        description="A message will be posted here whenever we are currently hosting a session. Please do not join the server when it is offline, you will be kicked!\n\n**Sessions are hosted daily around 5:00 PM EST!**",
        color=discord.Color.from_rgb(237, 29, 36)
    )

    last_updated_ts = f"<t:{int(time.time())}:R>"
    status_embed.add_field(name="Server Status", value=f"Last updated: {last_updated_ts}", inline=False)
    status_embed.add_field(name="Player Count", value=f"**`{len(players)}`**", inline=True)
    status_embed.add_field(name="Moderators", value=f"**`{len(mods_online)}`**", inline=True)
    status_embed.add_field(name="In Queue", value=f"**`{len(queue)}`**", inline=True)

    status_embed.set_image(url=FOOTER_IMAGE_URL)
    status_embed.set_footer(text="Nova Scotia Roleplay Utilities")

    return banner_embed, status_embed

async def update_status_loop():
    await client.wait_until_ready()
    channel = client.get_channel(DISCORD_CHANNEL_ID)
    if not channel:
        print(f"ERROR: Could not find channel with ID {DISCORD_CHANNEL_ID}.")
        return

    banner_msg = None
    status_msg = None
    view = JoinButtonView(url=JOIN_SERVER_URL)

    async for message in channel.history(limit=10):
        if message.author == client.user:
            if message.embeds and not message.embeds[0].fields:
                banner_msg = message
            elif message.embeds and message.embeds[0].fields:
                status_msg = message
        if banner_msg and status_msg:
            break

    while not client.is_closed():
        try:
            new_banner_embed, new_status_embed = build_embeds()

            if banner_msg is None:
                banner_msg = await channel.send(embed=new_banner_embed)

            if status_msg is None:
                status_msg = await channel.send(embed=new_status_embed, view=view)
            else:
                await status_msg.edit(embed=new_status_embed, view=view)

            await asyncio.sleep(60)
        except Exception as e:
            print(f"An error occurred in update_status_loop: {e}")
            banner_msg = None
            status_msg = None
            await asyncio.sleep(60)

@client.event
async def on_ready():
    print(f"Bot is logged in as {client.user}")
    client.loop.create_task(update_status_loop())
    client.loop.create_task(start_web_server())

@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    prefix = "!"

    if message.content.startswith(prefix):
        parts = message.content[len(prefix):].split(' ', 1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if command == "hello":
            await message.channel.send(f"Hello, {message.author.mention}!")
        elif command == "status":
            banner_embed, status_embed = build_embeds()
            view = JoinButtonView(url=JOIN_SERVER_URL)
            await message.channel.send(embeds=[banner_embed, status_embed], view=view)
        elif command == "playerinfo":
            if not args:
                await message.channel.send("Please provide a player name. Usage: `!playerinfo [PlayerName]`")
                return

            player_name_query = args.strip()
            players_data = get_data("players")

            if players_data is None:
                await message.channel.send("Could not retrieve player data from ERLC API. Please try again later.")
                return

            found_player = None
            for player in players_data:
                full_player_name = player["Player"].split(":")[0]
                if player_name_query.lower() == full_player_name.lower():
                    found_player = player
                    break
            
            if found_player:
                player_id = found_player.get("Player").split(":")[1] if ":" in found_player.get("Player") else "N/A"
                await message.channel.send(f"Player **{full_player_name}** is currently **online** (ID: `{player_id}`).")
            else:
                await message.channel.send(f"Player **{player_name_query}** is not currently online.")

client.run(DISCORD_BOT_TOKEN)
