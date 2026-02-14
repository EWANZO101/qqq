"""
FiveM Integration - Direct Database Read

Reads playtime, kills/deaths, and player data directly from the FiveM MySQL database.
"""

import pymysql
import json
from flask import current_app
from datetime import datetime, timedelta


class FiveMDB:
    """Shared database connection for all FiveM queries."""

    @classmethod
    def _get_connection(cls):
        try:
            conn = pymysql.connect(
                host=current_app.config.get('FIVEM_DB_HOST', '169.239.180.43'),
                user=current_app.config.get('FIVEM_DB_USER', 'csrp'),
                password=current_app.config.get('FIVEM_DB_PASSWORD', 'xhGM0NnDkvCouj8l'),
                database=current_app.config.get('FIVEM_DB_NAME', 'csrp'),
                port=int(current_app.config.get('FIVEM_DB_PORT', 3306)),
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=5
            )
            return conn, None
        except Exception as e:
            return None, str(e)



class FiveMPlaytime(FiveMDB):
    """Query FiveM playtime data."""

    @classmethod
    def get_player_playtime(cls, discord_id):
        if not discord_id:
            return None, 'No Discord ID provided'
        conn, error = cls._get_connection()
        if error:
            return None, error
        try:
            cursor = conn.cursor()
            now = datetime.utcnow()
            today = now.strftime('%Y-%m-%d')
            week_ago = (now - timedelta(days=7)).strftime('%Y-%m-%d')
            month_start = now.strftime('%Y-%m-01')
            year_start = now.strftime('%Y-01-01')

            cursor.execute(
                "SELECT session_start, minutes FROM cfrp_playtime "
                "WHERE discord_id = %s AND session_end IS NULL ORDER BY id DESC LIMIT 1",
                (discord_id,)
            )
            active = cursor.fetchone()
            is_online = active is not None
            current_session_minutes = 0
            if active and active['session_start']:
                start = active['session_start']
                if isinstance(start, str):
                    start = datetime.strptime(start, '%Y-%m-%d %H:%M:%S')
                current_session_minutes = max(int((now - start).total_seconds() / 60), 0)

            queries = {
                'today': ("SELECT COALESCE(SUM(minutes),0) as t FROM cfrp_playtime WHERE discord_id=%s AND date=%s", (discord_id, today)),
                'week': ("SELECT COALESCE(SUM(minutes),0) as t FROM cfrp_playtime WHERE discord_id=%s AND date>=%s", (discord_id, week_ago)),
                'month': ("SELECT COALESCE(SUM(minutes),0) as t FROM cfrp_playtime WHERE discord_id=%s AND date>=%s", (discord_id, month_start)),
                'year': ("SELECT COALESCE(SUM(minutes),0) as t FROM cfrp_playtime WHERE discord_id=%s AND date>=%s", (discord_id, year_start)),
                'total': ("SELECT COALESCE(SUM(minutes),0) as t FROM cfrp_playtime WHERE discord_id=%s", (discord_id,)),
            }
            results = {}
            for key, (sql, params) in queries.items():
                cursor.execute(sql, params)
                results[key] = int(cursor.fetchone()['t'] or 0)

            cursor.execute(
                "SELECT session_end FROM cfrp_playtime WHERE discord_id=%s AND session_end IS NOT NULL ORDER BY session_end DESC LIMIT 1",
                (discord_id,)
            )
            last_row = cursor.fetchone()
            last_seen = None
            if is_online:
                last_seen = now.isoformat() + 'Z'
            elif last_row and last_row['session_end']:
                ls = last_row['session_end']
                last_seen = ls.isoformat() + 'Z' if isinstance(ls, datetime) else str(ls)

            return {
                'is_online': is_online,
                'current_session_minutes': current_session_minutes,
                'today_minutes': results['today'],
                'week_minutes': results['week'],
                'month_minutes': results['month'],
                'year_minutes': results['year'],
                'total_minutes': results['total'],
                'last_seen': last_seen
            }, None
        except Exception as e:
            return None, str(e)
        finally:
            conn.close()


