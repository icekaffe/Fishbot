# Smish Fishing Bot
# Fully integrated Telegram fishing bot with rods, baits, shop, cooldown, inventory, leaderboard

import random
import json
import os
import time
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

LEADERBOARD_FILE = "leaderboard.json"
BASE_FISH_LIMIT = 3
TIME_WINDOW = 60 * 60  # 1 hour

leaderboard = {}
fishing_log = defaultdict(list)

rod_stats = {
    "Basic Rod": {"price": 0, "bonus": 0},
    "Sturdy Rod": {"price": 50, "bonus": 1},
    "Lucky Rod": {"price": 75, "bonus": 1},
    "Mystic Rod": {"price": 100, "bonus": 1},
    "Golden Rod": {"price": 150, "bonus": 2}
}

bait_stats = {
    "Worm": {"price": 0, "rarity": {"Common": 0.85, "Rare": 0.15}},
    "Bread": {"price": 5, "rarity": {"Common": 0.6, "Rare": 0.3, "Epic": 0.1}},
    "Insect": {"price": 8, "rarity": {"Common": 0.4, "Rare": 0.4, "Epic": 0.2}},
    "Golden Bug": {"price": 15, "rarity": {"Common": 0.2, "Rare": 0.5, "Epic": 0.3}},
    "Mystic Bait": {"price": 25, "rarity": {"Common": 0.05, "Rare": 0.45, "Epic": 0.45, "ultra_bonus": 0.05}}
}

rarity_multipliers = {"Common": 1, "Rare": 2, "Epic": 5}
rarity_sell_values = {"Common": 1, "Rare": 3, "Epic": 6}
ultra_coin_bonus = 10

fish_data = {
    "Common": {
        "normal": [{"species": "Carp", "emoji": "\U0001F41F", "min_weight": 1, "max_weight": 3, "min_length": 30, "max_length": 50}],
        "ultra": []
    },
    "Rare": {
        "normal": [{"species": "Pike", "emoji": "\U0001F408", "min_weight": 3, "max_weight": 6, "min_length": 50, "max_length": 80}],
        "ultra": [{"species": "Golden Eel", "emoji": "\u26A1", "min_weight": 4, "max_weight": 6, "min_length": 60, "max_length": 70}]
    },
    "Epic": {
        "normal": [{"species": "Jewel Fish", "emoji": "\U0001F48E", "min_weight": 1, "max_weight": 2, "min_length": 20, "max_length": 35}],
        "ultra": [{"species": "Leviathan", "emoji": "\U0001F409", "min_weight": 10, "max_weight": 15, "min_length": 150, "max_length": 200}]
    }
}

def choose_rarity(prob_dict):
    rand = random.random()
    cumulative = 0
    for rarity, prob in prob_dict.items():
        if rarity == "ultra_bonus": continue
        cumulative += prob
        if rand < cumulative:
            return rarity
    return "Common"

def get_user(user_id, name):
    return leaderboard.setdefault(str(user_id), {
        "name": name,
        "points": 0,
        "coins": 20,
        "inventory": {"baits": {}, "gear": [], "fish": []},
        "rod": "Basic Rod"
    })

def get_fish_limit(user):
    rod = user.get("rod", "Basic Rod")
    bonus = rod_stats.get(rod, {}).get("bonus", 0)
    return BASE_FISH_LIMIT + bonus

def load_leaderboard():
    if os.path.exists(LEADERBOARD_FILE):
        with open(LEADERBOARD_FILE, "r") as f:
            leaderboard.update(json.load(f))

def save_leaderboard():
    with open(LEADERBOARD_FILE, "w") as f:
        json.dump(leaderboard, f)

async def start_fishing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    name = update.message.from_user.first_name
    user = get_user(user_id, name)
    now = time.time()
    fishing_log[user_id] = [ts for ts in fishing_log[user_id] if now - ts < TIME_WINDOW]
    if len(fishing_log[user_id]) >= get_fish_limit(user):
        next_time = min(fishing_log[user_id]) + TIME_WINDOW
        remaining = int((next_time - now) // 60)
        await update.message.reply_text(f"You've reached your rod limit! Try again in {remaining} min.")
        return
    bait_inventory = user["inventory"].get("baits", {})
    if "Worm" not in bait_inventory:
        bait_inventory["Worm"] = 0
    buttons = [
        [InlineKeyboardButton(f"{bait} ({count})", callback_data=f"bait_{bait}_{user_id}")]
        for bait, count in bait_inventory.items() if count > 0 or bait == "Worm"
    ]
    await update.message.reply_text("Choose your bait:", reply_markup=InlineKeyboardMarkup(buttons))

async def bait_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    bait = parts[1]
    user_id = int(parts[2])
    user = get_user(user_id, query.from_user.first_name)
    if bait != "Worm" and user["inventory"]["baits"].get(bait, 0) <= 0:
        await query.edit_message_text("You're out of that bait!")
        return
    if bait != "Worm": user["inventory"]["baits"][bait] -= 1
    fishing_log[user_id].append(time.time())
    rarity = choose_rarity(bait_stats[bait]["rarity"])
    is_ultra = random.random() < (0.01 + bait_stats[bait]["rarity"].get("ultra_bonus", 0))
    fish_list = fish_data[rarity]["ultra"] if is_ultra else fish_data[rarity]["normal"]
    fish = random.choice(fish_list)
    weight = round(random.uniform(fish["min_weight"], fish["max_weight"]), 2)
    length = round(random.uniform(fish["min_length"], fish["max_length"]), 1)
    base_points = int(weight * rarity_multipliers[rarity])
    bonus = 25 if is_ultra else 0
    total_points = base_points + bonus
    coin_value = rarity_sell_values[rarity] + (ultra_coin_bonus if is_ultra else 0)
    user["points"] += total_points
    user["coins"] += coin_value
    user["inventory"].setdefault("fish", []).append({"species": fish["species"], "rarity": rarity, "emoji": fish["emoji"], "value": coin_value})
    save_leaderboard()
    message = f"You used {bait} and caught a {rarity} {fish['emoji']} {fish['species']}!\nWeight: {weight} kg | Length: {length} cm\nPoints: {total_points} | Coins: {coin_value}"
    if is_ultra: message += f"\nTrophy catch! +{bonus} pts, +{ultra_coin_bonus} coins!"
    await query.edit_message_text(message)

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.message.from_user.id, update.message.from_user.first_name)
    user_id = str(update.message.from_user.id)
    buttons = [
        [InlineKeyboardButton(f"Buy {bait} ({info['price']} coins)", callback_data=f"buy_{bait}_{user_id}")]
        for bait, info in bait_stats.items() if bait != "Worm"
    ]
    rod_buttons = [
        [InlineKeyboardButton(f"Buy {rod} ({info['price']} coins) – +{info['bonus']} fish/hr", callback_data=f"buyrod_{rod}_{user_id}")]
        for rod, info in rod_stats.items() if rod != "Basic Rod"
    ]
    buttons.extend(rod_buttons)
    if user["inventory"].get("fish"):
        buttons.append([InlineKeyboardButton(f"Sell all fish ({len(user['inventory']['fish'])})", callback_data=f"sellfish_{user_id}")])
    shop_text = f"You currently have the *{user['rod']}* equipped (+{rod_stats[user['rod']]['bonus']} fish/hr)."
    await update.message.reply_text(shop_text, parse_mode="Markdown")
    await update.message.reply_text("Shop options:", reply_markup=InlineKeyboardMarkup(buttons))

