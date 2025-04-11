import discord
from discord import app_commands
from discord.ext import commands
import random, json, asyncio, os

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

DATA_FILE = "wallets.json"
games = {}

def load_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            json.dump({"users": {}}, f)
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_user(data, user_id):
    user_id = str(user_id)
    if user_id not in data["users"]:
        data["users"][user_id] = {"gold": 1000, "wins": 0, "losses": 0}
    return data["users"][user_id]

@tree.command(name="balance", description="Check your gold balance")
async def balance(interaction: discord.Interaction):
    data = load_data()
    user = get_user(data, interaction.user.id)
    await interaction.response.send_message(f"You have **{user['gold']} gold**.")

@tree.command(name="earn", description="Earn some free gold")
async def earn(interaction: discord.Interaction):
    data = load_data()
    user = get_user(data, interaction.user.id)
    earned = random.randint(100, 500)
    user["gold"] += earned
    save_data(data)
    await interaction.response.send_message(f"You earned **{earned} gold**! You now have **{user['gold']} gold**.")

@tree.command(name="pay", description="Pay gold to another player")
@app_commands.describe(member="The user to pay", amount="Amount of gold to send")
async def pay(interaction: discord.Interaction, member: discord.Member, amount: int):
    if amount <= 0:
        await interaction.response.send_message("Amount must be positive.", ephemeral=True)
        return

    data = load_data()
    sender = get_user(data, interaction.user.id)
    receiver = get_user(data, member.id)

    if sender["gold"] < amount:
        await interaction.response.send_message("You don't have enough gold.", ephemeral=True)
        return

    sender["gold"] -= amount
    receiver["gold"] += amount
    save_data(data)

    await interaction.response.send_message(f"{interaction.user.mention} paid {member.mention} **{amount} gold**.")

@tree.command(name="deathroll", description="Challenge someone to a death roll duel")
@app_commands.describe(opponent="The person you're challenging", start="Starting roll number", bet="Gold you're wagering")
async def deathroll(interaction: discord.Interaction, opponent: discord.Member, start: int, bet: int = 0):
    if opponent.id == interaction.user.id:
        return await interaction.response.send_message("You can't challenge yourself.", ephemeral=True)

    if interaction.channel_id in games:
        return await interaction.response.send_message("There’s already a game in progress here.", ephemeral=True)

    data = load_data()
    p1 = get_user(data, interaction.user.id)
    p2 = get_user(data, opponent.id)

    if p1["gold"] < bet or p2["gold"] < bet:
        return await interaction.response.send_message("One of you doesn't have enough gold.", ephemeral=True)

    games[interaction.channel_id] = {
        "players": [interaction.user.id, opponent.id],
        "turn": interaction.user.id,
        "current_max": start,
        "bet": bet,
        "timeout_task": None
    }

    save_data(data)

    bet_msg = f" for **{bet} gold**" if bet else ""
    await interaction.response.send_message(
        f"{interaction.user.mention} has challenged {opponent.mention} to a death roll starting at {start}{bet_msg}!\n"
        f"{interaction.user.mention}, your turn! Use `/roll`."
    )
    await start_timeout(interaction.channel)

@tree.command(name="roll", description="Roll your turn in a death roll game")
async def roll(interaction: discord.Interaction):
    game = games.get(interaction.channel_id)
    if not game:
        return await interaction.response.send_message("No active death roll game.")

    if interaction.user.id != game["turn"]:
        return await interaction.response.send_message("It's not your turn!", ephemeral=True)

    if game["timeout_task"]:
        game["timeout_task"].cancel()

    roll_result = random.randint(1, game["current_max"])
    await interaction.response.send_message(f"{interaction.user.mention} rolled **{roll_result}** (1 - {game['current_max']})")

    if roll_result == 1:
        loser_id = interaction.user.id
        winner_id = [pid for pid in game["players"] if pid != loser_id][0]
        data = load_data()
        loser = get_user(data, loser_id)
        winner = get_user(data, winner_id)
        bet = game["bet"]

        loser["losses"] += 1
        winner["wins"] += 1

        if bet:
            loser["gold"] -= bet
            winner["gold"] += bet

        save_data(data)
        del games[interaction.channel_id]
        await interaction.followup.send(f"{interaction.user.mention} rolled a 1 and lost the game!\n<@{winner_id}> wins!")
    else:
        game["current_max"] = roll_result
        game["turn"] = [pid for pid in game["players"] if pid != interaction.user.id][0]
        next_player = await bot.fetch_user(game["turn"])
        await interaction.followup.send(f"{next_player.mention}, it's your turn! Use `/roll`.")
        await start_timeout(interaction.channel)

async def start_timeout(channel):
    game = games[channel.id]

    async def timeout():
        await asyncio.sleep(60)
        loser_id = game["turn"]
        winner_id = [pid for pid in game["players"] if pid != loser_id][0]
        data = load_data()
        loser = get_user(data, loser_id)
        winner = get_user(data, winner_id)

        loser["losses"] += 1
        winner["wins"] += 1

        if game["bet"]:
            loser["gold"] -= game["bet"]
            winner["gold"] += game["bet"]

        save_data(data)
        del games[channel.id]
        channel_obj = bot.get_channel(channel.id)
        await channel_obj.send(f"<@{loser_id}> took too long and forfeits the game! <@{winner_id}> wins!")

    task = asyncio.create_task(timeout())
    game["timeout_task"] = task

@bot.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {bot.user}")

# Run bot
bot.run(os.getenv("DISCORD_TOKEN"))