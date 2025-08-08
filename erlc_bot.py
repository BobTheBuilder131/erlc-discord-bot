import requests
import discord
import asyncio
import time
import os
from aiohttp import web
import datetime
from discord.ext import commands
from discord import app_commands

# --- CONFIGURATION ---
DISCORD_BOT_TOKEN = os.environ['DISCORD_BOT_TOKEN']
DISCORD_CHANNEL_ID = int(os.environ['DISCORD_CHANNEL_ID'])
ERLC_API_KEY = os.environ['ERLC_API_KEY']
JOIN_SERVER_URL = "https://policeroleplay.community/join/NSRPLive"

# --- URLs for your images --
SESSIONS_BANNER_URL = "https://media.discordapp.net/attachments/1377899647993122842/1403170076307492985/image.png"
FOOTER_IMAGE_URL = "https://media.discordapp.net/attachments/1377899647993122842/1397599002991530157/NSRP_Line_ending-Photoroom.png"
# ----------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

async def handle(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get('PORT', 8080))
    print(f"Attempting to start web server on 0.0.0.0:{port}")
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server started successfully on port {port}")

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
    await bot.wait_until_ready()
    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    if not channel:
        print(f"ERROR: Could not find channel with ID {DISCORD_CHANNEL_ID}.")
        return

    banner_msg = None
    status_msg = None
    view = JoinButtonView(url=JOIN_SERVER_URL)

    async for message in channel.history(limit=10):
        if message.author == bot.user:
            if message.embeds and not message.embeds[0].fields:
                banner_msg = message
            elif message.embeds and message.embeds[0].fields:
                status_msg = message
        if banner_msg and status_msg:
            break

    while not bot.is_closed():
        try:
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Bot loop: Heartbeat - Running update cycle.") # NEW: Heartbeat log
            new_banner_embed, new_status_embed = build_embeds()
            
            if banner_msg is None:
                banner_msg = await channel.send(embed=new_banner_embed)
            if status_msg is None:
                status_msg = await channel.send(embed=new_status_embed, view=view)
            else:
                await status_msg.edit(embed=new_status_embed, view=view)
            
            await asyncio.sleep(60)
        except Exception as e:
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] CRITICAL ERROR IN UPDATE LOOP: {e}")
            banner_msg = None
            status_msg = None
            await asyncio.sleep(60)

@bot.event
async def on_ready():
    print(f"Bot is logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")

    bot.loop.create_task(update_status_loop())
    bot.loop.create_task(start_web_server())

@bot.tree.command(name="hello", description="Says hello to the user!")
async def hello_command(interaction: discord.Interaction):
    await interaction.response.send_message(f"Hello, {interaction.user.mention}!", ephemeral=True)

@bot.tree.command(name="embed", description="Sends a custom embed message.")
@app_commands.describe(
    title="The title of the embed",
    description="The main text of the embed",
    color="Hex color code for the embed (e.g., #FF0000 for red)"
)
async def embed_command(
    interaction: discord.Interaction,
    title: str,
    description: str,
    color: str = "#3498DB"
):
    try:
        embed_color = int(color.lstrip('#'), 16)
    except ValueError:
        await interaction.response.send_message("Invalid color format. Please use a hex code like #FF0000.", ephemeral=True)
        return

    embed = discord.Embed(
        title=title,
        description=description,
        color=embed_color
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="playerinfo", description="Checks if a player is online in ERLC.")
@app_commands.describe(player_name="The full name of the player to check")
async def playerinfo_command(interaction: discord.Interaction, player_name: str):
    await interaction.response.defer(ephemeral=True)

    players_data = get_data("players")

    if players_data is None:
        await interaction.followup.send("Could not retrieve player data from ERLC API. Please try again later.", ephemeral=True)
        return

    found_player = None
    for player in players_data:
        full_player_name = player["Player"].split(":")[0]
        if player_name.lower() == full_player_name.lower():
            found_player = player
            break
    
    if found_player:
        player_id = found_player.get("Player").split(":")[1] if ":" in found_player.get("Player") else "N/A"
        await interaction.followup.send(f"Player **{full_player_name}** is currently **online** (ID: `{player_id}`).", ephemeral=True)
    else:
        await interaction.followup.send(f"Player **{player_name}** is not currently online.", ephemeral=True)

