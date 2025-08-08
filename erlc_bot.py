import requests
import discord
import asyncio
import time
import os
from aiohttp import web # Import aiohttp for the web server
import datetime # Used for adding timestamps to status updates

# --- CONFIGURATION ---
DISCORD_BOT_TOKEN = os.environ['DISCORD_BOT_TOKEN']
DISCORD_CHANNEL_ID = int(os.environ['DISCORD_CHANNEL_ID'])
ERLC_API_KEY = os.environ['ERLC_API_KEY']
JOIN_SERVER_URL = "https://policeroleplay.community/join/NSRPLive" # <-- IMPORTANT: Put your button link here

# --- URLs for your images --
SESSIONS_BANNER_URL = "https://media.discordapp.net/attachments/1377899647993122842/1403170076307492985/image.png"
FOOTER_IMAGE_URL = "https://media.discordapp.net/attachments/1377899647993122842/1397599002991530157/NSRP_Line_ending-Photoroom.png"
# ----------------------------------------------------

# Enable message_content intent for the bot to read message content
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# The web server to keep the port open (required for Render's free Web Service)
async def handle(request):
    """
    Handles incoming web requests to keep the Render service alive.
    Returns a simple text response.
    """
    return web.Response(text="Bot is running!")

async def start_web_server():
    """
    Starts a small aiohttp web server to listen on the assigned port.
    This is necessary for Render's free Web Service tier to keep the bot alive.
    """
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    # Get the port from Render's environment variable, default to 8080 if not found
    port = int(os.environ.get('PORT', 8080))
    print(f"Attempting to start web server on 0.0.0.0:{port}")
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server started successfully on port {port}")

class JoinButtonView(discord.ui.View):
    """
    A Discord UI View containing a persistent button to join the server.
    """
    def __init__(self, url):
        super().__init__(timeout=None) # Timeout=None makes the button persistent
        self.add_item(discord.ui.Button(label="Join Server", style=discord.ButtonStyle.link, url=url))

def get_data(endpoint):
    """
    Synchronously fetches data from the ERLC API.
    """
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
    """
    Builds the Discord embeds for the session banner and server status.
    """
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
    """
    Background task to periodically update the server status message in Discord.
    """
    await client.wait_until_ready()
    channel = client.get_channel(DISCORD_CHANNEL_ID)
    if not channel:
        print(f"ERROR: Could not find channel with ID {DISCORD_CHANNEL_ID}.")
        return

    banner_msg = None
    status_msg = None
    view = JoinButtonView(url=JOIN_SERVER_URL)

    # Try to find previous messages to edit
    async for message in channel.history(limit=10): # Limit history search to reduce API calls
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
            print("Bot loop: Attempting to build embeds...")
            new_banner_embed, new_status_embed = build_embeds()
            print("Bot loop: Embeds built. Attempting to send/edit message...")

            # If the banner doesn't exist, send it ONCE and then leave it alone.
            if banner_msg is None:
                banner_msg = await channel.send(embed=new_banner_embed)

            # Always edit the status message. If it doesn't exist, send it first.
            if status_msg is None:
                status_msg = await channel.send(embed=new_status_embed, view=view)
            else:
                await status_msg.edit(embed=new_status_embed, view=view)
            
            print("Bot loop: Message sent/edited successfully.")
            await asyncio.sleep(60) # Update every 60 seconds
        except Exception as e:
            print(f"CRITICAL ERROR IN UPDATE LOOP: {e}")
            # Reset on error so it can try to find/resend the messages
            banner_msg = None
            status_msg = None
            await asyncio.sleep(60) # Wait before retrying

@client.event
async def on_ready():
    """
    Event handler for when the bot successfully connects to Discord.
    Starts background tasks.
    """
    print(f"Bot is logged in as {client.user}")
    client.loop.create_task(update_status_loop())
    client.loop.create_task(start_web_server()) # Start the web server

@client.event
async def on_message(message: discord.Message):
    """
    Event handler for when a message is sent in a Discord channel.
    Handles bot commands.
    """
    # Ignore messages from the bot itself
    if message.author == client.user:
        return

    # Define your command prefix
    prefix = "!"

    # Check if the message starts with the prefix
    if message.content.startswith(prefix):
        # Attempt to delete the user's command message
        try:
            await message.delete()
            print(f"Deleted command message from {message.author}: {message.content}")
        except discord.Forbidden:
            print(f"Bot lacks 'Manage Messages' permission to delete message from {message.author}.")
            await message.channel.send("I need 'Manage Messages' permission to delete your command!", delete_after=10)
        except discord.HTTPException as e:
            print(f"Failed to delete message: {e}")

        # Split the message into command and arguments
        parts = message.content[len(prefix):].split(' ', 1)
        command = parts[0].lower()
        # args = parts[1] if len(parts) > 1 else "" # Not strictly needed for these commands

        if command == "debug": # New: !debug command
            # This will print a message to the Render logs
            debug_message = f"DEBUG command received from {message.author} in #{message.channel.name}. Current time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            print(debug_message)
            # Send debug info privately to the user
            try:
                await message.author.send(f"Debug log message sent to Render console. Check the service logs! \n\n`{debug_message}`")
            except discord.Forbidden:
                await message.channel.send(f"{message.author.mention}, I couldn't DM you. Debug info sent to console.", delete_after=10)
        elif command == "update": # New: !update command
            # This triggers an immediate update of the status message
            print(f"UPDATE command received from {message.author} in #{message.channel.name}. Triggering immediate status refresh.")
            
            channel = client.get_channel(DISCORD_CHANNEL_ID)
            if not channel:
                await message.author.send("Error: Could not find the designated status channel for update.")
                return

            banner_msg = None
            status_msg = None
            view = JoinButtonView(url=JOIN_SERVER_URL)

            # Find existing messages to edit (similar to update_status_loop)
            async for history_message in channel.history(limit=10):
                if history_message.author == client.user:
                    if history_message.embeds and not history_message.embeds[0].fields:
                        banner_msg = history_message
                    elif history_message.embeds and history_message.embeds[0].fields:
                        status_msg = history_message
                if banner_msg and status_msg:
                    break

            try:
                new_banner_embed, new_status_embed = build_embeds()
                if banner_msg is None:
                    banner_msg = await channel.send(embed=new_banner_embed)
                if status_msg is None:
                    status_msg = await channel.send(embed=new_status_embed, view=view)
                else:
                    await status_msg.edit(embed=new_status_embed, view=view)
                # Send confirmation privately to the user
                await message.author.send("Session status updated successfully!")
            except discord.Forbidden:
                await message.channel.send(f"{message.author.mention}, I couldn't DM you. Session status updated in channel.", delete_after=10)
            except Exception as e:
                await message.author.send(f"Error updating status: {e}")
                print(f"Error in !update command: {e}")
        # You can add more elif statements for other commands here
        # elif command == "anothercommand":
        #     await message.channel.send("This is another command!")

client.run(DISCORD_BOT_TOKEN)
