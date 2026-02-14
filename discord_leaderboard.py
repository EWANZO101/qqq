"""
CFRP Discord Live Leaderboard Bot
Uses the web app's local database (player_sessions table).
Updates a single embed message every 30 seconds.
"""

import discord
import asyncio
import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
CHANNEL_ID = int(os.getenv('LEADERBOARD_CHANNEL_ID', '0'))
UPDATE_INTERVAL = 30

MESSAGE_ID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.leaderboard_message_id')

# Import Flask app for DB access
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app
from models import db, PlayerSession, User


def fmt(minutes):
    if not minutes:
        return '0m'
    d = minutes // 1440
    h = (minutes % 1440) // 60
    m = minutes % 60
    parts = []
    if d > 0: parts.append(f'{d}d')
    if h > 0: parts.append(f'{h}h')
    if m > 0 or not parts: parts.append(f'{m}m')
    return ' '.join(parts)


def fetch_data():
    """Fetch all leaderboard data from local DB."""
    with app.app_context():
        try:
            now = datetime.utcnow()
            today = now.date()
            week_ago = today - timedelta(days=7)

            # Active players
            sessions = PlayerSession.query.filter_by(session_end=None).all()
            active_players = []
            seen = set()
            for s in sessions:
                if s.discord_id in seen:
                    continue
                seen.add(s.discord_id)
                mins = int((now - s.session_start).total_seconds() / 60)
                user = User.query.filter_by(discord_id=s.discord_id).first()
                active_players.append({
                    'username': user.username if user else s.player_name or 'Unknown',
                    'minutes': mins
                })

            online_count = len(active_players)

            # Unique today
            unique_today = db.session.query(
                db.func.count(db.func.distinct(PlayerSession.discord_id))
            ).filter(PlayerSession.date == today).scalar()

            # Total playtime today
            total_pt_today = db.session.query(
                db.func.coalesce(db.func.sum(PlayerSession.minutes), 0)
            ).filter(PlayerSession.date == today).scalar()

            # Today leaderboard (top 10)
            today_results = db.session.query(
                PlayerSession.discord_id,
                db.func.sum(PlayerSession.minutes).label('total')
            ).filter(PlayerSession.date == today).group_by(
                PlayerSession.discord_id
            ).order_by(db.func.sum(PlayerSession.minutes).desc()).limit(10).all()

            today_lb = []
            for discord_id, total in today_results:
                user = User.query.filter_by(discord_id=discord_id).first()
                today_lb.append({'username': user.username if user else 'Unknown', 'minutes': int(total or 0)})

            # Week leaderboard (top 10)
            week_results = db.session.query(
                PlayerSession.discord_id,
                db.func.sum(PlayerSession.minutes).label('total')
            ).filter(PlayerSession.date >= week_ago).group_by(
                PlayerSession.discord_id
            ).order_by(db.func.sum(PlayerSession.minutes).desc()).limit(10).all()

            week_lb = []
            for discord_id, total in week_results:
                user = User.query.filter_by(discord_id=discord_id).first()
                week_lb.append({'username': user.username if user else 'Unknown', 'minutes': int(total or 0)})

            # Kill leaderboard (from remote DB)
            kill_lb = []
            try:
                from utils.fivem import FiveMAdmin
                data, err = FiveMAdmin.get_kill_leaderboard('week')
                if data:
                    kill_lb = data[:10]
            except:
                pass

            return {
                'active_players': active_players,
                'online_count': online_count,
                'unique_today': unique_today,
                'total_playtime_today': int(total_pt_today),
                'today_lb': today_lb,
                'week_lb': week_lb,
                'kill_lb': kill_lb,
            }
        except Exception as e:
            print(f"[ERROR] Database query failed: {e}")
            return None