@bot.tree.command(name="serverinfo", description="Displays detailed information about the ERLC server.")
async def serverinfo_command(interaction: discord.Interaction):
    await interaction.response.defer()

    server_data = get_data("server")
    players_data = get_data("players")
    queue_data = get_data("queue")

    if server_data is None or players_data is None or queue_data is None:
        await interaction.followup.send("Could not retrieve server information from ERLC API. Please try again later.")
        return

    embed = discord.Embed(
        title=f"🚨 ERLC Server: {server_data.get('Name', 'N/A')} 🚨",
        color=discord.Color.from_rgb(237, 29, 36)
    )
    embed.add_field(name="Owner", value=server_data.get('OwnerUsername', 'N/A'), inline=True)
    embed.add_field(name="Current Players", value=f"`{len(players_data)}`", inline=True)
    embed.add_field(name="Max Players", value=f"`{server_data.get('MaxPlayers', 'N/A')}`", inline=True)
    embed.add_field(name="Players in Queue", value=f"`{len(queue_data)}`", inline=True)
    embed.add_field(name="Join Key", value=f"`{server_data.get('JoinKey', 'N/A')}`", inline=True)
    embed.add_field(name="Account Verified Required", value=server_data.get('AccVerifiedReq', 'N/A'), inline=True)
    embed.set_footer(text="Data from ERLC API")
    embed.timestamp = datetime.datetime.now()

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="staffonline", description="Lists currently online staff members in ERLC.")
async def staffonline_command(interaction: discord.Interaction):
    await interaction.response.defer()

    players_data = get_data("players")
    staff_data = get_data("staff")

    if players_data is None or staff_data is None:
        await interaction.followup.send("Could not retrieve staff or player data from ERLC API. Please try again later.")
        return

    mod_names = set(staff_data.get("Mods", {}).values())
    admin_names = set(staff_data.get("Admins", {}).values())
    all_staff_names = mod_names.union(admin_names)

    online_staff_list = []
    for player in players_data:
        player_name = player["Player"].split(":")[0]
        if player_name in all_staff_names:
            online_staff_list.append(player_name)
    
    if online_staff_list:
        staff_message = "👮 **Online Staff:** " + ", ".join(online_staff_list)
    else:
        staff_message = "No staff members are currently online."
    
    await interaction.followup.send(staff_message)

@bot.tree.command(name="teamcount", description="Shows a breakdown of players by team in ERLC.")
async def teamcount_command(interaction: discord.Interaction):
    await interaction.response.defer()

    players_data = get_data("players")

    if players_data is None:
        await interaction.followup.send("Could not retrieve player data from ERLC API. Please try again later.")
        return

    team_counts = {}
    for player in players_data:
        team = player.get("Team", "Unknown Team")
        team_counts[team] = team_counts.get(team, 0) + 1
    
    if team_counts:
        team_message = "👥 **Player Count by Team:**\n"
        for team, count in team_counts.items():
            team_message += f"- {team}: `{count}`\n"
    else:
        team_message = "No players currently online to count by team."
    
    await interaction.followup.send(team_message)

@bot.tree.command(name="vehicles", description="Lists all active vehicles in the ERLC server.")
async def vehicles_command(interaction: discord.Interaction):
    await interaction.response.defer()

    vehicles_data = get_data("vehicles")

    if vehicles_data is None:
        await interaction.followup.send("Could not retrieve vehicle data from ERLC API. Please try again later.")
        return

    if vehicles_data:
        vehicle_list = []
        for vehicle in vehicles_data:
            name = vehicle.get("Name", "Unnamed Vehicle")
            owner = vehicle.get("Owner", "No Owner")
            texture = vehicle.get("Texture")
            
            if texture and texture != "Default":
                vehicle_list.append(f"- `{name}` (Owner: {owner}, Texture: {texture})")
            else:
                vehicle_list.append(f"- `{name}` (Owner: {owner})")
        
        vehicles_message = "🚗 **Active Vehicles:**\n" + "\n".join(vehicle_list[:10])
        if len(vehicle_list) > 10:
            vehicles_message += f"\n...and {len(vehicle_list) - 10} more."
    else:
        vehicles_message = "No active vehicles found in the server."
    
    await interaction.followup.send(vehicles_message)


