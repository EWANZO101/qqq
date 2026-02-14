import os
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, abort
from flask_login import login_required, current_user
from models import db, PlayerSession, PlayerEconomy, EconomySnapshot, User

from utils.fivem import FiveMStats, FiveMPlayerInfo, FiveMAdmin

api_bp = Blueprint('api', __name__, url_prefix='/api')

SERVER_API_KEY = os.getenv('SERVER_API_KEY', '')


# ===== HEARTBEAT FROM FIVEM =====

@api_bp.route('/server/heartbeat', methods=['POST'])
def server_heartbeat():
    """Receive heartbeat from FiveM server with list of online players."""
    key = request.headers.get('X-API-Key') or request.args.get('key')
    if not key or key != SERVER_API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True)
    if not data or 'players' not in data:
        return jsonify({'error': 'Invalid payload'}), 400

    now = datetime.utcnow()
    today = now.date()
    online_discord_ids = set()

    for player in data['players']:
        discord_id = player.get('discord_id')
        name = player.get('name', 'Unknown')
        if not discord_id:
            continue
        online_discord_ids.add(discord_id)

        # Find active session
        session = PlayerSession.query.filter_by(
            discord_id=discord_id, session_end=None
        ).order_by(PlayerSession.id.desc()).first()

        if session:
            # Update heartbeat and minutes
            minutes = int((now - session.session_start).total_seconds() / 60)
            session.last_heartbeat = now
            session.minutes = minutes
            session.player_name = name

            # Midnight rollover
            if session.date != today:
                session.session_end = now
                session.minutes = int((now - session.session_start).total_seconds() / 60)
                new_session = PlayerSession(
                    discord_id=discord_id, player_name=name,
                    session_start=now, last_heartbeat=now,
                    minutes=0, date=today
                )
                db.session.add(new_session)
        else:
            # New session
            new_session = PlayerSession(
                discord_id=discord_id, player_name=name,
                session_start=now, last_heartbeat=now,
                minutes=0, date=today
            )
            db.session.add(new_session)

    # Close sessions for players NOT in heartbeat (left server)
    if online_discord_ids:
        stale = PlayerSession.query.filter(
            PlayerSession.session_end.is_(None),
            ~PlayerSession.discord_id.in_(online_discord_ids)
        ).all()
    else:
        # No players online - close all
        stale = PlayerSession.query.filter(
            PlayerSession.session_end.is_(None)
        ).all()

    for s in stale:
        s.session_end = now
        s.minutes = int((now - s.session_start).total_seconds() / 60)

    # Also close sessions with no heartbeat for 90+ seconds
    cutoff = now - timedelta(seconds=90)
    stale_hb = PlayerSession.query.filter(
        PlayerSession.session_end.is_(None),
        PlayerSession.last_heartbeat < cutoff
    ).all()

    for s in stale_hb:
        s.session_end = s.last_heartbeat
        s.minutes = int((s.last_heartbeat - s.session_start).total_seconds() / 60)
        if not s.disconnect_reason:
            s.disconnect_reason = 'Heartbeat timeout (no data for 90s)'

    # Track economy per player
    total_cash = 0
    total_bank = 0
    live_positions = []
    for player in data['players']:
        discord_id = player.get('discord_id')
        cash = player.get('cash', 0)
        bank = player.get('bank', 0)
        px = player.get('x', 0)
        py = player.get('y', 0)
        pz = player.get('z', 0)
        name = player.get('name', 'Unknown')
        if not discord_id:
            continue
        total_cash += cash
        total_bank += bank
        
        live_positions.append({
            'discord_id': discord_id, 'name': name,
            'x': px, 'y': py, 'z': pz
        })
        
        if cash > 0 or bank > 0:
            pe = PlayerEconomy.query.filter_by(discord_id=discord_id).first()
            if pe:
                pe.cash = cash
                pe.bank = bank
                pe.updated_at = now
            else:
                pe = PlayerEconomy(discord_id=discord_id, cash=cash, bank=bank, updated_at=now)
                db.session.add(pe)

    from flask import current_app
    current_app.config['LIVE_POSITIONS'] = live_positions
    current_app.config['LIVE_POSITIONS_TIME'] = now

    # Save economy snapshot every 10 minutes
    last_snap = EconomySnapshot.query.order_by(EconomySnapshot.id.desc()).first()
    if not last_snap or (now - last_snap.timestamp).total_seconds() > 600:
        snap = EconomySnapshot(
            timestamp=now, total_cash=total_cash, total_bank=total_bank,
            player_count=len(online_discord_ids),
            unique_players=db.session.query(db.func.count(db.func.distinct(PlayerSession.discord_id))).filter(
                PlayerSession.date == today
            ).scalar()
        )
        db.session.add(snap)

    db.session.commit()

    return jsonify({'ok': True, 'tracked': len(online_discord_ids)})


