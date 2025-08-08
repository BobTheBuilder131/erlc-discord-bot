import requests
import discord
import asyncio
import time
import os
from aiohttp import web # New: Import aiohttp for the web server

# --- CONFIGURATION ---
DISCORD_BOT_TOKEN = os.environ['DISCORD_BOT_TOKEN']
DISCORD_CHANNEL_ID = int(os.environ['DISCORD_CHANNEL_ID'])
ERLC_API_KEY = os.environ['ERLC_API_KEY']
JOIN_SERVER_URL = "https://policeroleplay.community/join/NSRPLive" # <-- IMPORTANT: Put your button link here

# --- URLs for your images ---
SESSIONS_BANNER_URL = "https://media.discordapp.net/attachments/1377899647993122842/1403170076307492985/image.png"
FOOTER_IMAGE_URL = "https://media.discordapp.net/attachments/1377899647993122842/1397599002991530157/NSRP_Line_ending-Photoroom.png"
# ----------------------------------------------------

intents = discord.Intents.default()
client = discord.Client(intents=intents)

# New: The web server to keep the port open
async def handle(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get('PORT', 8080)))
    await site.start()

class JoinButtonView(discord.ui.View):
    def __init__(self, url):
        super().__init__(timeout=None) # Timeout=None makes the button persistent
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
    # --- Embed 1: The Banner ---
    banner_embed = discord.Embed(color=discord.Color.from_rgb(237, 29, 36))
    banner_embed.set_image(url=SESSIONS_BANNER_URL)

    # --- Embed 2: The Status ---
    players = get_data("players") or []
    queue = get_data("queue") or []
    staff = get_data("staff") or {}

    mod_names = set(staff.get("Mods", {}).values())
    admin_names = set(staff.get("Admins", {}).values())
    all_mods = mod_names.union(admin_names)

    mods_online = [p["Player"].split(":")[0] for p in players if p["Player"].split(":")[0] in all_mods]

    status_embed = discord.Embed(
        description="A message will be posted here whenever we are currently hosting a session. Please do not join the server when it is offline, you will be kicked!\n\n**Sessions are hosted daily around <t:1672534800:t>!**",
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

    # Try to find previous messages to edit
    async for message in channel.history(limit=10):
        if message.author == client.user:
            # The top message will have an embed with an image but no fields
            if message.embeds and not message.embeds[0].fields:
                banner_msg = message
            # The bottom message will have fields
            elif message.embeds and message.embeds[0].fields:
                status_msg = message
        if banner_msg and status_msg:
            break

    while not client.is_closed():
        try:
            new_banner_embed, new_status_embed = build_embeds()

            # If the banner doesn't exist, send it ONCE and then leave it alone.
            if banner_msg is None:
                banner_msg = await channel.send(embed=new_banner_embed)

            # Always edit the status message. If it doesn't exist, send it first.
            if status_msg is None:
                status_msg = await channel.send(embed=new_status_embed, view=view)
            else:
                await status_msg.edit(embed=new_status_embed, view=view)

            await asyncio.sleep(60) 
        except Exception as e:
            print(f"An error occurred: {e}")
            # Reset on error so it can try to find/resend the messages
            banner_msg = None
            status_msg = None
            await asyncio.sleep(60)

@client.event
async def on_ready():
    print(f"Bot is logged in as {client.user}")
    client.loop.create_task(update_status_loop())
    client.loop.create_task(start_web_server()) # New: Start the web server

client.run(DISCORD_BOT_TOKEN)