# Existing: on_message event handler for traditional prefix commands
@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    await bot.process_commands(message)

    prefix = "!"

    if message.content.startswith(prefix):
        try:
            await message.delete()
            print(f"Deleted command message from {message.author}: {message.content}")
        except discord.Forbidden:
            print(f"Bot lacks 'Manage Messages' permission to delete message from {message.author}.")
            await message.channel.send("I need 'Manage Messages' permission to delete your command!", delete_after=10)
        except discord.HTTPException as e:
            print(f"Failed to delete message: {e}")

        parts = message.content[len(prefix):].split(' ', 1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if command == "debug":
            debug_message = f"DEBUG command received from {message.author} in #{message.channel.name}. Current time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            print(debug_message)
            try:
                await message.author.send(f"Debug log message sent to Render console. Check the service logs! \n\n`{debug_message}`")
            except discord.Forbidden:
                await message.channel.send(f"{message.author.mention}, I couldn't DM you. Debug info sent to console.", delete_after=10)
        elif command == "update":
            print(f"UPDATE command received from {message.author} in #{message.channel.name}. Triggering immediate status refresh.")
            
            channel = bot.get_channel(DISCORD_CHANNEL_ID)
            if not channel:
                await message.author.send("Error: Could not find the designated status channel for update.")
                return

            banner_msg = None
            status_msg = None
            view = JoinButtonView(url=JOIN_SERVER_URL)

            async for history_message in channel.history(limit=10):
                if history_message.author == bot.user:
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
                await message.author.send("Session status updated successfully!")
            except discord.Forbidden:
                await message.channel.send(f"{message.author.mention}, I couldn't DM you. Session status updated in channel.", delete_after=10)
            except Exception as e:
                await message.author.send(f"Error updating status: {e}")
                print(f"Error in !update command: {e}")
        elif command == "refresh":
            print(f"REFRESH command received from {message.author} in #{message.channel.name}. Triggering full status refresh.")
            
            channel = bot.get_channel(DISCORD_CHANNEL_ID)
            if not channel:
                await message.author.send("Error: Could not find the designated status channel for refresh.")
                return

            # This will force the update_status_loop to re-find/re-send messages
            # by temporarily setting banner_msg and status_msg to None.
            # This is a bit of a hack but effective for a "full refresh".
            # Accessing global variables directly in an async function can be tricky.
            # It's better to make update_status_loop callable or reset its internal state.
            # For simplicity for now, we'll try to force a re-send.
            
            # To truly force a re-send, we can call the update_status_loop logic directly
            # after resetting the message pointers.
            
            # Temporarily clear the message pointers for the next update cycle
            # This is a bit tricky with the current loop structure.
            # A more robust solution would be to make update_status_loop accept arguments
            # or have a separate function to clear the message IDs.
            
            # For now, we'll just try to force the send/edit logic again.
            # The most reliable way to force a full re-send is to briefly stop and restart the loop,
            # but that's more complex.
            # A simpler approach for !refresh is to just send a new message.
            
            # Option 1: Send a new message (simpler for !refresh)
            try:
                new_banner_embed, new_status_embed = build_embeds()
                await channel.send(embed=new_banner_embed)
                await channel.send(embed=new_status_embed, view=view)
                await message.author.send("Session status fully refreshed and re-posted successfully!")
            except discord.Forbidden:
                await message.channel.send(f"{message.author.mention}, I couldn't DM you. Session status fully refreshed in channel.", delete_after=10)
            except Exception as e:
                await message.author.send(f"Error during full refresh: {e}")
                print(f"Error in !refresh command: {e}")


bot.run(DISCORD_BOT_TOKEN)