@api_bp.route('/admin/live-positions')
@login_required
def live_positions():
    """Get live player positions for the map."""
    if not current_user.has_permission('view_admin_panel') and not current_user.is_admin():
        abort(403)
    from flask import current_app
    positions = current_app.config.get('LIVE_POSITIONS', [])
    updated = current_app.config.get('LIVE_POSITIONS_TIME')
    return jsonify({
        'players': positions,
        'updated': updated.isoformat() + 'Z' if updated else None
    })


@api_bp.route('/server/disconnect', methods=['POST'])
def server_disconnect():
    """Receive player disconnect event from FiveM with deep analytics."""
    api_key = request.headers.get('X-API-Key', '')
    if api_key != os.environ.get('SERVER_API_KEY', ''):
        abort(401)
    
    data = request.get_json(silent=True) or {}
    discord_id = data.get('discord_id')
    reason = data.get('reason', 'Unknown')
    player_name = data.get('name', 'Unknown')
    category = data.get('category', '')
    
    # Deep analytics fields
    analysis = data.get('analysis', '')
    avg_ping = data.get('avg_ping', 0)
    max_ping = data.get('max_ping', 0)
    last_ping = data.get('last_ping', 0)
    ping_history = data.get('ping_history', '')
    ping_spike = data.get('ping_spike', False)
    ping_climbing = data.get('ping_climbing', False)
    went_silent = data.get('went_silent', False)
    silent_seconds = data.get('silent_seconds', 0)
    was_dead = data.get('was_dead', False)
    was_moving = data.get('was_moving', False)
    was_afk = data.get('was_afk', False)
    afk_seconds = data.get('afk_seconds', 0)
    was_in_vehicle = data.get('was_in_vehicle', False)
    vehicle_speed = data.get('vehicle_speed', 0)
    health = data.get('health', 0)
    armor = data.get('armor', 0)
    px = data.get('x', 0)
    py = data.get('y', 0)
    pz = data.get('z', 0)
    
    if not discord_id:
        return jsonify({'error': 'Missing discord_id'}), 400
    
    now = datetime.utcnow()
    
    session = PlayerSession.query.filter_by(
        discord_id=discord_id,
        session_end=None
    ).order_by(PlayerSession.id.desc()).first()
    
    if session:
        session.session_end = now
        session.minutes = int((now - session.session_start).total_seconds() / 60)
        
        # Build rich disconnect reason with all metadata
        meta_parts = [reason[:300]]
        if analysis:
            meta_parts.append(f'analysis:{analysis[:500]}')
        meta_parts.append(f'ping:{last_ping}ms avg:{avg_ping}ms max:{max_ping}ms')
        if ping_history:
            meta_parts.append(f'pingHistory:{ping_history}')
        
        flags = []
        if ping_spike: flags.append('PING_SPIKE')
        if ping_climbing: flags.append('PING_CLIMBING')
        if went_silent: flags.append(f'SILENT_{silent_seconds}s')
        if was_dead: flags.append('DEAD')
        if was_afk: flags.append(f'AFK_{afk_seconds}s')
        if was_in_vehicle: flags.append(f'VEHICLE_{vehicle_speed}kph')
        if flags:
            meta_parts.append('flags:' + ','.join(flags))
        
        if px or py:
            meta_parts.append(f'pos:({px},{py},{pz})')
        if health:
            meta_parts.append(f'hp:{health} armor:{armor}')
        
        session.disconnect_reason = ' | '.join(meta_parts)
        db.session.commit()
        print(f"[Disconnect] {player_name} ({discord_id}): [{category}] {reason}")
        if analysis:
            print(f"  → {analysis}")
        return jsonify({'ok': True, 'session_id': session.id})
    
    return jsonify({'ok': True, 'message': 'No active session found'})


