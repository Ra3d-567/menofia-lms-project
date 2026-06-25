from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
import os
import uuid

def get_book_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    return f'official_books/{uuid.uuid4().hex}{ext}'

def get_material_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    return f'materials/{uuid.uuid4().hex}{ext}'

def get_submission_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    # Optionally include university ID or user ID in filename
    user_id = instance.student.university_id or instance.student.id
    return f'submissions/{user_id}_{uuid.uuid4().hex}{ext}'

class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', _('Admin')
        DOCTOR = 'DOCTOR', _('Doctor')
        STUDENT = 'STUDENT', _('Student')

    ACADEMIC_YEAR_CHOICES = (
        (1, 'First Year'),
        (2, 'Second Year'),
        (3, 'Third Year'),
        (4, 'Fourth Year'),
    )

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    university_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    department = models.CharField(max_length=100, blank=True)
    academic_year = models.IntegerField(choices=ACADEMIC_YEAR_CHOICES, default=1, null=True, blank=True)
    section_group = models.IntegerField(
        null=True, 
        blank=True, 
        help_text=_('Section 1 to 5')
    )
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)

    REQUIRED_FIELDS = ['email', 'role']

    def __str__(self):
        return f"{self.username} - {self.get_role_display()}"


class Subject(models.Model):
    DAYS_OF_WEEK = (
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    )

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    official_book = models.FileField(upload_to=get_book_upload_path, blank=True, null=True)
    
    # ForeignKey to User filtering only for the DOCTOR role
    professor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        limit_choices_to={'role': User.Role.DOCTOR},
        related_name='subjects_taught'
    )
    lecture_day = models.IntegerField(choices=DAYS_OF_WEEK, null=True, blank=True)
    academic_year = models.IntegerField(choices=User.ACADEMIC_YEAR_CHOICES, default=1)

    def __str__(self):
        return f"{self.code}: {self.name}"


class SubjectSection(models.Model):
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='subject_sections'
    )
    section_group = models.IntegerField(choices=[(i, str(i)) for i in range(1, 6)])
    instructor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        limit_choices_to={'role': User.Role.DOCTOR},
        related_name='sections_taught'
    )
    section_day = models.IntegerField(choices=Subject.DAYS_OF_WEEK, null=True, blank=True)

    class Meta:
        unique_together = ('subject', 'section_group')

    def __str__(self):
        return f"{self.subject.code} - Section {self.section_group}"


class Material(models.Model):
    class MaterialType(models.TextChoices):
        LECTURE = 'LECTURE', _('Lecture')
        SECTION = 'SECTION', _('Section')

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    video_url = models.URLField(blank=True, null=True)
    file = models.FileField(upload_to=get_material_upload_path, blank=True, null=True)
    material_type = models.CharField(max_length=10, choices=MaterialType.choices, default=MaterialType.LECTURE)
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='materials'
    )
    subject_section = models.ForeignKey(
        SubjectSection,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='materials',
        help_text=_('Linked to a specific section if MaterialType is SECTION.')
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.get_material_type_display()}] {self.title} ({self.subject.code})"


class Assignment(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='assignments')
    subject_section = models.ForeignKey(
        SubjectSection, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='assignments',
        help_text=_('Linked to a specific section if created by a section instructor.')
    )
    due_date = models.DateTimeField()
    max_grade = models.FloatField(default=100.0)
    requirements_text = models.TextField(blank=True, null=True)
    max_file_size_mb = models.IntegerField(default=10)
    allowed_extensions = models.CharField(max_length=200, default='pdf,zip,docx,rar')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        section_info = f" (Section {self.subject_section.section_group})" if self.subject_section else ""
        return f"{self.title} - {self.subject.code}{section_info}"


class Submission(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        limit_choices_to={'role': User.Role.STUDENT}, 
        related_name='submissions'
    )
    submitted_file = models.FileField(upload_to=get_submission_upload_path)
    submitted_at = models.DateTimeField(auto_now_add=True)
    grade = models.FloatField(null=True, blank=True)
    feedback = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('assignment', 'student')

    def __str__(self):
        return f"{self.student.username} - {self.assignment.title}"


class Announcement(models.Model):
    title = models.CharField(max_length=255)
    content = models.TextField()
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='announcements_made')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='announcements')
    subject_section = models.ForeignKey(
        SubjectSection, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='section_announcements',
        help_text=_('Linked to a specific section if created by a section instructor.')
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        section_info = f" (Section {self.subject_section.section_group})" if self.subject_section else " (General)"
        return f"{self.title} - {self.subject.code}{section_info}"


class AttendanceSession(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='attendance_sessions')
    subject_section = models.ForeignKey(SubjectSection, on_delete=models.CASCADE, null=True, blank=True, related_name='section_attendance_sessions')
    date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(default=timezone.now)
    instructor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attendance_taken')
    pin_code = models.CharField(max_length=4, null=True, blank=True)
    pin_duration_minutes = models.IntegerField(default=5)
    is_makeup_class = models.BooleanField(default=False)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        section_info = f" (Section {self.subject_section.section_group})" if self.subject_section else " (General)"
        return f"{self.subject.code}{section_info} - {self.date}"

class AttendanceRecord(models.Model):
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name='records')
    student = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': User.Role.STUDENT}, related_name='attendance_records')
    is_present = models.BooleanField(default=False)

    class Meta:
        unique_together = ['session', 'student']

    def __str__(self):
        return f"{self.student.username} - {'Present' if self.is_present else 'Absent'}"
