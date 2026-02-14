import requests
import json
from flask import current_app


class DiscordWebhook:
    """Send webhook notifications to Discord."""

    @staticmethod
    def send_application_notification(application, webhook_url):
        """Send a new application notification to Discord."""
        try:
            form_data = application.get_form_data()
            fields = []
            for key, value in form_data.items():
                display_key = key.replace('_', ' ').title()
                val_str = str(value)
                if len(val_str) > 200:
                    val_str = val_str[:200] + '...'
                fields.append({
                    'name': display_key,
                    'value': val_str or 'N/A',
                    'inline': len(val_str) < 50
                })

            embed = {
                'title': f'📋 New {application.app_type.name} Application',
                'description': f'**Applicant:** {application.applicant.username}\n**Discord ID:** {application.applicant.discord_id or "Not provided"}',
                'color': 0x3498db,
                'fields': fields[:25],
                'footer': {'text': f'Application #{application.id}'},
                'timestamp': application.created_at.isoformat() + 'Z'
            }

            payload = {'embeds': [embed]}
            resp = requests.post(webhook_url, json=payload, timeout=10)
            return resp.status_code in (200, 204)
        except Exception as e:
            current_app.logger.error(f'Discord webhook error: {e}')
            return False

    @staticmethod
    def send_status_update(application, webhook_url, old_status, reviewer):
        """Send application status update to Discord."""
        try:
            color_map = {
                'accepted': 0x2ecc71,
                'denied': 0xe74c3c,
                'pending': 0xf39c12,
            }
            status_emoji = {
                'accepted': '✅',
                'denied': '❌',
                'pending': '⏳',
            }

            embed = {
                'title': f'{status_emoji.get(application.status, "📋")} Application #{application.id} Updated',
                'description': (
                    f'**Applicant:** {application.applicant.username}\n'
                    f'**Type:** {application.app_type.name}\n'
                    f'**Status:** {old_status.title()} → **{application.status.title()}**\n'
                    f'**Reviewed by:** {reviewer.username}'
                ),
                'color': color_map.get(application.status, 0x95a5a6),
                'footer': {'text': f'Application #{application.id}'},
            }

            if application.denial_reason:
                embed['fields'] = [{'name': 'Reason', 'value': application.denial_reason}]

            payload = {'embeds': [embed]}
            resp = requests.post(webhook_url, json=payload, timeout=10)
            return resp.status_code in (200, 204)
        except Exception as e:
            current_app.logger.error(f'Discord webhook error: {e}')
            return False


class DiscordAPI:
    """Interact with the Discord Bot API for role management."""

    DISCORD_API_BASE = 'https://discord.com/api/v10'

    @classmethod
    def _get_headers(cls):
        token = current_app.config.get('DISCORD_BOT_TOKEN')
        if not token:
            return None
        return {
            'Authorization': f'Bot {token}',
            'Content-Type': 'application/json',
        }

    @classmethod
    def _get_guild_id(cls):
        return current_app.config.get('DISCORD_GUILD_ID')

    @classmethod
    def assign_role(cls, discord_user_id, role_id):
        """Assign a Discord role to a user."""
        headers = cls._get_headers()
        guild_id = cls._get_guild_id()

        if not headers:
            return False, 'Discord bot token not configured'
        if not guild_id:
            return False, 'Discord guild ID not configured'
        if not discord_user_id:
            return False, 'User has no Discord ID'

        url = f'{cls.DISCORD_API_BASE}/guilds/{guild_id}/members/{discord_user_id}/roles/{role_id}'

        try:
            resp = requests.put(url, headers=headers, timeout=10)
            if resp.status_code in (200, 204):
                return True, 'Role assigned successfully'
            else:
                error_msg = resp.json().get('message', resp.text) if resp.text else f'HTTP {resp.status_code}'
                current_app.logger.error(f'Discord role assign failed: {error_msg}')
                return False, f'Discord API error: {error_msg}'
        except Exception as e:
            current_app.logger.error(f'Discord role assign exception: {e}')
            return False, str(e)

    @classmethod
    def remove_role(cls, discord_user_id, role_id):
        """Remove a Discord role from a user."""
        headers = cls._get_headers()
        guild_id = cls._get_guild_id()

        if not headers or not guild_id or not discord_user_id:
            return False, 'Missing configuration'

        url = f'{cls.DISCORD_API_BASE}/guilds/{guild_id}/members/{discord_user_id}/roles/{role_id}'

        try:
            resp = requests.delete(url, headers=headers, timeout=10)
            if resp.status_code in (200, 204):
                return True, 'Role removed successfully'
            else:
                error_msg = resp.json().get('message', resp.text) if resp.text else f'HTTP {resp.status_code}'
                return False, f'Discord API error: {error_msg}'
        except Exception as e:
            current_app.logger.error(f'Discord role remove exception: {e}')
            return False, str(e)

    @classmethod
    def assign_multiple_roles(cls, discord_user_id, role_ids):
        """Assign multiple Discord roles to a user."""
        results = []
        for role_id in role_ids:
            success, message = cls.assign_role(discord_user_id, role_id)
            results.append({'role_id': role_id, 'success': success, 'message': message})
        return results

    @classmethod
    def get_member(cls, discord_user_id):
        """Get Discord member info."""
        headers = cls._get_headers()
        guild_id = cls._get_guild_id()

        if not headers or not guild_id:
            return None

        url = f'{cls.DISCORD_API_BASE}/guilds/{guild_id}/members/{discord_user_id}'

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception:
            return None