@api_bp.route('/admin/session-history')
@login_required
def session_history():
    """Get recent session history with disconnect reasons (admin)."""
    if not current_user.has_permission('view_admin_panel') and not current_user.is_admin():
        abort(403)
    
    limit = request.args.get('limit', 50, type=int)
    discord_id = request.args.get('discord_id')
    
    query = PlayerSession.query.filter(PlayerSession.session_end.isnot(None))
    if discord_id:
        query = query.filter_by(discord_id=discord_id)
    
    sessions = query.order_by(PlayerSession.id.desc()).limit(min(limit, 200)).all()
    
    result = []
    for s in sessions:
        user = User.query.filter_by(discord_id=s.discord_id).first()
        meta = s.reason_meta
        result.append({
            'id': s.id,
            'discord_id': s.discord_id,
            'username': user.username if user else s.player_name or 'Unknown',
            'player_name': s.player_name,
            'session_start': s.session_start.isoformat() + 'Z',
            'session_end': s.session_end.isoformat() + 'Z' if s.session_end else None,
            'minutes': s.minutes,
            'reason': s.reason_display,
            'analysis': meta.get('analysis', ''),
            'category': s.reason_category,
            'ping': meta.get('ping', ''),
            'avg_ping': meta.get('avg_ping', ''),
            'max_ping': meta.get('max_ping', ''),
            'ping_history': meta.get('ping_history', ''),
            'flags': meta.get('flags', []),
            'position': meta.get('position', ''),
            'health': meta.get('health', ''),
            'date': s.date.isoformat()
        })
    
    # Stats summary
    from sqlalchemy import func
    total_sessions = PlayerSession.query.filter(PlayerSession.session_end.isnot(None))
    if discord_id:
        total_sessions = total_sessions.filter_by(discord_id=discord_id)
    total = total_sessions.count()
    
    # Category breakdown
    all_ended = total_sessions.all()
    categories = {}
    for s in all_ended[-200:]:
        cat = s.reason_category
        categories[cat] = categories.get(cat, 0) + 1
    
    return jsonify({
        'sessions': result,
        'total': total,
        'categories': categories
    })


@api_bp.route('/player/session-history')
@login_required
def player_session_history():
    """Get session history for the logged-in player."""
    if not current_user.discord_id:
        return jsonify({'sessions': [], 'total': 0, 'categories': {}})
    
    limit = request.args.get('limit', 30, type=int)
    sessions = PlayerSession.query.filter(
        PlayerSession.discord_id == current_user.discord_id,
        PlayerSession.session_end.isnot(None)
    ).order_by(PlayerSession.id.desc()).limit(min(limit, 100)).all()
    
    result = []
    categories = {}
    for s in sessions:
        cat = s.reason_category
        categories[cat] = categories.get(cat, 0) + 1
        meta = s.reason_meta
        result.append({
            'id': s.id,
            'session_start': s.session_start.isoformat() + 'Z',
            'session_end': s.session_end.isoformat() + 'Z',
            'minutes': s.minutes,
            'reason': s.reason_display,
            'analysis': meta.get('analysis', ''),
            'category': cat,
            'ping': meta.get('ping', ''),
            'avg_ping': meta.get('avg_ping', ''),
            'max_ping': meta.get('max_ping', ''),
            'flags': meta.get('flags', []),
            'date': s.date.isoformat()
        })
    
    return jsonify({
        'sessions': result,
        'total': len(result),
        'categories': categories
    })


# ===== PLAYTIME QUERIES (LOCAL DB) =====

def get_playtime_data(discord_id):
    """Get playtime data for a player from local DB."""
    now = datetime.utcnow()
    today = now.date()
    week_ago = today - timedelta(days=7)
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    # Active session
    active = PlayerSession.query.filter_by(
        discord_id=discord_id, session_end=None
    ).order_by(PlayerSession.id.desc()).first()

    is_online = active is not None
    current_session = 0
    if active:
        current_session = int((now - active.session_start).total_seconds() / 60)

    # Helper to sum minutes for a date filter
    def sum_minutes(date_filter=None):
        q = db.session.query(db.func.coalesce(db.func.sum(PlayerSession.minutes), 0)).filter(
            PlayerSession.discord_id == discord_id
        )
        if date_filter is not None:
            q = q.filter(date_filter)
        stored = q.scalar()
        # Add live session time (replace stored active minutes with real-time)
        if is_online and active:
            return int(stored) - active.minutes + current_session
        return int(stored)

    today_min = sum_minutes(PlayerSession.date == today)
    week_min = sum_minutes(PlayerSession.date >= week_ago)
    month_min = sum_minutes(PlayerSession.date >= month_start)
    year_min = sum_minutes(PlayerSession.date >= year_start)
    total_min = sum_minutes()

    # Last seen
    last = PlayerSession.query.filter(
        PlayerSession.discord_id == discord_id
    ).order_by(PlayerSession.id.desc()).first()
    last_seen = None
    if last:
        ts = last.last_heartbeat or last.session_end or last.session_start
        last_seen = ts.isoformat() + 'Z'

    return {
        'is_online': is_online,
        'current_session_minutes': current_session,
        'today_minutes': today_min,
        'week_minutes': week_min,
        'month_minutes': month_min,
        'year_minutes': year_min,
        'total_minutes': total_min,
        'last_seen': last_seen
    }