class FiveMStats(FiveMDB):
    """Query kill/death stats from cfrp_player_stats."""

    @classmethod
    def get_player_stats(cls, discord_id):
        if not discord_id:
            return None, 'No Discord ID provided'
        conn, error = cls._get_connection()
        if error:
            return None, error
        try:
            cursor = conn.cursor()
            now = datetime.utcnow()
            today = now.strftime('%Y-%m-%d')
            week_ago = (now - timedelta(days=7)).strftime('%Y-%m-%d')
            month_start = now.strftime('%Y-%m-01')

            # Total kills & deaths
            cursor.execute(
                "SELECT event_type, COUNT(*) as cnt FROM cfrp_player_stats "
                "WHERE discord_id=%s AND event_type IN ('kill','death') GROUP BY event_type",
                (discord_id,)
            )
            totals = {'kill': 0, 'death': 0}
            for row in cursor.fetchall():
                totals[row['event_type']] = row['cnt']

            # Today
            cursor.execute(
                "SELECT event_type, COUNT(*) as cnt FROM cfrp_player_stats "
                "WHERE discord_id=%s AND event_type IN ('kill','death') AND DATE(created_at)=%s GROUP BY event_type",
                (discord_id, today)
            )
            today_stats = {'kill': 0, 'death': 0}
            for row in cursor.fetchall():
                today_stats[row['event_type']] = row['cnt']

            # This week
            cursor.execute(
                "SELECT event_type, COUNT(*) as cnt FROM cfrp_player_stats "
                "WHERE discord_id=%s AND event_type IN ('kill','death') AND DATE(created_at)>=%s GROUP BY event_type",
                (discord_id, week_ago)
            )
            week_stats = {'kill': 0, 'death': 0}
            for row in cursor.fetchall():
                week_stats[row['event_type']] = row['cnt']

            # This month
            cursor.execute(
                "SELECT event_type, COUNT(*) as cnt FROM cfrp_player_stats "
                "WHERE discord_id=%s AND event_type IN ('kill','death') AND DATE(created_at)>=%s GROUP BY event_type",
                (discord_id, month_start)
            )
            month_stats = {'kill': 0, 'death': 0}
            for row in cursor.fetchall():
                month_stats[row['event_type']] = row['cnt']

            # Top weapons used (kills)
            cursor.execute(
                "SELECT weapon, COUNT(*) as cnt FROM cfrp_player_stats "
                "WHERE discord_id=%s AND event_type='kill' AND weapon IS NOT NULL "
                "GROUP BY weapon ORDER BY cnt DESC LIMIT 5",
                (discord_id,)
            )
            top_weapons = [{'weapon': r['weapon'], 'count': r['cnt']} for r in cursor.fetchall()]

            # Top causes of death
            cursor.execute(
                "SELECT cause, COUNT(*) as cnt FROM cfrp_player_stats "
                "WHERE discord_id=%s AND event_type='death' AND cause IS NOT NULL "
                "GROUP BY cause ORDER BY cnt DESC LIMIT 5",
                (discord_id,)
            )
            top_death_causes = [{'cause': r['cause'], 'count': r['cnt']} for r in cursor.fetchall()]

            # Recent events (last 20)
            cursor.execute(
                "SELECT event_type, cause, weapon, killer_name, victim_name, created_at "
                "FROM cfrp_player_stats WHERE discord_id=%s "
                "ORDER BY created_at DESC LIMIT 20",
                (discord_id,)
            )
            recent = []
            for r in cursor.fetchall():
                ca = r['created_at']
                recent.append({
                    'type': r['event_type'],
                    'cause': r['cause'],
                    'weapon': r['weapon'],
                    'killer': r['killer_name'],
                    'victim': r['victim_name'],
                    'time': ca.isoformat() + 'Z' if isinstance(ca, datetime) else str(ca)
                })

            kd_ratio = round(totals['kill'] / max(totals['death'], 1), 2)

            return {
                'total_kills': totals['kill'],
                'total_deaths': totals['death'],
                'kd_ratio': kd_ratio,
                'today_kills': today_stats['kill'],
                'today_deaths': today_stats['death'],
                'week_kills': week_stats['kill'],
                'week_deaths': week_stats['death'],
                'month_kills': month_stats['kill'],
                'month_deaths': month_stats['death'],
                'top_weapons': top_weapons,
                'top_death_causes': top_death_causes,
                'recent_events': recent,
            }, None
        except Exception as e:
            return None, str(e)
        finally:
            conn.close()