def build_embed(data):
    now = datetime.utcnow()
    embed = discord.Embed(
        title="\U0001f3ae  CFRP Server Leaderboard",
        color=0x5865F2,
        timestamp=now
    )

    status_text = f"\U0001f7e2 **{data['online_count']}** Online  \u2022  \U0001f465 **{data['unique_today']}** Unique Today  \u2022  \u23f1\ufe0f **{fmt(data['total_playtime_today'])}** Total Playtime"
    embed.description = status_text

    if data['active_players']:
        lines = [f"\U0001f7e2 **{p['username']}** \u2014 {fmt(p['minutes'])}" for p in data['active_players'][:15]]
        embed.add_field(name=f"\U0001f534 Live Players ({len(data['active_players'])})", value='\n'.join(lines), inline=False)
    else:
        embed.add_field(name="\U0001f534 Live Players", value="No players online", inline=False)

    medals = ['\U0001f947', '\U0001f948', '\U0001f949']

    if data['today_lb']:
        lines = []
        for i, p in enumerate(data['today_lb']):
            medal = medals[i] if i < 3 else f'`{i+1}.`'
            lines.append(f"{medal} **{p['username']}** \u2014 {fmt(p['minutes'])}")
        embed.add_field(name="\U0001f4ca Today's Playtime", value='\n'.join(lines), inline=True)
    else:
        embed.add_field(name="\U0001f4ca Today's Playtime", value="No data yet", inline=True)

    if data['week_lb']:
        lines = []
        for i, p in enumerate(data['week_lb']):
            medal = medals[i] if i < 3 else f'`{i+1}.`'
            lines.append(f"{medal} **{p['username']}** \u2014 {fmt(p['minutes'])}")
        embed.add_field(name="\U0001f4c8 Weekly Playtime", value='\n'.join(lines), inline=True)
    else:
        embed.add_field(name="\U0001f4c8 Weekly Playtime", value="No data yet", inline=True)

    if data['kill_lb']:
        lines = []
        for i, p in enumerate(data['kill_lb']):
            medal = medals[i] if i < 3 else f'`{i+1}.`'
            lines.append(f"{medal} **{p.get('username','Unknown')}** \u2014 {p.get('kills',0)}K / {p.get('deaths',0)}D ({p.get('kd_ratio','0')})")
        embed.add_field(name="\u2694\ufe0f Weekly Kill Leaders", value='\n'.join(lines), inline=False)
    else:
        embed.add_field(name="\u2694\ufe0f Weekly Kill Leaders", value="No kills recorded yet", inline=False)

    embed.set_footer(text="CFRP Leaderboard \u2022 Updates every 30s")
    return embed


def save_message_id(mid):
    with open(MESSAGE_ID_FILE, 'w') as f:
        f.write(str(mid))

def load_message_id():
    try:
        with open(MESSAGE_ID_FILE, 'r') as f:
            return int(f.read().strip())
    except:
        return None


intents = discord.Intents.default()
client = discord.Client(intents=intents)
leaderboard_message = None


@client.event
async def on_ready():
    global leaderboard_message
    print(f'[CFRP Leaderboard] Bot logged in as {client.user}')

    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        print(f'[ERROR] Channel {CHANNEL_ID} not found!')
        return

    saved_id = load_message_id()
    if saved_id:
        try:
            leaderboard_message = await channel.fetch_message(saved_id)
            print(f'[CFRP Leaderboard] Found existing message: {saved_id}')
        except:
            leaderboard_message = None

    if not leaderboard_message:
        data = fetch_data()
        if data:
            embed = build_embed(data)
        else:
            embed = discord.Embed(title="\U0001f3ae CFRP Server Leaderboard", description="Loading...", color=0x5865F2)
        leaderboard_message = await channel.send(embed=embed)
        save_message_id(leaderboard_message.id)
        print(f'[CFRP Leaderboard] Created new message: {leaderboard_message.id}')

    client.loop.create_task(update_loop())


async def update_loop():
    global leaderboard_message
    await client.wait_until_ready()

    while not client.is_closed():
        try:
            data = fetch_data()
            if data and leaderboard_message:
                embed = build_embed(data)
                await leaderboard_message.edit(embed=embed)
        except discord.HTTPException as e:
            if e.status == 404:
                channel = client.get_channel(CHANNEL_ID)
                if channel:
                    data = fetch_data()
                    if data:
                        embed = build_embed(data)
                        leaderboard_message = await channel.send(embed=embed)
                        save_message_id(leaderboard_message.id)
        except Exception as e:
            print(f'[ERROR] Update failed: {e}')

        await asyncio.sleep(UPDATE_INTERVAL)


if __name__ == '__main__':
    if not BOT_TOKEN:
        print('[ERROR] DISCORD_BOT_TOKEN not set')
        exit(1)
    if not CHANNEL_ID:
        print('[ERROR] LEADERBOARD_CHANNEL_ID not set')
        exit(1)
    print('[CFRP Leaderboard] Starting bot...')
    client.run(BOT_TOKEN)