def get_active_players_data():
    """Get list of currently online players."""
    now = datetime.utcnow()
    sessions = PlayerSession.query.filter_by(session_end=None).all()
    players = []
    seen = set()
    for s in sessions:
        if s.discord_id in seen:
            continue
        seen.add(s.discord_id)
        mins = int((now - s.session_start).total_seconds() / 60)
        user = User.query.filter_by(discord_id=s.discord_id).first()
        players.append({
            'discord_id': s.discord_id,
            'username': user.username if user else s.player_name or 'Unknown',
            'session_minutes': mins
        })
    return {'count': len(players), 'players': players}


def get_overview_data():
    """Server overview stats from local DB."""
    now = datetime.utcnow()
    today = now.date()
    week_ago = today - timedelta(days=7)

    active = db.session.query(db.func.count(db.func.distinct(PlayerSession.discord_id))).filter(
        PlayerSession.session_end.is_(None)
    ).scalar()

    unique_today = db.session.query(db.func.count(db.func.distinct(PlayerSession.discord_id))).filter(
        PlayerSession.date == today
    ).scalar()
    unique_week = db.session.query(db.func.count(db.func.distinct(PlayerSession.discord_id))).filter(
        PlayerSession.date >= week_ago
    ).scalar()
    unique_total = db.session.query(db.func.count(db.func.distinct(PlayerSession.discord_id))).scalar()

    pt_today = db.session.query(db.func.coalesce(db.func.sum(PlayerSession.minutes), 0)).filter(
        PlayerSession.date == today
    ).scalar()
    pt_week = db.session.query(db.func.coalesce(db.func.sum(PlayerSession.minutes), 0)).filter(
        PlayerSession.date >= week_ago
    ).scalar()

    # Kill stats from remote DB
    kills_today = deaths_today = kills_week = deaths_week = 0
    try:
        from utils.fivem import FiveMAdmin as FA
        conn, err = FA._get_connection()
        if not err:
            cursor = conn.cursor()
            today_str = now.strftime('%Y-%m-%d')
            week_str = (now - timedelta(days=7)).strftime('%Y-%m-%d')
            cursor.execute(
                "SELECT event_type, COUNT(*) as cnt FROM cfrp_player_stats "
                "WHERE DATE(created_at)=%s GROUP BY event_type", (today_str,)
            )
            for r in cursor.fetchall():
                if r['event_type'] == 'kill': kills_today = r['cnt']
                elif r['event_type'] == 'death': deaths_today = r['cnt']

            cursor.execute(
                "SELECT event_type, COUNT(*) as cnt FROM cfrp_player_stats "
                "WHERE created_at >= %s GROUP BY event_type", (week_str + ' 00:00:00',)
            )
            for r in cursor.fetchall():
                if r['event_type'] == 'kill': kills_week = r['cnt']
                elif r['event_type'] == 'death': deaths_week = r['cnt']
            conn.close()
    except:
        pass

    return {
        'active_players': active,
        'unique_today': unique_today,
        'unique_week': unique_week,
        'unique_total': unique_total,
        'playtime_today_minutes': int(pt_today),
        'playtime_week_minutes': int(pt_week),
        'kills_today': kills_today,
        'deaths_today': deaths_today,
        'kills_week': kills_week,
        'deaths_week': deaths_week,
    }


