import os
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


def get_book_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    return f'official_books/{uuid.uuid4().hex}{ext}'

def get_material_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    return f'materials/{uuid.uuid4().hex}{ext}'

def get_submission_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1]
    # Handle both old Submission and new SubmissionFile models
    if hasattr(instance, 'submission'):
        student = instance.submission.student
    else:
        student = instance.student
        
    user_id = student.university_id or student.id
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
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=[('Male', 'Male'), ('Female', 'Female')], null=True, blank=True)
    needs_review = models.BooleanField(default=False, help_text=_('Flagged for manual review (e.g. English name translation)'))
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    registered_subjects = models.ManyToManyField('Subject', blank=True, related_name='enrolled_students')

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
    code = models.CharField(max_length=20, unique=True, null=True, blank=True, verbose_name="كود المادة")
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
    max_total_grade = models.IntegerField(default=100)

    def __str__(self):
        return f"{self.code}: {self.name}"

    @property
    def students(self):
        return self.enrolled_students.filter(role=User.Role.STUDENT)


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
    max_total_grade = models.IntegerField(default=50)

    class Meta:
        unique_together = ('subject', 'section_group')

    def __str__(self):
        return f"{self.subject.code} - Section {self.section_group}"

    @property
    def students(self):
        return self.subject.enrolled_students.filter(role=User.Role.STUDENT, section_group=self.section_group)


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
    lecture = models.ForeignKey('Material', on_delete=models.CASCADE, null=True, blank=True, related_name='assignments')
    max_file_size_mb = models.PositiveIntegerField(default=10)
    max_files = models.PositiveIntegerField(default=1)
    allowed_extensions = models.CharField(max_length=200, default='.pdf,.docx,.zip')
    is_active = models.BooleanField(default=True, help_text="Manually open or close submissions")
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
    submitted_file = models.FileField(upload_to=get_submission_upload_path, null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    grade = models.FloatField(null=True, blank=True)
    feedback = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('assignment', 'student')

    def __str__(self):
        return f"{self.student.username} - {self.assignment.title}"


class SubmissionFile(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to=get_submission_upload_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"File for {self.submission}"


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

class AdminDevice(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trusted_devices')
    device_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    device_name = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.device_name or 'Unknown Device'}"
class GlobalAnnouncement(models.Model):
    message = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Global Announcement ({'Active' if self.is_active else 'Inactive'})"

class Notification(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message = models.CharField(max_length=500)
    link = models.CharField(max_length=500, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.recipient.username}"

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=User)
def auto_enroll_student_subjects(sender, instance, created, **kwargs):
    if created and instance.role == User.Role.STUDENT and instance.academic_year:
        subjects = Subject.objects.filter(academic_year=instance.academic_year)
        if subjects.exists():
            instance.registered_subjects.set(subjects)
            
        from lms_app.utils import send_discord_log
        send_discord_log(f"🎓 **New User Registration:** A new student ({instance.username}) has joined the platform!")

@receiver(post_save, sender=Material)
def log_new_material(sender, instance, created, **kwargs):
    if created:
        from lms_app.utils import send_discord_log
        send_discord_log(f"🟢 **New Content:** A new Material was just uploaded!")

@receiver(post_save, sender=Subject)
def log_new_subject(sender, instance, created, **kwargs):
    if created:
        from lms_app.utils import send_discord_log
        send_discord_log(f"🟢 **New Content:** A new Subject was just created!")

@receiver(post_save, sender=Assignment)
def log_new_assignment(sender, instance, created, **kwargs):
    if created:
        from lms_app.utils import send_discord_log
        send_discord_log(f"🟢 **New Content:** A new Assignment was just uploaded!")
        
        # Create notifications for students
        from django.urls import reverse
        
        link = reverse('subject_detail', args=[instance.subject.id])
        message = f"تم رفع تكليف جديد: {instance.title}"
        
        if instance.subject_section:
            students = User.objects.filter(role=User.Role.STUDENT, academic_year=instance.subject.academic_year, section_group=instance.subject_section.section_group)
        else:
            students = instance.subject.enrolled_students.all()
            
        notifications_to_create = []
        for student in students:
            notifications_to_create.append(
                Notification(recipient=student, message=message, link=link)
            )
        
        if notifications_to_create:
            Notification.objects.bulk_create(notifications_to_create)
class Exam(models.Model):
    subject = models.ForeignKey('Subject', on_delete=models.CASCADE, related_name='exams', verbose_name="المادة")
    title = models.CharField(max_length=200, verbose_name="عنوان الامتحان")
    description = models.TextField(blank=True, null=True, verbose_name="تعليمات الامتحان")
    
    EXAM_TYPE_CHOICES = (
        ('LECTURE', 'محاضرة'),
        ('SECTION', 'سكشن'),
    )
    exam_type = models.CharField(max_length=20, choices=EXAM_TYPE_CHOICES, default='LECTURE')
    creator = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_exams')
    subject_section = models.ForeignKey('SubjectSection', on_delete=models.CASCADE, null=True, blank=True, related_name='exams')
    
    # Time & Duration Controls
    start_date = models.DateTimeField(blank=True, null=True, verbose_name="تاريخ ووقت فتح الامتحان")
    end_date = models.DateTimeField(blank=True, null=True, verbose_name="تاريخ ووقت غلق الامتحان")
    duration_minutes = models.PositiveIntegerField(default=30, verbose_name="مدة الامتحان (بالدقائق)")
    is_active = models.BooleanField(default=False, verbose_name="مفعل (يمكن إيقافه يدوياً)")
    
    # Permissions & Visibility
    show_score = models.BooleanField(default=True, verbose_name="إظهار الدرجة للطالب بعد التسليم")
    show_answers = models.BooleanField(default=False, verbose_name="إظهار الإجابات الصحيحة للطالب")
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.subject.name}"

class Question(models.Model):
    QUESTION_TYPES = (
        ('MCQ', 'اختيار من متعدد'),
        ('TF', 'صح وخطأ'),
    )
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField(verbose_name="نص السؤال")
    question_type = models.CharField(max_length=3, choices=QUESTION_TYPES, default='MCQ', verbose_name="نوع السؤال")
    marks = models.PositiveIntegerField(default=1, verbose_name="درجة السؤال")

    def __str__(self):
        return self.text

class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    text = models.CharField(max_length=255, verbose_name="نص الاختيار")
    is_correct = models.BooleanField(default=False, verbose_name="إجابة صحيحة")

    def __str__(self):
        return self.text

class ExamAttempt(models.Model):
    student = models.ForeignKey('User', on_delete=models.CASCADE, related_name='exam_attempts', verbose_name="الطالب")
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='attempts', verbose_name="الامتحان")
    start_time = models.DateTimeField(auto_now_add=True, verbose_name="وقت البدء")
    end_time = models.DateTimeField(blank=True, null=True, verbose_name="وقت التسليم")
    score = models.FloatField(default=0.0, verbose_name="الدرجة")
    is_submitted = models.BooleanField(default=False, verbose_name="تم التسليم")

    class Meta:
        unique_together = ('student', 'exam') # Ensure one attempt per student

    def __str__(self):
        return f"{self.student.username} - {self.exam.title}"

class StudentAnswer(models.Model):
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name='answers', verbose_name="المحاولة")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, verbose_name="السؤال")
    selected_choice = models.ForeignKey(Choice, on_delete=models.CASCADE, null=True, blank=True, verbose_name="الاختيار المحدد")

    class Meta:
        unique_together = ('attempt', 'question') # One answer per question per attempt

    def __str__(self):
        return f"{self.attempt.student.username} - {self.question.text[:20]}"
