import os
import datetime
import csv
import django
import discord
from discord import app_commands
from discord.ext import commands

# Setup Django environment so we can use models
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lms_project.settings')
django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from asgiref.sync import sync_to_async

# Requires message content intent to read commands (still good to keep)
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

def is_owner_interaction():
    async def predicate(interaction: discord.Interaction) -> bool:
        owner_id = getattr(settings, 'DISCORD_OWNER_ID', None)
        if owner_id and str(interaction.user.id) == str(owner_id):
            return True
        return False
    return app_commands.check(predicate)

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("❌ Unauthorized: You do not have permission to use this command.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ An error occurred: {str(error)}", ephemeral=True)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'✅ Logged in securely as {bot.user} (ID: {bot.user.id})')
    print('✅ Slash commands synced.')
    print('------')

@sync_to_async
def create_superuser_sync(username, password):
    User = get_user_model()
    if User.objects.filter(username=username).exists():
        return False
    User.objects.create_superuser(
        username=username,
        password=password,
        email=f"{username}@admin.local",
        role=User.Role.ADMIN
    )
    return True

@bot.tree.command(name='create_admin', description="Create a Django superuser account securely")
@app_commands.describe(username="The username for the admin", password="The password for the admin")
@is_owner_interaction()
async def create_admin(interaction: discord.Interaction, username: str, password: str):
    try:
        success = await create_superuser_sync(username, password)
        if not success:
            await interaction.response.send_message(f"⚠️ User `{username}` already exists.", ephemeral=True)
            return

        await interaction.response.send_message(f"✅ Success! Admin account `{username}` has been securely created.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to create admin: `{str(e)}`", ephemeral=True)

@bot.tree.command(name='backup', description="Generate a backup of the SQLite database")
@is_owner_interaction()
async def backup(interaction: discord.Interaction):
    try:
        db_path = settings.BASE_DIR / 'db.sqlite3'
        
        if not os.path.exists(db_path):
            await interaction.response.send_message("❌ Error: Database file `db.sqlite3` not found.", ephemeral=True)
            return
            
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M')
        filename = f"backup_{timestamp}.sqlite3"
        
        await interaction.response.send_message("⏳ Processing database backup...", ephemeral=True)
        # We can edit the original response to attach the file
        await interaction.edit_original_response(content="✅ Backup complete.", attachments=[discord.File(fp=str(db_path), filename=filename)])
        
    except Exception as e:
        await interaction.edit_original_response(content=f"❌ Backup failed: `{str(e)}`\n*(Note: Discord has an 8MB file size limit for free servers. If your database is larger than this, the backup will fail.)*")

@sync_to_async
def assign_target_sync(target_type, target_id, material_id):
    User = get_user_model()
    from lms_app.models import Subject
    
    try:
        subject = Subject.objects.get(id=material_id)
    except Subject.DoesNotExist:
        return {"success": False, "message": f"❌ Error: Subject ID `{material_id}` not found."}

    target_type = target_type.lower()
    
    if target_type == 'student':
        try:
            student = User.objects.get(university_id=target_id, role=User.Role.STUDENT)
            student.registered_subjects.add(subject)
            return {
                "success": True, 
                "title": "🎓 Student Assignment Success", 
                "description": f"**Student:** {student.first_name} {student.last_name} ({student.university_id})\n**Subject Assigned:** {subject.name} ({subject.code})"
            }
        except User.DoesNotExist:
            return {"success": False, "message": f"❌ Error: Student with Academic Code `{target_id}` not found."}
            
    elif target_type == 'doctor':
        try:
            doctor = User.objects.get(id=target_id, role=User.Role.DOCTOR)
            subject.professor = doctor
            subject.save()
            return {
                "success": True, 
                "title": "👨‍🏫 Doctor Assignment Success", 
                "description": f"**Doctor:** {doctor.first_name} {doctor.last_name}\n**Subject Assigned:** {subject.name} ({subject.code})"
            }
        except User.DoesNotExist:
            return {"success": False, "message": f"❌ Error: Doctor with ID `{target_id}` not found."}
            
    elif target_type == 'section':
        try:
            section_group = int(target_id)
            students = User.objects.filter(role=User.Role.STUDENT, section_group=section_group, academic_year=subject.academic_year)
            count = students.count()
            
            if count == 0:
                return {"success": False, "message": f"⚠️ Warning: No students found in Section `{section_group}` for Academic Year `{subject.academic_year}`."}
                
            subject.enrolled_students.add(*list(students))
            
            return {
                "success": True, 
                "title": "👥 Section Bulk Assignment Success", 
                "description": f"**Section Group:** {section_group}\n**Subject Assigned:** {subject.name} ({subject.code})\n**Students Updated:** {count}"
            }
        except ValueError:
            return {"success": False, "message": "❌ Error: Section target_id must be an integer (e.g., 1, 2, 3)."}
            
    else:
        return {"success": False, "message": f"❌ Error: Invalid target type `{target_type}`. Use `student`, `doctor`, or `section`."}

