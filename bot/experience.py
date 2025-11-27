import discord
import datetime
import asyncio
from discord import app_commands
from discord.ext import commands
from firebase_admin import db

class Experience(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_ref = db.reference('Experiences')
        self.ready = False
        self.listener = self.db_ref.listen(self.on_experience_change)

    def cog_unload(self):
        if self.listener:
            self.listener.close()

    def on_experience_change(self, event):
        if not self.ready:
            self.ready = True
            return

        if event.event_type == 'put':
            if event.path == '/':
                return
            
            # If path is like '/<exp_id>', it's a new experience or full update of one
            # If path is like '/<exp_id>/status', it's a status update
            
            path_parts = event.path.strip('/').split('/')
            if len(path_parts) == 1:
                # New experience added or fully updated
                exp_id = path_parts[0]
                data = event.data
                if data and isinstance(data, dict) and data.get('status') == 'pending':
                    asyncio.run_coroutine_threadsafe(self.notify_new_request(exp_id, data), self.bot.loop)

    async def notify_new_request(self, exp_id, data):
        server_id = data.get('server_id')
        if not server_id:
            return

        config_ref = db.reference(f'Request Notification Config/{server_id}')
        config = config_ref.get()
        
        if not config or not config.get('notification_channel'):
            return

        channel_id = config.get('notification_channel')
        role_id = config.get('notification_role')

        try:
            channel_id = int(channel_id)
            channel = self.bot.get_channel(channel_id)
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except:
                    return
            
            embed = discord.Embed(
                title="New Experience Request",
                description=f"A new experience request has been submitted for **{data.get('server_name', 'Unknown Server')}**.",
                color=discord.Color.yellow(),
                timestamp=datetime.datetime.now()
            )
            
            user_id = data.get('user_id', 'Unknown ID')
            embed.add_field(name="User", value=f"<@{user_id}> `({user_id})`", inline=False)
            embed.add_field(name="Role", value=data.get('role_title', 'N/A'), inline=True)
            
            start = f"{data.get('start_month')}/{data.get('start_year')}"
            end = f"{data.get('end_month')}/{data.get('end_year')}" if data.get('end_month') else "Present"
            embed.add_field(name="Duration", value=f"{start} - {end}", inline=True)
            
            if data.get('description'):
                desc = data.get('description')
                if len(desc) > 1024:
                    desc = desc[:1021] + "..."
                embed.add_field(name="Description", value=desc, inline=False)
            
            view_url = f"https://servercv.com/view/{server_id}" 
            embed.add_field(name="Actions", value=f"[View & Manage Request]({view_url})", inline=False)
            
            content = f"<@&{role_id}>" if role_id else None
            await channel.send(content=content, embed=embed)

        except Exception as e:
            print(f"Error sending notification: {e}")

    @app_commands.command(name="setup", description="Setup notifications for new experience requests")
    @app_commands.describe(channel="The channel to send notifications to", role="Optional role to ping")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_command(self, interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role = None):
        server_id = str(interaction.guild_id)
        update_data = {
            'notification_channel': str(channel.id)
        }
        if role:
            update_data['notification_role'] = str(role.id)
            
        db.reference(f'Request Notification Config/{server_id}').update(update_data)
        
        msg = f"✅ Notifications for new experience requests will be sent to {channel.mention}."
        if role:
            msg += f"\n🔔 Role to ping: {role.mention}"
            
        await interaction.response.send_message(msg, ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Experience(bot))