async def buy_bait(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bait, uid = query.data.split("_")[1], int(query.data.split("_")[2])
    user = get_user(uid, query.from_user.first_name)
    price = bait_stats[bait]["price"]
    if user["coins"] < price:
        await query.edit_message_text("Not enough coins!")
        return
    user["coins"] -= price
    user["inventory"]["baits"][bait] = user["inventory"]["baits"].get(bait, 0) + 1
    save_leaderboard()
    await query.edit_message_text(f"You bought 1 {bait}. You now have {user['inventory']['baits'][bait]}.")

async def buy_rod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rod, uid = query.data.split("_")[1], int(query.data.split("_")[2])
    user = get_user(uid, query.from_user.first_name)
    cost = rod_stats[rod]["price"]
    if user["coins"] < cost:
        await query.edit_message_text("Not enough coins!")
        return
    user["coins"] -= cost
    user["rod"] = rod
    save_leaderboard()
    await query.edit_message_text(f"You bought and equipped {rod}! Your fishing limit is now {get_fish_limit(user)} per hour.")

async def sell_fish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = int(query.data.split("_")[1])
    user = get_user(uid, query.from_user.first_name)
    fish_list = user["inventory"].get("fish", [])
    total = sum(f["value"] for f in fish_list)
    user["coins"] += total
    user["inventory"]["fish"] = []
    save_leaderboard()
    await query.edit_message_text(f"You sold {len(fish_list)} fish for {total} coins!")

async def my_fish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.message.from_user.id, update.message.from_user.first_name)
    fish_list = user["inventory"].get("fish", [])
    if not fish_list:
        await update.message.reply_text("You have no fish.")
        return
    text = "\n".join([f"{f['emoji']} {f['species']} ({f['rarity']}) – {f['value']} coins" for f in fish_list])
    await update.message.reply_text(f"**Your Fish Inventory:**\n{text}", parse_mode="Markdown")

async def show_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.message.from_user.id, update.message.from_user.first_name)
    await update.message.reply_text(f"You have {user['coins']} coins.")

async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sorted_board = sorted(leaderboard.values(), key=lambda x: x["points"], reverse=True)
    titles = {1: "\U0001F3C6 Champion", 2: "\U0001F948 Master", 3: "\U0001F949 Pro"}
    text = "**Leaderboard:**\n"
    for i, entry in enumerate(sorted_board[:10], 1):
        title = titles.get(i, "")
        text += f"{i}. {entry['name']}: {entry['points']} pts {title}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "**Smish Fishing Bot Commands:**

"
        "🎣 /fish – Start fishing (choose your bait)
"
        "🐟 /myfish – View your caught fish
"
        "💰 /sellfish – Sell all fish (via shop button)
"
        "🛒 /shop – Buy bait, rods, and sell fish
"
        "🪙 /coins – Check your coin balance
"
        "🏆 /leaderboard – Top players with titles
"
        "❓ /help – Show this help message"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

def main():
    load_leaderboard()
    token = os.getenv("YOUR_BOT_TOKEN") or "<YOUR_BOT_TOKEN_HERE>"
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("fish", start_fishing))
    app.add_handler(CommandHandler("shop", shop))
    app.add_handler(CommandHandler("coins", show_coins))
    app.add_handler(CommandHandler("myfish", my_fish))
    app.add_handler(CommandHandler("leaderboard", show_leaderboard))
    app.add_handler(CommandHandler("help", show_help))
    app.add_handler(CallbackQueryHandler(bait_chosen, pattern="^bait_"))
    app.add_handler(CallbackQueryHandler(buy_bait, pattern="^buy_"))
    app.add_handler(CallbackQueryHandler(buy_rod, pattern="^buyrod_"))
    app.add_handler(CallbackQueryHandler(sell_fish, pattern="^sellfish_"))
    app.run_polling()

if __name__ == "__main__":
    main()