@bot.tree.command(name='assign', description="Assign a student, doctor, or section to a subject")
@app_commands.describe(target_type="student, doctor, or section", target_id="University ID, Doctor ID, or Section Group (1-5)", material_id="Subject ID")
@is_owner_interaction()
async def assign(interaction: discord.Interaction, target_type: str, target_id: str, material_id: int):
    try:
        result = await assign_target_sync(target_type, target_id, material_id)
        if not result["success"]:
            await interaction.response.send_message(result["message"], ephemeral=True)
            return
            
        embed = discord.Embed(title=result["title"], description=result["description"], color=0x00FF00)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ Critical Error in Assignment: `{str(e)}`", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Critical Error in Assignment: `{str(e)}`", ephemeral=True)

@sync_to_async
def set_global_announcement(message):
    from lms_app.models import GlobalAnnouncement
    if message.lower() == 'off':
        GlobalAnnouncement.objects.update(is_active=False)
        return False
    else:
        GlobalAnnouncement.objects.update(is_active=False)
        GlobalAnnouncement.objects.create(message=message, is_active=True)
        return True

@bot.tree.command(name='announce', description="Broadcast a global UI announcement. Use 'off' to disable.")
@app_commands.describe(message="The message to announce, or 'off' to turn off.")
@is_owner_interaction()
async def announce(interaction: discord.Interaction, message: str):
    try:
        is_on = await set_global_announcement(message)
        if not is_on:
            embed = discord.Embed(title="🔇 Announcement Cleared", description="The global UI announcement has been deactivated.", color=0xFF0000)
        else:
            embed = discord.Embed(title="📢 Announcement Live", description=f"Successfully broadcasted to the main UI:\n\n**{message}**", color=0x00FF00)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error broadcasting announcement: `{str(e)}`", ephemeral=True)

@bot.tree.command(name='maintenance', description="Enable or disable maintenance lockdown mode")
@app_commands.describe(enable="True to activate lockdown, False to unlock")
@is_owner_interaction()
async def maintenance(interaction: discord.Interaction, enable: bool):
    try:
        lockdown_file = settings.BASE_DIR / 'lockdown.flag'
        if enable:
            with open(lockdown_file, 'w') as f:
                f.write('maintenance mode active')
            embed = discord.Embed(title="🚨 SYSTEM LOCKDOWN 🚨", description="Maintenance mode has been ACTIVATED. All standard users are now blocked from accessing the site. Admin portal remains active.", color=0xFF0000)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            if lockdown_file.exists():
                import os
                os.remove(lockdown_file)
                embed = discord.Embed(title="🟢 SYSTEM UNLOCKED", description="Maintenance mode has been DEACTIVATED. All systems are operational and users can now access the site.", color=0x00FF00)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message("ℹ️ The system is already unlocked (no lockdown.flag found).", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error toggling maintenance: `{str(e)}`", ephemeral=True)

@sync_to_async
def generate_student_export(filename):
    User = get_user_model()
    students = User.objects.filter(role=User.Role.STUDENT)
    
    with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['University ID', 'Full Name', 'Academic Year', 'Registered Subjects Count'])
        
        for student in students:
            subject_count = student.registered_subjects.count()
            writer.writerow([
                student.university_id or '',
                f"{student.first_name} {student.last_name}".strip() or student.username,
                student.academic_year or 'N/A',
                subject_count
            ])
    return filename