def get_leaderboard_data(period='week', limit=20):
    """Playtime leaderboard from local DB."""
    today = datetime.utcnow().date()

    query = db.session.query(
        PlayerSession.discord_id,
        db.func.sum(PlayerSession.minutes).label('total_minutes')
    )

    if period == 'today':
        query = query.filter(PlayerSession.date == today)
    elif period == 'week':
        query = query.filter(PlayerSession.date >= today - timedelta(days=7))
    elif period == 'month':
        query = query.filter(PlayerSession.date >= today.replace(day=1))

    results = query.group_by(PlayerSession.discord_id).order_by(
        db.func.sum(PlayerSession.minutes).desc()
    ).limit(limit).all()

    leaderboard = []
    for i, (discord_id, total_min) in enumerate(results):
        user = User.query.filter_by(discord_id=discord_id).first()
        leaderboard.append({
            'rank': i + 1,
            'discord_id': discord_id,
            'username': user.username if user else 'Unknown',
            'total_minutes': int(total_min or 0)
        })
    return leaderboard


# ===== USER ENDPOINTS =====

@api_bp.route('/playtime')
@login_required
def get_my_playtime():
    discord_id = current_user.discord_id
    if not discord_id:
        return jsonify({'error': 'No Discord ID linked'}), 400
    return jsonify(get_playtime_data(discord_id))


@api_bp.route('/stats')
@login_required
def get_my_stats():
    discord_id = current_user.discord_id
    if not discord_id:
        return jsonify({'error': 'No Discord ID linked'}), 400
    data, error = FiveMStats.get_player_stats(discord_id)
    if error:
        return jsonify({'error': error})
    return jsonify(data)


@api_bp.route('/player-info')
@login_required
def get_my_player_info():
    discord_id = current_user.discord_id
    if not discord_id:
        return jsonify({'error': 'No Discord ID linked'}), 400
    data, error = FiveMPlayerInfo.get_player_info(discord_id)
    if error:
        return jsonify({'error': error})
    return jsonify(data)


# ===== ADMIN ENDPOINTS =====

@api_bp.route('/playtime/<discord_id>')
@login_required
def get_user_playtime(discord_id):
    if not current_user.has_permission('view_admin_panel') and not current_user.is_admin():
        abort(403)
    return jsonify(get_playtime_data(discord_id))


@api_bp.route('/stats/<discord_id>')
@login_required
def get_user_stats(discord_id):
    if not current_user.has_permission('view_admin_panel') and not current_user.is_admin():
        abort(403)
    data, error = FiveMStats.get_player_stats(discord_id)
    if error:
        return jsonify({'error': error})
    return jsonify(data)


@api_bp.route('/player-info/<discord_id>')
@login_required
def get_user_player_info(discord_id):
    if not current_user.has_permission('view_admin_panel') and not current_user.is_admin():
        abort(403)
    data, error = FiveMPlayerInfo.get_player_info(discord_id)
    if error:
        return jsonify({'error': error})
    return jsonify(data)


@api_bp.route('/admin/active-players')
@login_required
def get_active_players():
    if not current_user.has_permission('view_admin_panel') and not current_user.is_admin():
        abort(403)
    return jsonify(get_active_players_data())


@api_bp.route('/admin/overview')
@login_required
def get_server_overview():
    if not current_user.has_permission('view_admin_panel') and not current_user.is_admin():
        abort(403)
    return jsonify(get_overview_data())


@api_bp.route('/admin/leaderboard/<period>')
@login_required
def get_leaderboard(period):
    if not current_user.has_permission('view_admin_panel') and not current_user.is_admin():
        abort(403)
    if period not in ('today', 'week', 'month', 'all'):
        return jsonify({'error': 'Invalid period'}), 400
    return jsonify(get_leaderboard_data(period))


@api_bp.route('/admin/kill-leaderboard/<period>')
@login_required
def get_kill_leaderboard(period):
    if not current_user.has_permission('view_admin_panel') and not current_user.is_admin():
        abort(403)
    if period not in ('today', 'week', 'month', 'all'):
        return jsonify({'error': 'Invalid period'}), 400
    data, error = FiveMAdmin.get_kill_leaderboard(period)
    if error:
        return jsonify({'error': error})
    return jsonify(data)


@api_bp.route('/admin/recent-kills')
@login_required
def get_recent_kills():
    if not current_user.has_permission('view_admin_panel') and not current_user.is_admin():
        abort(403)
    data, error = FiveMAdmin.get_recent_kills()
    if error:
        return jsonify({'error': error})
    return jsonify(data)