class FiveMPlayerInfo(FiveMDB):
    """Query QBox player info."""

    @classmethod
    def get_player_info(cls, discord_id):
        if not discord_id:
            return None, 'No Discord ID provided'
        conn, error = cls._get_connection()
        if error:
            return None, error
        try:
            cursor = conn.cursor()
            discord_str = 'discord:' + discord_id

            cursor.execute("SELECT userId FROM users WHERE discord=%s LIMIT 1", (discord_str,))
            user_row = cursor.fetchone()
            if not user_row:
                return None, 'Player not found in FiveM database'

            user_id = user_row['userId']

            cursor.execute(
                "SELECT citizenid, name, charinfo, money, job, gang, metadata, last_updated, last_logged_out "
                "FROM players WHERE userId=%s ORDER BY last_updated DESC",
                (user_id,)
            )
            characters = []
            for row in cursor.fetchall():
                charinfo = json.loads(row['charinfo']) if row['charinfo'] else {}
                money = json.loads(row['money']) if row['money'] else {}
                job = json.loads(row['job']) if row['job'] else {}
                gang = json.loads(row['gang']) if row['gang'] else {}
                metadata = json.loads(row['metadata']) if row['metadata'] else {}

                characters.append({
                    'citizenid': row['citizenid'],
                    'name': row['name'],
                    'firstname': charinfo.get('firstname', ''),
                    'lastname': charinfo.get('lastname', ''),
                    'nationality': charinfo.get('nationality', ''),
                    'gender': charinfo.get('gender', 0),
                    'birthdate': charinfo.get('birthdate', ''),
                    'phone': charinfo.get('phone', ''),
                    'cash': int(money.get('cash', 0)),
                    'bank': int(money.get('bank', 0)),
                    'crypto': int(money.get('crypto', 0)),
                    'job_name': job.get('name', 'unemployed'),
                    'job_label': job.get('label', 'Unemployed'),
                    'job_grade': job.get('grade', {}).get('name', ''),
                    'gang_name': gang.get('name', 'none'),
                    'gang_label': gang.get('label', 'None'),
                    'stress': metadata.get('stress', 0),
                    'hunger': round(metadata.get('hunger', 0), 1),
                    'thirst': round(metadata.get('thirst', 0), 1),
                    'health': metadata.get('health', 200),
                    'armor': metadata.get('armor', 0),
                    'is_dead': metadata.get('isdead', False),
                    'in_jail': metadata.get('injail', 0),
                    'has_record': metadata.get('criminalrecord', {}).get('hasRecord', False),
                    'licenses': metadata.get('licences', {}),
                    'blood_type': metadata.get('bloodtype', 'Unknown'),
                    'last_updated': row['last_updated'].isoformat() + 'Z' if isinstance(row['last_updated'], datetime) else str(row['last_updated']) if row['last_updated'] else None,
                    'last_logged_out': row['last_logged_out'].isoformat() + 'Z' if isinstance(row['last_logged_out'], datetime) else str(row['last_logged_out']) if row['last_logged_out'] else None,
                })

            return {'characters': characters}, None
        except Exception as e:
            return None, str(e)
        finally:
            conn.close()