@bot.tree.command(name='export_data', description="Export a CSV of student analytics")
@is_owner_interaction()
async def export_data(interaction: discord.Interaction):
    try:
        filename = "student_analytics_export.csv"
        await interaction.response.send_message("⏳ Generating data export...", ephemeral=True)
        
        await generate_student_export(filename)
        
        await interaction.edit_original_response(content="📊 **Data Export Complete!** Here is your analytical CSV file ready for Power BI / Excel.", attachments=[discord.File(fp=filename)])
        
        if os.path.exists(filename):
            os.remove(filename)
    except Exception as e:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ Error generating export: `{str(e)}`", ephemeral=True)
        else:
            await interaction.edit_original_response(content=f"❌ Error generating export: `{str(e)}`")

@sync_to_async
def reset_axes_sync(username=None):
    from axes.utils import reset
    if username:
        return reset(username=username)
    return reset()

@bot.tree.command(name='unban', description="Lift IP and User security lockouts")
@app_commands.describe(username="Optional username to unban, leave empty to unban everyone")
@is_owner_interaction()
async def unban(interaction: discord.Interaction, username: str = None):
    try:
        count = await reset_axes_sync(username)
        if username:
            embed = discord.Embed(title="🛡️ Security Lockout Cleared", description=f"The IP/User block has been lifted specifically for user: **{username}**.", color=0x00FF00)
        else:
            embed = discord.Embed(title="🛡️ Security Lockouts Cleared", description="All global IP/User blocks have been successfully lifted.", color=0x00FF00)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error during unban: `{str(e)}`", ephemeral=True)

# ----------------- UI VIEWS ----------------- #

@sync_to_async
def get_live_stats_sync():
    User = get_user_model()
    from lms_app.models import Exam, Assignment
    students_count = User.objects.filter(role=User.Role.STUDENT).count()
    doctors_count = User.objects.filter(role=User.Role.DOCTOR).count()
    exams_count = Exam.objects.count()
    assignments_count = Assignment.objects.count()
    return {
        "students": students_count,
        "doctors": doctors_count,
        "exams": exams_count,
        "assignments": assignments_count
    }

class AdminPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Lockdown Site", style=discord.ButtonStyle.danger, emoji="🔴")
    async def btn_lockdown(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            lockdown_file = settings.BASE_DIR / 'lockdown.flag'
            with open(lockdown_file, 'w') as f:
                f.write('maintenance mode active')
            embed = discord.Embed(title="🚨 SYSTEM LOCKDOWN 🚨", description="Maintenance mode has been ACTIVATED. All standard users are now blocked from accessing the site. Admin portal remains active.", color=0xFF0000)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error initiating lockdown: `{str(e)}`", ephemeral=True)

    @discord.ui.button(label="Unlock Site", style=discord.ButtonStyle.success, emoji="🟢")
    async def btn_unlock(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            lockdown_file = settings.BASE_DIR / 'lockdown.flag'
            if lockdown_file.exists():
                import os
                os.remove(lockdown_file)
                embed = discord.Embed(title="🟢 SYSTEM UNLOCKED", description="Maintenance mode has been DEACTIVATED. All systems are operational and users can now access the site.", color=0x00FF00)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message("ℹ️ The system is already unlocked.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error lifting lockdown: `{str(e)}`", ephemeral=True)

    @discord.ui.button(label="Generate Backup", style=discord.ButtonStyle.primary, emoji="📊")
    async def btn_backup(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            db_path = settings.BASE_DIR / 'db.sqlite3'
            
            if not os.path.exists(db_path):
                await interaction.response.send_message("❌ Error: Database file `db.sqlite3` not found.", ephemeral=True)
                return
                
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M')
            filename = f"backup_{timestamp}.sqlite3"
            
            await interaction.response.send_message("⏳ Processing database backup...", ephemeral=True)
            await interaction.edit_original_response(content="✅ Backup complete.", attachments=[discord.File(fp=str(db_path), filename=filename)])
            
        except Exception as e:
            await interaction.edit_original_response(content=f"❌ Backup failed: `{str(e)}`")

    @discord.ui.button(label="Live Stats", style=discord.ButtonStyle.secondary, emoji="📈")
    async def btn_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            stats = await get_live_stats_sync()
            embed = discord.Embed(title="📈 Live Platform Statistics", color=0x3498db)
            embed.add_field(name="👨‍🎓 Students", value=str(stats['students']), inline=True)
            embed.add_field(name="👨‍🏫 Doctors", value=str(stats['doctors']), inline=True)
            embed.add_field(name="📝 Exams", value=str(stats['exams']), inline=True)
            embed.add_field(name="📚 Assignments", value=str(stats['assignments']), inline=True)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error fetching stats: `{str(e)}`", ephemeral=True)

@bot.tree.command(name='admin_panel', description="Open the Interactive Control Dashboard")
@is_owner_interaction()
async def admin_panel(interaction: discord.Interaction):
    embed = discord.Embed(title="🛠️ Admin Control Dashboard", description="Select an action below to manage the LMS.", color=0x3498db)
    await interaction.response.send_message(embed=embed, view=AdminPanelView(), ephemeral=True)


class UserApprovalView(discord.ui.View):
    def __init__(self, target_user_id: int):
        super().__init__(timeout=None)
        self.target_user_id = target_user_id
        
    @sync_to_async
    def toggle_user_status(self, is_approved: bool):
        User = get_user_model()
        try:
            user = User.objects.get(id=self.target_user_id)
            if is_approved:
                user.needs_review = False
                user.is_active = True
                user.save()
                return True, user
            else:
                user.is_active = False
                user.save()
                return True, user
        except User.DoesNotExist:
            return False, None

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="✅")
    async def btn_approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        success, user = await self.toggle_user_status(True)
        if success:
            await interaction.response.send_message(f"✅ User `{user.username}` approved successfully.", ephemeral=True)
            self.stop()
        else:
            await interaction.response.send_message("❌ Error: User not found.", ephemeral=True)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger, emoji="❌")
    async def btn_reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        success, user = await self.toggle_user_status(False)
        if success:
            await interaction.response.send_message(f"🚫 User `{user.username}` rejected and deactivated.", ephemeral=True)
            self.stop()
        else:
            await interaction.response.send_message("❌ Error: User not found.", ephemeral=True)

@sync_to_async
def get_student_info_sync(university_id):
    User = get_user_model()
    try:
        student = User.objects.get(university_id=university_id, role=User.Role.STUDENT)
        subjects_count = student.registered_subjects.count()
        return {
            "success": True,
            "full_name": f"{student.first_name} {student.last_name}".strip() or student.username,
            "academic_year": student.academic_year,
            "section_group": student.section_group,
            "subjects_count": subjects_count
        }
    except User.DoesNotExist:
        return {"success": False}

@bot.tree.command(name='student_info', description="Lookup a student by their University ID")
@app_commands.describe(university_id="The University ID of the student")
@is_owner_interaction()
async def student_info(interaction: discord.Interaction, university_id: str):
    try:
        info = await get_student_info_sync(university_id)
        if not info["success"]:
            await interaction.response.send_message(f"❌ Student with University ID `{university_id}` not found.", ephemeral=True)
            return
            
        embed = discord.Embed(title="🎓 Student Lookup", color=0x2ecc71)
        embed.add_field(name="Full Name", value=info['full_name'], inline=False)
        embed.add_field(name="Academic Year", value=str(info['academic_year']), inline=True)
        embed.add_field(name="Section Group", value=str(info['section_group']), inline=True)
        embed.add_field(name="Registered Subjects", value=str(info['subjects_count']), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: `{str(e)}`", ephemeral=True)

@sync_to_async
def notify_student_sync(university_id, message):
    User = get_user_model()
    from lms_app.models import Notification
    try:
        student = User.objects.get(university_id=university_id, role=User.Role.STUDENT)
        Notification.objects.create(
            recipient=student,
            message=message,
            link="#"
        )
        return True, f"{student.first_name} {student.last_name}".strip() or student.username
    except User.DoesNotExist:
        return False, None

@bot.tree.command(name='notify_student', description="Send a direct LMS notification to a student")
@app_commands.describe(university_id="The University ID of the student", message="The notification message")
@is_owner_interaction()
async def notify_student(interaction: discord.Interaction, university_id: str, message: str):
    try:
        success, name = await notify_student_sync(university_id, message)
        if not success:
            await interaction.response.send_message(f"❌ Student with University ID `{university_id}` not found.", ephemeral=True)
            return
            
        embed = discord.Embed(title="✅ Notification Sent", description=f"Successfully sent a notification to **{name}**:\n\n\"{message}\"", color=0x2ecc71)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: `{str(e)}`", ephemeral=True)

def run():
    token = getattr(settings, 'DISCORD_BOT_TOKEN', None)
    if not token or token == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("❌ Error: DISCORD_BOT_TOKEN is missing from settings.")
        return
        
    print("Starting Discord Admin Bot...")
    bot.run(token)

if __name__ == "__main__":
    run()