# ===== ANALYTICS ENDPOINTS =====

@api_bp.route('/admin/analytics/death-heatmap')
@login_required
def death_heatmap():
    """Return death locations for heatmap visualization."""
    if not current_user.has_permission('view_admin_panel') and not current_user.is_admin():
        abort(403)
    try:
        from utils.fivem import FiveMDB
        conn, err = FiveMDB._get_connection()
        if err:
            return jsonify({'error': err})
        cursor = conn.cursor()
        days = request.args.get('days', '7', type=str)
        cursor.execute(
            "SELECT x, y, z, event_type, weapon, cause, created_at FROM cfrp_player_stats "
            "WHERE x IS NOT NULL AND y IS NOT NULL AND created_at >= DATE_SUB(NOW(), INTERVAL %s DAY) "
            "ORDER BY created_at DESC LIMIT 500",
            (int(days),)
        )
        points = []
        for r in cursor.fetchall():
            points.append({
                'x': r['x'], 'y': r['y'], 'z': r['z'],
                'type': r['event_type'], 'weapon': r['weapon'],
                'cause': r['cause'],
                'time': r['created_at'].isoformat() + 'Z' if r['created_at'] else None
            })
        conn.close()
        return jsonify(points)
    except Exception as e:
        return jsonify({'error': str(e)})


@api_bp.route('/admin/analytics/retention')
@login_required
def player_retention():
    """Player retention: how many players return after first visit."""
    if not current_user.has_permission('view_admin_panel') and not current_user.is_admin():
        abort(403)
    
    now = datetime.utcnow()
    today = now.date()
    
    # Get first visit date per player
    first_visits = db.session.query(
        PlayerSession.discord_id,
        db.func.min(PlayerSession.date).label('first_date')
    ).group_by(PlayerSession.discord_id).subquery()
    
    retention = {}
    for days_label, days_val in [('Day 1', 1), ('Day 3', 3), ('Day 7', 7), ('Day 14', 14), ('Day 30', 30)]:
        # Players whose first visit was at least X days ago
        cutoff = today - timedelta(days=days_val)
        
        # Total players who first joined on or before cutoff
        total_eligible = db.session.query(db.func.count()).select_from(first_visits).filter(
            first_visits.c.first_date <= cutoff
        ).scalar()
        
        if total_eligible == 0:
            retention[days_label] = {'total': 0, 'returned': 0, 'rate': 0}
            continue
        
        # Of those, how many have a session on or after (first_date + X days)
        returned = 0
        eligible_players = db.session.query(first_visits.c.discord_id, first_visits.c.first_date).filter(
            first_visits.c.first_date <= cutoff
        ).all()
        
        for discord_id, first_date in eligible_players:
            target_date = first_date + timedelta(days=days_val)
            has_return = PlayerSession.query.filter(
                PlayerSession.discord_id == discord_id,
                PlayerSession.date >= target_date
            ).first()
            if has_return:
                returned += 1
        
        rate = round((returned / total_eligible) * 100, 1) if total_eligible > 0 else 0
        retention[days_label] = {'total': total_eligible, 'returned': returned, 'rate': rate}
    
    # New vs returning today
    new_today = 0
    returning_today = 0
    today_players = db.session.query(db.func.distinct(PlayerSession.discord_id)).filter(
        PlayerSession.date == today
    ).all()
    
    for (discord_id,) in today_players:
        first = db.session.query(db.func.min(PlayerSession.date)).filter(
            PlayerSession.discord_id == discord_id
        ).scalar()
        if first == today:
            new_today += 1
        else:
            returning_today += 1
    
    return jsonify({
        'retention': retention,
        'new_today': new_today,
        'returning_today': returning_today,
        'total_unique': db.session.query(db.func.count(db.func.distinct(PlayerSession.discord_id))).scalar()
    })