class FiveMAdmin(FiveMDB):
    """Admin analytics."""

    @classmethod
    def get_active_players(cls):
        conn, error = cls._get_connection()
        if error:
            return None, error
        try:
            cursor = conn.cursor()
            now = datetime.utcnow()

            cursor.execute(
                "SELECT pt.discord_id, pt.session_start, u.username "
                "FROM cfrp_playtime pt "
                "INNER JOIN (SELECT discord_id, MAX(id) as max_id FROM cfrp_playtime WHERE session_end IS NULL GROUP BY discord_id) latest "
                "ON pt.id = latest.max_id "
                "LEFT JOIN users u ON u.discord = CONCAT('discord:', pt.discord_id) "
                "ORDER BY pt.session_start ASC"
            )
            players = []
            for row in cursor.fetchall():
                start = row['session_start']
                if isinstance(start, str):
                    start = datetime.strptime(start, '%Y-%m-%d %H:%M:%S')
                mins = max(int((now - start).total_seconds() / 60), 0)
                players.append({
                    'discord_id': row['discord_id'],
                    'username': row['username'] or 'Unknown',
                    'session_minutes': mins,
                    'session_start': start.isoformat() + 'Z'
                })
            return {'players': players, 'count': len(players)}, None
        except Exception as e:
            return None, str(e)
        finally:
            conn.close()

    @classmethod
    def get_leaderboard(cls, period='week', limit=20):
        conn, error = cls._get_connection()
        if error:
            return None, error
        try:
            cursor = conn.cursor()
            now = datetime.utcnow()
            if period == 'today':
                date_filter = now.strftime('%Y-%m-%d')
            elif period == 'week':
                date_filter = (now - timedelta(days=7)).strftime('%Y-%m-%d')
            elif period == 'month':
                date_filter = now.strftime('%Y-%m-01')
            else:
                date_filter = '2000-01-01'

            cursor.execute(
                "SELECT pt.discord_id, COALESCE(SUM(pt.minutes),0) as total_minutes, u.username "
                "FROM cfrp_playtime pt "
                "LEFT JOIN users u ON u.discord = CONCAT('discord:', pt.discord_id) "
                "WHERE pt.date >= %s "
                "GROUP BY pt.discord_id, u.username ORDER BY total_minutes DESC LIMIT %s",
                (date_filter, limit)
            )
            return [{'rank': i+1, 'discord_id': r['discord_id'], 'username': r['username'] or 'Unknown', 'total_minutes': int(r['total_minutes'])} for i, r in enumerate(cursor.fetchall())], None
        except Exception as e:
            return None, str(e)
        finally:
            conn.close()

    @classmethod
    def get_kill_leaderboard(cls, period='week', limit=20):
        conn, error = cls._get_connection()
        if error:
            return None, error
        try:
            cursor = conn.cursor()
            now = datetime.utcnow()
            if period == 'today':
                date_filter = now.strftime('%Y-%m-%d 00:00:00')
            elif period == 'week':
                date_filter = (now - timedelta(days=7)).strftime('%Y-%m-%d 00:00:00')
            elif period == 'month':
                date_filter = now.strftime('%Y-%m-01 00:00:00')
            else:
                date_filter = '2000-01-01 00:00:00'

            cursor.execute(
                "SELECT s.discord_id, "
                "SUM(CASE WHEN s.event_type='kill' THEN 1 ELSE 0 END) as kills, "
                "SUM(CASE WHEN s.event_type='death' THEN 1 ELSE 0 END) as deaths, "
                "u.username "
                "FROM cfrp_player_stats s "
                "LEFT JOIN users u ON u.discord = CONCAT('discord:', s.discord_id) "
                "WHERE s.created_at >= %s "
                "GROUP BY s.discord_id, u.username ORDER BY kills DESC LIMIT %s",
                (date_filter, limit)
            )
            lb = []
            for i, r in enumerate(cursor.fetchall()):
                k, d = int(r['kills']), int(r['deaths'])
                lb.append({'rank': i+1, 'discord_id': r['discord_id'], 'username': r['username'] or 'Unknown', 'kills': k, 'deaths': d, 'kd_ratio': round(k / max(d, 1), 2)})
            return lb, None
        except Exception as e:
            return None, str(e)
        finally:
            conn.close()

    @classmethod
    def get_recent_kills(cls, limit=50):
        conn, error = cls._get_connection()
        if error:
            return None, error
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT s.event_type, s.cause, s.weapon, s.killer_name, s.victim_name, "
                "s.discord_id, s.killer_discord_id, s.created_at, "
                "u1.username as victim_username, u2.username as killer_username "
                "FROM cfrp_player_stats s "
                "LEFT JOIN users u1 ON u1.discord = CONCAT('discord:', s.discord_id) "
                "LEFT JOIN users u2 ON u2.discord = CONCAT('discord:', s.killer_discord_id) "
                "WHERE s.event_type IN ('kill', 'death') "
                "ORDER BY s.created_at DESC LIMIT %s",
                (limit,)
            )
            events = []
            seen = set()
            for r in cursor.fetchall():
                # Deduplicate: each kill creates both a kill and death row, show once
                ca = r['created_at']
                key = str(ca) + (r['discord_id'] or '') + (r['killer_discord_id'] or '')
                if r['event_type'] == 'death' and key in seen:
                    continue
                if r['event_type'] == 'kill':
                    seen.add(str(ca) + (r['killer_discord_id'] or '') + (r['discord_id'] or ''))

                events.append({
                    'type': r['event_type'],
                    'cause': r['cause'],
                    'weapon': r['weapon'],
                    'killer': r['killer_username'] or r['killer_name'],
                    'victim': r['victim_username'] or r['victim_name'],
                    'time': ca.isoformat() + 'Z' if isinstance(ca, datetime) else str(ca)
                })
            return events, None
        except Exception as e:
            return None, str(e)
        finally:
            conn.close()

    @classmethod
    def get_server_overview(cls):
        conn, error = cls._get_connection()
        if error:
            return None, error
        try:
            cursor = conn.cursor()
            now = datetime.utcnow()
            today = now.strftime('%Y-%m-%d')
            week_ago = (now - timedelta(days=7)).strftime('%Y-%m-%d')

            cursor.execute("SELECT COUNT(DISTINCT discord_id) as cnt FROM cfrp_playtime WHERE session_end IS NULL")
            active = cursor.fetchone()['cnt']

            cursor.execute("SELECT COUNT(DISTINCT discord_id) as cnt FROM cfrp_playtime WHERE date=%s", (today,))
            unique_today = cursor.fetchone()['cnt']

            cursor.execute("SELECT COUNT(DISTINCT discord_id) as cnt FROM cfrp_playtime WHERE date>=%s", (week_ago,))
            unique_week = cursor.fetchone()['cnt']

            cursor.execute("SELECT COUNT(DISTINCT discord_id) as cnt FROM cfrp_playtime")
            unique_total = cursor.fetchone()['cnt']

            cursor.execute("SELECT COALESCE(SUM(minutes),0) as t FROM cfrp_playtime WHERE date=%s", (today,))
            playtime_today = int(cursor.fetchone()['t'])

            cursor.execute("SELECT COALESCE(SUM(minutes),0) as t FROM cfrp_playtime WHERE date>=%s", (week_ago,))
            playtime_week = int(cursor.fetchone()['t'])

            cursor.execute(
                "SELECT event_type, COUNT(*) as cnt FROM cfrp_player_stats "
                "WHERE DATE(created_at)=%s AND event_type IN ('kill','death') GROUP BY event_type", (today,))
            events_today = {'kill': 0, 'death': 0}
            for row in cursor.fetchall():
                events_today[row['event_type']] = row['cnt']

            cursor.execute(
                "SELECT event_type, COUNT(*) as cnt FROM cfrp_player_stats "
                "WHERE DATE(created_at)>=%s AND event_type IN ('kill','death') GROUP BY event_type", (week_ago,))
            events_week = {'kill': 0, 'death': 0}
            for row in cursor.fetchall():
                events_week[row['event_type']] = row['cnt']

            return {
                'active_players': active, 'unique_today': unique_today, 'unique_week': unique_week,
                'unique_total': unique_total, 'playtime_today_minutes': playtime_today,
                'playtime_week_minutes': playtime_week, 'kills_today': events_today['kill'],
                'deaths_today': events_today['death'], 'kills_week': events_week['kill'],
                'deaths_week': events_week['death'],
            }, None
        except Exception as e:
            return None, str(e)
        finally:
            conn.close()


def format_playtime(minutes):
    if minutes is None or minutes == 0:
        return '0m'
    days = minutes // 1440
    hours = (minutes % 1440) // 60
    mins = minutes % 60
    parts = []
    if days > 0: parts.append(f'{days}d')
    if hours > 0: parts.append(f'{hours}h')
    if mins > 0 or not parts: parts.append(f'{mins}m')
    return ' '.join(parts)