@api_bp.route('/admin/analytics/peak-hours')
@login_required
def peak_hours():
    """Analyze peak hours and daily player counts."""
    if not current_user.has_permission('view_admin_panel') and not current_user.is_admin():
        abort(403)
    
    now = datetime.utcnow()
    today = now.date()
    
    # Hourly breakdown from snapshots (last 7 days)
    week_ago = now - timedelta(days=7)
    snaps = EconomySnapshot.query.filter(EconomySnapshot.timestamp >= week_ago).all()
    
    # Average player count per hour
    hour_totals = {}
    hour_counts = {}
    for s in snaps:
        h = s.timestamp.hour
        hour_totals[h] = hour_totals.get(h, 0) + s.player_count
        hour_counts[h] = hour_counts.get(h, 0) + 1
    
    hourly = []
    for h in range(24):
        avg = round(hour_totals.get(h, 0) / max(hour_counts.get(h, 0), 1), 1)
        hourly.append({'hour': h, 'label': f'{h:02d}:00', 'avg_players': avg})
    
    # Daily unique players (last 30 days)
    thirty_days_ago = today - timedelta(days=30)
    daily_results = db.session.query(
        PlayerSession.date,
        db.func.count(db.func.distinct(PlayerSession.discord_id)).label('unique'),
        db.func.sum(PlayerSession.minutes).label('total_minutes')
    ).filter(PlayerSession.date >= thirty_days_ago).group_by(
        PlayerSession.date
    ).order_by(PlayerSession.date).all()
    
    daily = []
    for d, unique, total_min in daily_results:
        daily.append({
            'date': d.isoformat(),
            'unique_players': unique,
            'total_minutes': int(total_min or 0)
        })
    
    # Peak hour
    peak = max(hourly, key=lambda x: x['avg_players']) if hourly else {'hour': 0, 'avg_players': 0}
    
    return jsonify({
        'hourly': hourly,
        'daily': daily,
        'peak_hour': peak['label'] if peak else 'N/A',
        'peak_avg': peak['avg_players'] if peak else 0
    })


@api_bp.route('/admin/analytics/economy')
@login_required
def economy_dashboard():
    """Economy health dashboard."""
    if not current_user.has_permission('view_admin_panel') and not current_user.is_admin():
        abort(403)
    
    now = datetime.utcnow()
    
    # Latest economy per player (top 10 richest)
    richest = PlayerEconomy.query.order_by(
        (PlayerEconomy.cash + PlayerEconomy.bank).desc()
    ).limit(10).all()
    
    top_players = []
    for pe in richest:
        user = User.query.filter_by(discord_id=pe.discord_id).first()
        top_players.append({
            'username': user.username if user else 'Unknown',
            'discord_id': pe.discord_id,
            'cash': pe.cash,
            'bank': pe.bank,
            'total': pe.cash + pe.bank
        })
    
    # Total economy
    totals = db.session.query(
        db.func.coalesce(db.func.sum(PlayerEconomy.cash), 0),
        db.func.coalesce(db.func.sum(PlayerEconomy.bank), 0),
        db.func.count(PlayerEconomy.id)
    ).first()
    
    total_cash = int(totals[0])
    total_bank = int(totals[1])
    total_players = totals[2]
    avg_wealth = (total_cash + total_bank) // max(total_players, 1)
    
    # Economy over time (snapshots)
    week_ago = now - timedelta(days=7)
    snapshots = EconomySnapshot.query.filter(
        EconomySnapshot.timestamp >= week_ago
    ).order_by(EconomySnapshot.timestamp).all()
    
    timeline = []
    for s in snapshots:
        timeline.append({
            'time': s.timestamp.isoformat() + 'Z',
            'total_cash': s.total_cash,
            'total_bank': s.total_bank,
            'total': s.total_cash + s.total_bank,
            'players': s.player_count
        })
    
    # Wealth distribution brackets
    brackets = [
        ('Broke ($0-$1K)', 0, 1000),
        ('Low ($1K-$10K)', 1000, 10000),
        ('Medium ($10K-$100K)', 10000, 100000),
        ('Rich ($100K-$1M)', 100000, 1000000),
        ('Wealthy ($1M+)', 1000000, 999999999999),
    ]
    distribution = []
    for label, low, high in brackets:
        count = PlayerEconomy.query.filter(
            (PlayerEconomy.cash + PlayerEconomy.bank) >= low,
            (PlayerEconomy.cash + PlayerEconomy.bank) < high
        ).count()
        distribution.append({'label': label, 'count': count})
    
    return jsonify({
        'total_cash': total_cash,
        'total_bank': total_bank,
        'total_circulation': total_cash + total_bank,
        'total_players': total_players,
        'avg_wealth': avg_wealth,
        'top_players': top_players,
        'timeline': timeline,
        'distribution': distribution
    })
