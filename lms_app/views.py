import csv
import datetime
import io
import random
import re
from datetime import timedelta

import openpyxl
from django.contrib import messages
from django.contrib.auth import (authenticate, login, logout,
                                 update_session_auth_hash)
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.core.exceptions import PermissionDenied
from django.db.models import (Count, F, IntegerField, OuterRef, Prefetch, Q,
                              Subquery, Sum)
from django.db.models.functions import Coalesce
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from lms_project.discord_alerts import send_activity_alert

from .forms import UserProfileForm
from .models import (Announcement, Assignment, Choice, Exam, ExamAttempt,
                     Material, Question, StudentAnswer, Subject,
                     SubjectSection, Submission, SubmissionFile, User)


def home_redirect(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if request.user.role == User.Role.STUDENT:
        return redirect('student_dashboard')
    if request.user.role == User.Role.DOCTOR:
        return redirect('doctor_dashboard')
    if request.user.role == User.Role.ADMIN or request.user.is_superuser:
        return redirect('admin:index')
    return redirect('login')

def custom_lockout_response(request, credentials=None, *args, **kwargs):
    messages.error(request, "لقد تجاوزت الحد الأقصى لمحاولات الدخول. برجاء المحاولة مرة أخرى بعد 10 دقائق.")
    return redirect('login')

def user_login(request):
    error_message = None
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                if user.role == User.Role.ADMIN or user.is_superuser or user.is_staff:
                    messages.error(request, "عفواً، لا يمكن للإدارة أو الشؤون تسجيل الدخول من هذه الصفحة. يرجى التوجه للرابط السري الخاص بالإدارة.")
                    return redirect('login')
                login(request, user)
                if user.role == User.Role.DOCTOR:
                    return redirect('doctor_dashboard')
                elif user.role == User.Role.STUDENT:
                    return redirect('student_dashboard')
        else:
            # Check if the user exists but is inactive
            username = request.POST.get('username')
            if username:
                try:
                    user = User.objects.get(username=username)
                    if not user.is_active:
                        error_message = "Account suspended. Please contact Student Affairs."
                except User.DoesNotExist:
                    pass
    else:
        form = AuthenticationForm()
    return render(request, 'login.html', {'form': form, 'error_message': error_message})

def user_logout(request):
    is_admin = request.path.startswith('/secret-uni-portal/')
    logout(request)
    if is_admin:
        return redirect('/secret-uni-portal/')
    return redirect('login')

def is_doctor(user):
    # Only allow access if the user is authenticated and has the DOCTOR role
    return user.is_authenticated and user.role == User.Role.DOCTOR

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def doctor_dashboard(request):
    # Query subjects where the doctor is the main professor
    main_subjects = Subject.objects.filter(professor=request.user).prefetch_related('assignments', 'materials', 'subject_sections')
    
    # Query sections where the doctor is the specific instructor
    assigned_sections = SubjectSection.objects.filter(instructor=request.user).select_related('subject').prefetch_related('materials', 'assignments')
    
    context = {
        'main_subjects': main_subjects,
        'assigned_sections': assigned_sections,
        'now': timezone.now(),
        'DAYS_OF_WEEK': Subject.DAYS_OF_WEEK,
    }
    return render(request, 'doctor_dashboard.html', context)

def is_student(user):
    # Only allow access if the user is authenticated and has the STUDENT role
    return user.is_authenticated and user.role == User.Role.STUDENT

@login_required(login_url='/login/')
@user_passes_test(is_student, login_url='/login/')
def student_dashboard(request):
    # Query subjects based on explicit enrollment
    subjects = request.user.registered_subjects.all().select_related('professor').prefetch_related('assignments', 'materials')
    
    # Get all IDs to filter related data
    enrolled_subject_ids = subjects.values_list('id', flat=True)
    
    # Pre-fetch user submissions to avoid N+1 and attach to assignments
    user_submissions = {sub.assignment_id: sub for sub in request.user.submissions.all()}
    
    now = timezone.now()
    
    for subject in subjects:
        for assignment in subject.assignments.all():
            assignment.user_submission = user_submissions.get(assignment.id)
    announcements = Announcement.objects.filter(
        Q(subject_id__in=enrolled_subject_ids) &
        (Q(subject_section__isnull=True) | Q(subject_section__section_group=request.user.section_group)) &
        Q(is_active=True) &
        (Q(expires_at__isnull=True) | Q(expires_at__gt=now))
    ).select_related('author', 'subject', 'subject_section').order_by('-created_at')
    
    announcements_count = announcements.count()

    context = {
        'subjects': subjects,
        'announcements': announcements,
        'announcements_count': announcements_count,
    }
    return render(request, 'student_dashboard.html', context)

@login_required
@user_passes_test(is_student, login_url='/login/')
def student_settings(request):
    if request.method == 'POST':
        if 'profile_update' in request.POST:
            profile_form = UserProfileForm(request.POST, request.FILES, instance=request.user)
            password_form = PasswordChangeForm(request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'تم تحديث الملف الشخصي بنجاح!')
                return redirect('student_settings')
            else:
                messages.error(request, 'يرجى تصحيح الأخطاء في الملف الشخصي.')
        elif 'password_change' in request.POST:
            profile_form = UserProfileForm(instance=request.user)
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'تم تحديث كلمة المرور بنجاح!')
                return redirect('student_settings')
            else:
                messages.error(request, 'يرجى تصحيح الأخطاء في كلمة المرور.')
    else:
        profile_form = UserProfileForm(instance=request.user)
        password_form = PasswordChangeForm(request.user)
        
    return render(request, 'student_settings.html', {
        'profile_form': profile_form,
        'form': password_form
    })

@login_required
@user_passes_test(is_doctor, login_url='/login/')
def doctor_settings(request):
    if request.method == 'POST':
        if 'profile_update' in request.POST:
            profile_form = UserProfileForm(request.POST, request.FILES, instance=request.user)
            password_form = PasswordChangeForm(request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'تم تحديث الملف الشخصي بنجاح!')
                return redirect('doctor_settings')
            else:
                messages.error(request, 'يرجى تصحيح الأخطاء في الملف الشخصي.')
        elif 'password_change' in request.POST:
            profile_form = UserProfileForm(instance=request.user)
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'تم تحديث كلمة المرور بنجاح!')
                return redirect('doctor_settings')
            else:
                messages.error(request, 'يرجى تصحيح الأخطاء في كلمة المرور.')
    else:
        profile_form = UserProfileForm(instance=request.user)
        password_form = PasswordChangeForm(request.user)
        
    return render(request, 'doctor_settings.html', {
        'profile_form': profile_form,
        'form': password_form
    })

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def upload_material(request, subject_id):
    if request.method == 'POST':
        subject = get_object_or_404(Subject, id=subject_id, professor=request.user)
        title = request.POST.get('title')
        description = request.POST.get('description')
        video_url = request.POST.get('video_url')
        uploaded_file = request.FILES.get('file')
        material_type = Material.MaterialType.LECTURE
        
        if title and (uploaded_file or video_url or description):
            Material.objects.create(
                subject=subject,
                title=title,
                description=description,
                video_url=video_url,
                file=uploaded_file,
                material_type=material_type
            )
    return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/doctor/dashboard/'))

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def upload_material_section(request, section_id):
    if request.method == 'POST':
        section = get_object_or_404(SubjectSection, id=section_id, instructor=request.user)
        title = request.POST.get('title')
        description = request.POST.get('description')
        video_url = request.POST.get('video_url')
        uploaded_file = request.FILES.get('file')
        material_type = Material.MaterialType.SECTION
        
        if title and (uploaded_file or video_url or description):
            Material.objects.create(
                subject=section.subject,
                subject_section=section,
                title=title,
                description=description,
                video_url=video_url,
                file=uploaded_file,
                material_type=material_type
            )
    return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/doctor/dashboard/'))

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def delete_material(request, material_id):
    material = get_object_or_404(Material, id=material_id)
    
    # Check if the user owns this material (either main professor or section instructor)
    is_professor = material.subject.professor == request.user
    is_instructor = material.subject_section and material.subject_section.instructor == request.user
    
    if not (is_professor or is_instructor):
        raise PermissionDenied("You do not have permission to delete this material.")
        
    if request.method == 'POST':
        if material.file:
            material.file.delete() # Delete the file from storage
        material.delete() # Delete the object
        
    return redirect(request.META.get('HTTP_REFERER', 'doctor_dashboard'))

@login_required(login_url='/login/')
def lecture_detail(request, lecture_id):
    lecture = get_object_or_404(Material, id=lecture_id)
    
    if request.user.role == User.Role.STUDENT:
        if not request.user.registered_subjects.filter(id=lecture.subject.id).exists():
            raise PermissionDenied("You are not enrolled in the subject for this item.")
    
    # Optional: We could parse and clean the YouTube URL here, 
    # but we will handle it via JS in the template for better flexibility.
    
    return render(request, 'lecture_detail.html', {
        'lecture': lecture,
        'subject': lecture.subject
    })

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def edit_lecture(request, lecture_id):
    material = get_object_or_404(Material, id=lecture_id)
    
    # Ensure the user is the doctor of this subject or section
    is_professor = request.user == material.subject.professor
    is_instructor = material.subject_section and request.user == material.subject_section.instructor
    
    if not (is_professor or is_instructor):
        raise PermissionDenied("You do not have permission to edit this material.")
        
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        video_url = request.POST.get('video_url')
        uploaded_file = request.FILES.get('file')
        
        if title:
            material.title = title
            material.description = description
            material.video_url = video_url
            if uploaded_file:
                # Optionally delete the old file
                if material.file:
                    material.file.delete()
                material.file = uploaded_file
            material.save()
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', f'/lecture/{material.id}/'))
            
    return render(request, 'edit_lecture.html', {
        'material': material,
        'subject': material.subject
    })

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def create_assignment(request, subject_id):
    if request.method == 'POST':
        subject = get_object_or_404(Subject, id=subject_id, professor=request.user)
        title = request.POST.get('title')
        description = request.POST.get('description', '')
        due_date = request.POST.get('due_date')
        max_grade = request.POST.get('max_grade', 100)
        requirements_text = request.POST.get('requirements_text', '')
        max_file_size_mb = request.POST.get('max_file_size_mb', 10)
        max_files = request.POST.get('max_files', 1)
        allowed_extensions = request.POST.get('allowed_extensions', 'pdf,zip,docx,rar')
        lecture_id = request.POST.get('lecture_id')
        lecture = None
        if lecture_id:
            lecture = Material.objects.filter(id=lecture_id, subject=subject).first()

        if title and due_date:
            Assignment.objects.create(
                subject=subject,
                title=title,
                description=description,
                due_date=due_date,
                max_grade=max_grade,
                requirements_text=requirements_text,
                lecture=lecture,
                max_files=max_files,
                max_file_size_mb=max_file_size_mb,
                allowed_extensions=allowed_extensions
            )
    return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/doctor/dashboard/'))

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def create_assignment_section(request, section_id):
    if request.method == 'POST':
        section = get_object_or_404(SubjectSection, id=section_id, instructor=request.user)
        title = request.POST.get('title')
        description = request.POST.get('description', '')
        due_date = request.POST.get('due_date')
        max_grade = request.POST.get('max_grade', 100)
        requirements_text = request.POST.get('requirements_text', '')
        max_file_size_mb = request.POST.get('max_file_size_mb', 10)
        max_files = request.POST.get('max_files', 1)
        allowed_extensions = request.POST.get('allowed_extensions', 'pdf,zip,docx,rar')
        lecture_id = request.POST.get('lecture_id')
        lecture = None
        if lecture_id:
            lecture = Material.objects.filter(id=lecture_id, subject_section=section).first()

        if title and due_date:
            Assignment.objects.create(
                subject=section.subject,
                subject_section=section,
                title=title,
                description=description,
                due_date=due_date,
                max_grade=max_grade,
                requirements_text=requirements_text,
                lecture=lecture,
                max_files=max_files,
                max_file_size_mb=max_file_size_mb,
                allowed_extensions=allowed_extensions
            )
    return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/doctor/dashboard/'))

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def toggle_assignment_status(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id)
    if assignment.subject_section and assignment.subject_section.instructor != request.user:
        if assignment.subject.professor != request.user:
            raise PermissionDenied("You do not have permission to toggle this assignment.")
    elif not assignment.subject_section and assignment.subject.professor != request.user:
        raise PermissionDenied("You do not have permission to toggle this assignment.")
        
    assignment.is_active = not assignment.is_active
    assignment.save()
    status_str = "مفتوح" if assignment.is_active else "مغلق"
    messages.success(request, f"تم تغيير حالة التكليف بنجاح إلى: {status_str}")
    return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/doctor/dashboard/'))

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def edit_assignment(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id)
    if assignment.subject_section and assignment.subject_section.instructor != request.user:
        if assignment.subject.professor != request.user:
            raise PermissionDenied("You do not have permission to edit this assignment.")
    elif not assignment.subject_section and assignment.subject.professor != request.user:
        raise PermissionDenied("You do not have permission to edit this assignment.")
        
    if request.method == 'POST':
        assignment.title = request.POST.get('title', assignment.title)
        assignment.description = request.POST.get('description', assignment.description)
        
        due_date = request.POST.get('due_date')
        if due_date:
            assignment.due_date = due_date
            
        assignment.max_grade = request.POST.get('max_grade', assignment.max_grade)
        assignment.max_files = request.POST.get('max_files', assignment.max_files)
        assignment.max_file_size_mb = request.POST.get('max_file_size_mb', assignment.max_file_size_mb)
        assignment.allowed_extensions = request.POST.get('allowed_extensions', assignment.allowed_extensions)
        
        lecture_id = request.POST.get('lecture_id')
        if lecture_id:
            if assignment.subject_section:
                lecture = Material.objects.filter(id=lecture_id, subject_section=assignment.subject_section).first()
            else:
                lecture = Material.objects.filter(id=lecture_id, subject=assignment.subject).first()
            if lecture:
                assignment.lecture = lecture
        elif lecture_id == "":
            assignment.lecture = None

        assignment.save()
        messages.success(request, "تم تعديل التكليف بنجاح.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/doctor/dashboard/'))
        
    if assignment.subject_section:
        materials = Material.objects.filter(subject_section=assignment.subject_section)
    else:
        materials = Material.objects.filter(subject=assignment.subject, subject_section__isnull=True)
        
    return render(request, 'edit_assignment.html', {
        'assignment': assignment,
        'materials': materials
    })

@login_required(login_url='/login/')
@user_passes_test(is_student, login_url='/login/')
def submit_assignment(request, assignment_id):
    if request.method == 'POST':
        assignment = get_object_or_404(Assignment, id=assignment_id)
        
        if not request.user.registered_subjects.filter(id=assignment.subject.id).exists():
            raise PermissionDenied("You are not enrolled in the subject for this assignment.")
        
        if not assignment.is_active:
            messages.error(request, 'هذا التكليف مغلق حالياً ولا يقبل تسليمات جديدة.')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/student/dashboard/'))
            
        if timezone.now() > assignment.due_date:
            messages.error(request, "Deadline has passed. You cannot submit this assignment.")
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/student/dashboard/'))
            
        submitted_files = request.FILES.getlist('files')

        if submitted_files:
            if len(submitted_files) > assignment.max_files:
                messages.error(request, f"You can upload a maximum of {assignment.max_files} files.")
                return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/student/dashboard/'))

            import os
            allowed_exts = [ext.strip().lower() for ext in assignment.allowed_extensions.split(',') if ext.strip()]
            
            # Validate all files before creating any records
            for f in submitted_files:
                file_ext = os.path.splitext(f.name)[1].lower()
                if file_ext not in allowed_exts:
                    messages.error(request, f"الملف {f.name} غير مدعوم. الامتدادات المسموحة: {assignment.allowed_extensions}")
                    return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/student/dashboard/'))
                
                if f.size > assignment.max_file_size_mb * 1024 * 1024:
                    messages.error(request, f"File {f.name} exceeds the maximum limit of {assignment.max_file_size_mb} MB.")
                    return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/student/dashboard/'))

            submission, created = Submission.objects.update_or_create(
                assignment=assignment,
                student=request.user
            )
            
            # Clean up old files if they exist (in SubmissionFile model)
            for old_file in submission.files.all():
                if old_file.file:
                    old_file.file.delete(save=False) # Delete physical file
                old_file.delete() # Delete DB record
            
            # Create new SubmissionFile records
            for f in submitted_files:
                SubmissionFile.objects.create(submission=submission, file=f)

            messages.success(request, "Assignment submitted successfully.")
    return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/student/dashboard/'))

@login_required(login_url='/login/')
@user_passes_test(is_student, login_url='/login/')
def unsubmit_assignment(request, submission_id):
    if request.method == 'POST':
        # Strictly enforce ownership by filtering by student=request.user
        submission = get_object_or_404(Submission, id=submission_id, student=request.user)
        
        if submission.grade is not None:
            messages.error(request, "You cannot unsubmit an assignment that has already been graded.")
        else:
            # Delete associated files
            for old_file in submission.files.all():
                if old_file.file:
                    old_file.file.delete(save=False) # Delete physical file
                old_file.delete() # Delete DB record
            if submission.submitted_file: # old backward compatible field
                submission.submitted_file.delete(save=False)
                
            submission.delete()
            messages.success(request, "Your submission has been cancelled. You may re-upload a new file.")
            
    return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/student/dashboard/'))

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def view_submissions(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id)
    
    # Ensure the doctor owns the assignment
    is_professor = assignment.subject.professor == request.user
    is_instructor = assignment.subject_section and assignment.subject_section.instructor == request.user
    
    if not (is_professor or is_instructor):
        raise PermissionDenied("You do not have permission to view these submissions.")

    submissions = assignment.submissions.all().select_related('student')
    context = {
        'assignment': assignment,
        'submissions': submissions,
    }
    return render(request, 'submissions_list.html', context)

import io
import zipfile

from django.http import HttpResponse


@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def download_all_submissions(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id)
    
    is_professor = assignment.subject.professor == request.user
    is_instructor = assignment.subject_section and assignment.subject_section.instructor == request.user
    
    if not (is_professor or is_instructor):
        raise PermissionDenied("You do not have permission to download these submissions.")

    # Create a zip file in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for submission in assignment.submissions.all():
            # Old single file field
            if submission.submitted_file and submission.submitted_file.name:
                try:
                    file_name = f"{submission.student.university_id or submission.student.id}_{submission.student.username}/{submission.submitted_file.name.split('/')[-1]}"
                    zip_file.writestr(file_name, submission.submitted_file.read())
                except Exception:
                    pass
            # New SubmissionFile model
            for sub_file in submission.files.all():
                if sub_file.file and sub_file.file.name:
                    try:
                        file_name = f"{submission.student.university_id or submission.student.id}_{submission.student.username}/{sub_file.file.name.split('/')[-1]}"
                        zip_file.writestr(file_name, sub_file.file.read())
                    except Exception:
                        pass
                        
    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="Assignment_{assignment.id}_Submissions.zip"'
    return response

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def grade_submission(request, submission_id):
    if request.method == 'POST':
        submission = get_object_or_404(Submission, id=submission_id)
        
        # Ensure the doctor owns the assignment
        assignment = submission.assignment
        is_professor = assignment.subject.professor == request.user
        is_instructor = assignment.subject_section and assignment.subject_section.instructor == request.user
        
        if not (is_professor or is_instructor):
            raise PermissionDenied("You do not have permission to grade this submission.")
            
        grade = request.POST.get('grade')
        feedback = request.POST.get('feedback')
        if grade:
            grade_val = float(grade)
            if grade_val < 0 or grade_val > assignment.max_score:
                messages.error(request, f"يجب أن تكون الدرجة بين 0 و {assignment.max_score}")
                return redirect('view_submissions', assignment_id=assignment.id)
            submission.grade = grade_val
        if feedback is not None:
            submission.feedback = feedback
        submission.save()
        messages.success(request, 'Grade and feedback updated successfully.')
                
        return redirect('view_submissions', assignment_id=assignment.id)
    return redirect('doctor_dashboard')

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def delete_assignment(request, assignment_id):
    if request.method == 'POST':
        assignment = get_object_or_404(Assignment, id=assignment_id)
        
        # Ensure the doctor owns the assignment
        is_professor = assignment.subject.professor == request.user
        is_instructor = assignment.subject_section and assignment.subject_section.instructor == request.user
        
        if not (is_professor or is_instructor):
            raise PermissionDenied("You do not have permission to delete this assignment.")
            
        assignment.delete()
        messages.success(request, "Assignment deleted successfully.")
            
    return redirect('doctor_dashboard')

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def create_announcement(request, subject_id):
    if request.method == 'POST':
        subject = get_object_or_404(Subject, id=subject_id, professor=request.user)
        title = request.POST.get('title')
        content = request.POST.get('content')
        expires_at = request.POST.get('expires_at') or None

        if title and content:
            Announcement.objects.create(
                title=title,
                content=content,
                author=request.user,
                subject=subject,
                expires_at=expires_at
            )
    return redirect('doctor_dashboard')

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def create_announcement_section(request, section_id):
    if request.method == 'POST':
        section = get_object_or_404(SubjectSection, id=section_id, instructor=request.user)
        title = request.POST.get('title')
        content = request.POST.get('content')
        expires_at = request.POST.get('expires_at') or None

        if title and content:
            Announcement.objects.create(
                title=title,
                content=content,
                author=request.user,
                subject=section.subject,
                subject_section=section,
                expires_at=expires_at
            )
    return redirect('doctor_dashboard')

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def delete_announcement(request, announcement_id):
    if request.method == 'POST':
        announcement = get_object_or_404(Announcement, id=announcement_id)
        is_professor = announcement.subject.professor == request.user
        is_instructor = announcement.subject_section and announcement.subject_section.instructor == request.user
        
        if not (is_professor or is_instructor or announcement.author == request.user):
            raise PermissionDenied("You do not have permission to delete this announcement.")
            
        announcement.delete()
    return redirect('doctor_dashboard')

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def update_schedule(request, subject_id, section_id=None):
    if request.method == 'POST':
        day = request.POST.get('day')
        if day is not None:
            subject = get_object_or_404(Subject, id=subject_id)
            if section_id:
                section = get_object_or_404(SubjectSection, id=section_id, subject=subject, instructor=request.user)
                section.section_day = int(day)
                section.save()
                messages.success(request, f"Schedule updated for {subject.name} (Section {section.section_group}).")
            else:
                if subject.professor != request.user:
                    raise PermissionDenied("You do not have permission to update this subject's schedule.")
                subject.lecture_day = int(day)
                subject.save()
                messages.success(request, f"Schedule updated for {subject.name}.")
    return redirect('doctor_dashboard')








@user_passes_test(lambda u: u.is_superuser, login_url='/login/')
def import_students_csv(request):
    # إعدادات تقسيم السكاشن حسب الحروف الأبجدية
    # يمكنك تعديل هذه القائمة بسهولة لزيادة أو تقليل عدد السكاشن أو تغيير توزيع الحروف
    # كل مفتاح يمثل رقم السكشين، والقيمة هي قائمة الحروف التي ينتمي إليها الطالب في هذا السكشن
    ALPHA_SECTION_MAPPING = {
        1: ['أ', 'إ', 'آ', 'ا', 'ب', 'ت', 'ث'],
        2: ['ج', 'ح', 'خ', 'د', 'ذ', 'ر', 'ز'],
        3: ['س', 'ش', 'ص', 'ض', 'ط', 'ظ', 'ع', 'غ'],
        4: ['ف', 'ق', 'ك', 'ل', 'م'],
        5: ['ن', 'ه', 'و', 'ي']
    }

    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            messages.error(request, 'Please upload a CSV file.')
            return redirect('import_students_csv')
            
        if not csv_file.name.endswith('.csv'):
            messages.error(request, 'File must be a CSV.')
            return redirect('import_students_csv')

        data_set = csv_file.read().decode('UTF-8-SIG')
        io_string = io.StringIO(data_set)
        
        reader = csv.DictReader(io_string, delimiter=',', quotechar='"')
        
        success_count = 0
        skip_count = 0
        failed_count = 0
        error_details = []
        
        academic_years_seen = set()
        
        for raw_row in reader:
            row = {k.strip().lower(): v.strip() for k, v in raw_row.items() if k is not None}
            
            try:
                name = row.get('first_name') or row.get('name') or row.get('student_name') or ''
                last_name = row.get('last_name') or ''
                email = row.get('email') or ''
                academic_year_raw = row.get('academic_year') or row.get('year') or row.get('level') or ''
                dob_raw = row.get('date_of_birth') or row.get('dob') or '2000-01-01'
                gender_raw = row.get('gender') or 'Male'
                
                if not name:
                    error_details.append(f"Row {reader.line_num}: Missing student name.")
                    failed_count += 1
                    continue
                
                # Transliterate name if English
                needs_review = False
                if bool(re.search(r'[a-zA-Z]', name + last_name)):
                    needs_review = True
                    mapping = {'th': 'ث', 'sh': 'ش', 'ch': 'ش', 'kh': 'خ', 'gh': 'غ', 'a': 'ا', 'b': 'ب', 'c': 'ك', 'd': 'د', 'e': 'ي', 'f': 'ف', 'g': 'ج', 'h': 'ه', 'i': 'ي', 'j': 'ج', 'k': 'ك', 'l': 'ل', 'm': 'م', 'n': 'ن', 'o': 'و', 'p': 'ب', 'q': 'ق', 'r': 'ر', 's': 'س', 't': 'ت', 'u': 'و', 'v': 'ف', 'w': 'و', 'x': 'كس', 'y': 'ي', 'z': 'ز'}
                    
                    def to_ar(text):
                        text = text.lower()
                        for eng, ar in sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True):
                            text = text.replace(eng, ar)
                        return text
                    
                    name = to_ar(name)
                    last_name = to_ar(last_name)
                    
                if not last_name and ' ' in name:
                    name_parts = name.split(maxsplit=1)
                    first_name = name_parts[0]
                    last_name = name_parts[1] if len(name_parts) > 1 else ''
                else:
                    first_name = name
                
                try:
                    academic_year = int(academic_year_raw)
                except ValueError:
                    academic_year = 1
                    
                academic_years_seen.add(academic_year)
                
                # Parse DOB
                try:
                    dob = datetime.datetime.strptime(dob_raw, "%Y-%m-%d").date()
                except ValueError:
                    try:
                        dob = datetime.datetime.strptime(dob_raw, "%m/%d/%Y").date()
                    except ValueError:
                        dob = datetime.date(2000, 1, 1)
                        
                gender = 'Male' if gender_raw.lower() in ['m', 'male', 'ذكر'] else 'Female'
                
                # Generate IDs
                century = "2" if dob.year < 2000 else "3"
                yy = str(dob.year)[-2:]
                mm = f"{dob.month:02d}"
                dd = f"{dob.day:02d}"
                gov = f"{random.randint(1, 35):02d}"
                rnd_digits = f"{random.randint(0, 999):03d}"
                g_digit = str(random.choice([1, 3, 5, 7, 9])) if gender == 'Male' else str(random.choice([2, 4, 6, 8]))
                parity = str(random.randint(1, 9))
                
                national_id = f"{century}{yy}{mm}{dd}{gov}{rnd_digits}{g_digit}{parity}"
                
                # Generate Student Code (unique)
                while True:
                    student_code = str(random.randint(1000000000, 9999999999))
                    if not User.objects.filter(university_id=student_code).exists():
                        break
                        
                if User.objects.filter(username=national_id).exists():
                    skip_count += 1
                    continue
                
                user = User(
                    username=national_id,
                    university_id=student_code,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    role=User.Role.STUDENT,
                    academic_year=academic_year,
                    date_of_birth=dob,
                    gender=gender,
                    needs_review=needs_review
                )
                user.set_password(national_id)
                user.save()
                success_count += 1
            except Exception as e:
                error_details.append(f"Row {reader.line_num} ({raw_row.get('national_id', 'Unknown')}): {str(e)}")
                failed_count += 1
                
        # Post-Import Alphabetical Distribution
        for year in academic_years_seen:
            # Fetch all students for this year
            students = User.objects.filter(role=User.Role.STUDENT, academic_year=year)
            
            updated_students = []
            for student in students:
                first_letter = student.first_name.strip()[0] if student.first_name else 'أ'
                assigned_section = 1 # Fallback
                
                # Check mapping for correct section bucket
                for section_num, letters in ALPHA_SECTION_MAPPING.items():
                    if first_letter in letters:
                        assigned_section = section_num
                        break
                
                student.section_group = assigned_section
                updated_students.append(student)
                
            # Perform bulk update for efficiency
            if updated_students:
                User.objects.bulk_update(updated_students, ['section_group'])
        alert_description = f"**Action By:** {request.user.username}\n**Results:**\n✅ Successfully Imported: {success_count}\n⏭️ Skipped (Already Exists): {skip_count}\n❌ Failed: {failed_count}\n*Students have been distributed alphabetically to sections automatically.*"
        
        if error_details:
            errors_str = "\n".join([f"• {err}" for err in error_details[:10]])
            if len(error_details) > 10:
                errors_str += f"\n*...and {len(error_details) - 10} more errors.*"
            alert_description += f"\n\n**⚠️ Failure Reasons:**\n{errors_str}"

        send_activity_alert(
            title="📊 Student CSV Import Completed",
            description=alert_description,
            color=5763719
        )
        messages.success(request, f'Finished! Imported {success_count} students. Skipped {skip_count}. Failed {failed_count}. Students distributed alphabetically.')
        return redirect('import_students_csv')
        
    return render(request, 'import_students.html')

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def upload_official_book(request, subject_id):
    if request.method == 'POST':
        subject = get_object_or_404(Subject, id=subject_id, professor=request.user)
        uploaded_file = request.FILES.get('official_book')
        
        if uploaded_file:
            if subject.official_book:
                subject.official_book.delete(save=False)
            subject.official_book = uploaded_file
            subject.save()
            messages.success(request, 'Official course book uploaded successfully.')
    return HttpResponseRedirect(request.META.get('HTTP_REFERER', f'/subject/{subject_id}/'))


@login_required(login_url='/login/')
def subject_detail(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)
    
    # Check permissions
    if request.user.role == User.Role.STUDENT:
        if not request.user.registered_subjects.filter(id=subject.id).exists():
            raise PermissionDenied("You are not enrolled in this subject.")
    elif request.user.role == User.Role.DOCTOR:
        is_professor = (subject.professor == request.user)
        is_ta = subject.subject_sections.filter(instructor=request.user).exists()
        if not is_professor and not is_ta:
            raise PermissionDenied("You are not the professor or TA for this subject.")
            
    # Fetch related data
    lecture_materials = subject.materials.filter(subject_section__isnull=True).order_by('-created_at')
    
    if request.user.role == User.Role.STUDENT and request.user.section_group:
        section_materials = subject.materials.filter(subject_section__section_group=request.user.section_group).order_by('-created_at')
    else:
        section_materials = subject.materials.none()
        
    assignments = subject.assignments.filter(subject_section__isnull=True).order_by('-created_at')
    
    now = timezone.now()
    announcements = subject.announcements.filter(
        subject_section__isnull=True, 
        is_active=True
    ).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    ).order_by('-created_at')
    
    # Pre-fetch user submissions if student
    if request.user.role == User.Role.STUDENT:
        user_submissions = {sub.assignment_id: sub for sub in request.user.submissions.filter(assignment__in=assignments)}
        for assignment in assignments:
            assignment.user_submission = user_submissions.get(assignment.id)

    is_ta = False
    if request.user.role == User.Role.DOCTOR:
        is_ta = subject.subject_sections.filter(instructor=request.user).exists()

    # --- Exam Visibility Logic ---
    visible_exams = subject.exams.none()
    
    if request.user == subject.professor:
        visible_exams = subject.exams.all()
    elif request.user.role == User.Role.DOCTOR:
        visible_exams = subject.exams.filter(Q(exam_type='LECTURE') | Q(creator=request.user))
    elif request.user.role == User.Role.STUDENT:
        student_section = subject.subject_sections.filter(section_group=request.user.section_group).first()
        if student_section:
            visible_exams = subject.exams.filter(Q(exam_type='LECTURE') | Q(subject_section=student_section))
        else:
            visible_exams = subject.exams.filter(exam_type='LECTURE')

    context = {
        'subject': subject,
        'lecture_materials': lecture_materials,
        'section_materials': section_materials,
        'total_materials_count': lecture_materials.count() + section_materials.count(),
        'assignments': assignments,
        'announcements': announcements,
        'is_ta': is_ta,
        'visible_exams': visible_exams,
    }
    return render(request, 'subject_detail.html', context)

@login_required(login_url='/login/')
def section_detail(request, section_id):
    section = get_object_or_404(SubjectSection, id=section_id)
    subject = section.subject
    
    # Check permissions
    if request.user.role == User.Role.STUDENT:
        if not request.user.registered_subjects.filter(id=subject.id).exists() or section.section_group != request.user.section_group:
            raise PermissionDenied("You are not enrolled in this section.")
    elif request.user.role == User.Role.DOCTOR:
        if section.instructor != request.user:
            raise PermissionDenied("You are not the instructor for this section.")
            
    # Fetch related data
    materials = section.materials.order_by('-created_at')
    assignments = section.assignments.order_by('-created_at')
    
    now = timezone.now()
    announcements = Announcement.objects.filter(
        Q(subject=section.subject, subject_section__isnull=True) | Q(subject_section=section),
        is_active=True
    ).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    ).order_by('-created_at')
    
    # Pre-fetch user submissions if student
    if request.user.role == User.Role.STUDENT:
        user_submissions = {sub.assignment_id: sub for sub in request.user.submissions.filter(assignment__in=assignments)}
        for assignment in assignments:
            assignment.user_submission = user_submissions.get(assignment.id)
            
    context = {
        'section': section,
        'subject': subject,
        'materials': materials,
        'assignments': assignments,
        'announcements': announcements,
    }
    return render(request, 'section_detail.html', context)

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def subject_roster(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)
    
    # Restrict access
    if subject.professor != request.user:
        messages.error(request, "غير مصرح لك بعرض بيانات هذه المادة")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/doctor/dashboard/'))
        
    # --- Advanced Roster Analytics ---
    # 1. Assignment Subqueries
    assign_sum = Submission.objects.filter(
        student=OuterRef('pk'), assignment__subject=subject
    ).values('student').annotate(total=Sum('grade')).values('total')
    
    assign_count = Submission.objects.filter(
        student=OuterRef('pk'), assignment__subject=subject
    ).values('student').annotate(c=Count('id')).values('c')

    # 2. Exam Subqueries
    exam_sum = ExamAttempt.objects.filter(
        student=OuterRef('pk'), exam__subject=subject, exam__exam_type='LECTURE', is_submitted=True
    ).values('student').annotate(total=Sum('score')).values('total')
    
    exam_count = ExamAttempt.objects.filter(
        student=OuterRef('pk'), exam__subject=subject, exam__exam_type='LECTURE', is_submitted=True
    ).values('student').annotate(c=Count('id')).values('c')

    # 3. Master Annotation
    students = list(subject.students.annotate(
        submission_count=Coalesce(Subquery(assign_count, output_field=IntegerField()), 0),
        assignment_grade=Coalesce(Subquery(assign_sum, output_field=IntegerField()), 0),
        exam_attempt_count=Coalesce(Subquery(exam_count, output_field=IntegerField()), 0),
        exam_grade=Coalesce(Subquery(exam_sum, output_field=IntegerField()), 0),
    ).annotate(
        total_grade=F('assignment_grade') + F('exam_grade')
    ).order_by('username').prefetch_related(
        Prefetch('exam_attempts', queryset=ExamAttempt.objects.filter(exam__subject=subject, exam__exam_type='LECTURE', is_submitted=True), to_attr='subject_exam_attempts')
    ))
    
    exams = Exam.objects.filter(subject=subject, exam_type='LECTURE').order_by('created_at')
    
    for student in students:
        attempt_dict = {attempt.exam_id: attempt.score for attempt in student.subject_exam_attempts}
        student.ordered_exam_scores = [attempt_dict.get(exam.id, None) for exam in exams]
    
    return render(request, 'subject_roster.html', {
        'subject': subject,
        'students': students,
        'exams': exams
    })

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def section_roster(request, section_id):
    section = get_object_or_404(SubjectSection, id=section_id)
    
    # Restrict access
    if section.instructor != request.user and section.subject.professor != request.user:
        messages.error(request, "غير مصرح لك بعرض بيانات هذا السكشن")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/doctor/dashboard/'))
        
    # --- Advanced Roster Analytics ---
    # 1. Assignment Subqueries (Only section assignments)
    assign_sum = Submission.objects.filter(
        student=OuterRef('pk'), assignment__subject_section=section
    ).values('student').annotate(total=Sum('grade')).values('total')
    
    assign_count = Submission.objects.filter(
        student=OuterRef('pk'), assignment__subject_section=section
    ).values('student').annotate(c=Count('id')).values('c')

    # 2. Exam Subqueries (Only section exams)
    exam_sum = ExamAttempt.objects.filter(
        student=OuterRef('pk'), exam__subject_section=section, exam__exam_type='SECTION', is_submitted=True
    ).values('student').annotate(total=Sum('score')).values('total')
    
    exam_count = ExamAttempt.objects.filter(
        student=OuterRef('pk'), exam__subject_section=section, exam__exam_type='SECTION', is_submitted=True
    ).values('student').annotate(c=Count('id')).values('c')

    # 3. Master Annotation
    students = list(section.students.annotate(
        submission_count=Coalesce(Subquery(assign_count, output_field=IntegerField()), 0),
        assignment_grade=Coalesce(Subquery(assign_sum, output_field=IntegerField()), 0),
        exam_attempt_count=Coalesce(Subquery(exam_count, output_field=IntegerField()), 0),
        exam_grade=Coalesce(Subquery(exam_sum, output_field=IntegerField()), 0),
    ).annotate(
        total_grade=F('assignment_grade') + F('exam_grade')
    ).order_by('username').prefetch_related(
        Prefetch('exam_attempts', queryset=ExamAttempt.objects.filter(
            exam__subject_section=section,
            exam__exam_type='SECTION',
            is_submitted=True
        ), to_attr='section_exam_attempts')
    ))

    exams = Exam.objects.filter(subject=section.subject, subject_section=section, exam_type='SECTION').order_by('created_at')

    for student in students:
        attempt_dict = {attempt.exam_id: attempt.score for attempt in student.section_exam_attempts}
        student.ordered_exam_scores = [attempt_dict.get(exam.id, None) for exam in exams]
    
    return render(request, 'section_roster.html', {
        'section': section,
        'students': students,
        'exams': exams
    })

@login_required(login_url='/login/')
def register_admin_device(request):
    if not request.user.is_superuser:
        return HttpResponse("Unauthorized", status=401)
        
    from lms_app.models import AdminDevice
    device = AdminDevice.objects.create(user=request.user, device_name=request.META.get('HTTP_USER_AGENT', '')[:100])
    
    response = HttpResponse("تم تسجيل هذا الجهاز بنجاح كجهاز موثوق. يمكنك الآن الدخول للوحة التحكم بأمان.")
    response.set_cookie(
        'admin_trusted_device', 
        str(device.device_token), 
        max_age=10 * 365 * 24 * 60 * 60, # 10 years
        httponly=True, 
        secure=True, 
        samesite='Strict'
    )
    return response

from django.contrib.admin.views.decorators import staff_member_required


@staff_member_required
def bulk_academic_assignment(request):
    if request.method == 'POST':
        assignment_type = request.POST.get('assignment_type')
        target_id = request.POST.get('target_id')
        subject_id = request.POST.get('subject_id')
        
        try:
            subject = Subject.objects.get(id=subject_id)
            target_val = int(target_id)
            
            if assignment_type == 'year':
                students = User.objects.filter(role=User.Role.STUDENT, academic_year=target_val)
                target_label = f"Academic Year {target_val}"
            elif assignment_type == 'section':
                students = User.objects.filter(role=User.Role.STUDENT, section_group=target_val, academic_year=subject.academic_year)
                target_label = f"Section {target_val} (Year {subject.academic_year})"
            else:
                messages.error(request, "Invalid assignment type.")
                return redirect('bulk_academic_assignment')
                
            count = students.count()
            if count == 0:
                messages.warning(request, f"No students found for {target_label}.")
            else:
                subject.enrolled_students.add(*list(students))
                messages.success(request, f"Successfully enrolled {count} students from {target_label} into {subject.name} ({subject.code}).")
                
        except Subject.DoesNotExist:
            messages.error(request, "Selected subject does not exist.")
        except ValueError:
            messages.error(request, "Target ID must be a valid number.")
        except Exception as e:
            messages.error(request, f"Error occurred: {str(e)}")
            
        return redirect('bulk_academic_assignment')
        
    subjects = Subject.objects.all().order_by('academic_year', 'name')
    return render(request, 'admin/bulk_assignment.html', {'subjects': subjects})


@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def export_grades_csv(request, subject_id, section_id=None):
    subject = get_object_or_404(Subject, id=subject_id)
    
    if section_id:
        section = get_object_or_404(SubjectSection, id=section_id, subject=subject)
        if section.instructor != request.user and subject.professor != request.user:
            raise PermissionDenied("You do not have permission to export this section.")
        students = section.students.annotate(
            total_grade=Sum('submissions__grade', filter=Q(submissions__assignment__subject_section=section))
        ).order_by('username')
        filename = f"{subject.code}_section_{section.section_group}_grades.csv"
    else:
        if subject.professor != request.user:
            raise PermissionDenied("You do not have permission to export this subject.")
        students = subject.students.annotate(
            total_grade=Sum('submissions__grade', filter=Q(submissions__assignment__subject=subject))
        ).order_by('username')
        filename = f"{subject.code}_grades.csv"

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['Student Name', 'University ID', 'Section Group', 'Total Grade'])
    
    for student in students:
        name = f"{student.first_name} {student.last_name}".strip() or student.username
        writer.writerow([name, student.university_id or '', student.section_group or '', student.total_grade or 0])
        
    return response


@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def delete_official_book(request, subject_id):
    if request.method == 'POST':
        subject = get_object_or_404(Subject, id=subject_id)
        if subject.professor != request.user:
            raise PermissionDenied("You do not have permission to modify this subject.")
        
        if subject.official_book:
            subject.official_book.delete(save=False)
            subject.official_book = None
            subject.save()
            messages.success(request, "Official book deleted successfully.")
        
    return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/doctor/dashboard/'))

@login_required
@user_passes_test(is_doctor)
def update_subject_grade(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id, professor=request.user)
    if request.method == 'POST':
        max_grade = request.POST.get('max_grade')
        if max_grade and max_grade.isdigit():
            subject.max_total_grade = int(max_grade)
            subject.save()
            messages.success(request, 'تم تحديث الدرجة النهائية للمادة بنجاح.')
        else:
            messages.error(request, 'يرجى إدخال رقم صحيح.')
    # Redirect back to where they came from (could be subject_roster or section_roster)
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('subject_roster', subject_id=subject.id)

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def update_section_grade(request, section_id):
    section = get_object_or_404(SubjectSection, id=section_id)
    if section.instructor != request.user and section.subject.professor != request.user:
        raise PermissionDenied("ليس لديك الصلاحية لتحديث درجة هذا السكشن.")
        
    if request.method == 'POST':
        max_grade = request.POST.get('max_grade')
        if max_grade and max_grade.isdigit():
            section.max_total_grade = int(max_grade)
            section.save()
            messages.success(request, 'تم تحديث الدرجة النهائية للسكشن بنجاح.')
        else:
            messages.error(request, 'يرجى إدخال رقم صحيح.')
    
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('section_roster', section_id=section.id)

@login_required
def delete_notification(request, notification_id):
    from .models import Notification
    notification = get_object_or_404(Notification, id=notification_id, recipient=request.user)
    notification.delete()
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    if request.user.role == User.Role.STUDENT:
        return redirect('student_dashboard')
    return redirect('doctor_dashboard')

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def bulk_create_announcement(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        content = request.POST.get('content')
        targets = request.POST.getlist('targets')
        
        if not title or not content or not targets:
            messages.error(request, 'يرجى إدخال عنوان ومحتوى الإعلان واختيار جهة واحدة على الأقل.')
            return redirect('doctor_dashboard')

        for target in targets:
            if target.startswith('subject_'):
                subject_id = target.split('_')[1]
                subject = get_object_or_404(Subject, id=subject_id, professor=request.user)
                Announcement.objects.create(
                    title=title,
                    content=content,
                    author=request.user,
                    subject=subject
                )
            elif target.startswith('section_'):
                section_id = target.split('_')[1]
                section = get_object_or_404(SubjectSection, id=section_id, instructor=request.user)
                Announcement.objects.create(
                    title=title,
                    content=content,
                    author=request.user,
                    subject=section.subject,
                    subject_section=section
                )
        
        messages.success(request, 'تم إرسال الإعلان بنجاح إلى الجهات المحددة.')
        return redirect('doctor_dashboard')
    
    return redirect('doctor_dashboard')

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def create_exam(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)
    is_prof = (subject.professor == request.user)
    
    if request.method == 'POST':
        title = request.POST.get('title')
        section_id = request.POST.get('section_id')
        
        section_obj = None
        if section_id:
            # Explict section provided from frontend
            section_obj = get_object_or_404(SubjectSection, id=section_id, subject=subject)
            if not is_prof and section_obj.instructor != request.user:
                raise PermissionDenied('ليس لديك الصلاحية لإنشاء امتحان في هذا السكشن.')
        else:
            # Fallback
            if not is_prof:
                section_obj = subject.subject_sections.filter(instructor=request.user).first()
                if not section_obj:
                    raise PermissionDenied('ليس لديك الصلاحية لإنشاء امتحان في هذه المادة.')
        
        if title:
            exam_type = 'SECTION' if section_obj else 'LECTURE'
            new_exam = Exam.objects.create(
                subject=subject, 
                title=title, 
                duration_minutes=30, # Default duration
                is_active=False,
                exam_type=exam_type, 
                creator=request.user, 
                subject_section=section_obj
            )
            messages.success(request, 'تم إنشاء الامتحان مبدئياً. يرجى ضبط الإعدادات وإضافة الأسئلة.')
            return HttpResponseRedirect(f'/doctor/exam/{new_exam.id}/questions/')
            
    return HttpResponseRedirect(f'/subject/{subject.id}/')

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def toggle_exam_status(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    if exam.subject.professor != request.user and exam.creator != request.user:
        raise PermissionDenied("ليس لديك الصلاحية لتعديل هذا الامتحان.")
        
    if not exam.is_active and exam.questions.count() == 0:
        messages.error(request, "لا يمكن تفعيل امتحان لا يحتوي على أسئلة! يرجى إضافة أسئلة أولاً.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', f'/subject/{exam.subject.id}/'))
    exam.is_active = not exam.is_active
    exam.save()
    messages.success(request, f"تم {'تفعيل' if exam.is_active else 'إيقاف'} الامتحان بنجاح.")
    return HttpResponseRedirect(request.META.get('HTTP_REFERER', f'/subject/{exam.subject.id}/'))

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def delete_exam(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    if exam.subject.professor != request.user and exam.creator != request.user:
        raise PermissionDenied("ليس لديك الصلاحية لحذف هذا الامتحان.")
    if request.method == 'POST':
        exam.delete()
        messages.success(request, "تم حذف الامتحان بنجاح.")
    return HttpResponseRedirect(request.META.get('HTTP_REFERER', f'/subject/{exam.subject.id}/'))

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def manage_exam_questions(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    if exam.subject.professor != request.user and exam.creator != request.user:
        raise PermissionDenied("ليس لديك الصلاحية لإدارة أسئلة هذا الامتحان.")
    is_locked = ExamAttempt.objects.filter(exam=exam).exists()
    
    if request.method == 'POST':
        if is_locked:
            messages.error(request, 'لا يمكن التعديل. بدأ الطلاب في أداء الامتحان.')
            return HttpResponseRedirect(f'/doctor/exam/{exam.id}/questions/')
            
        action = request.POST.get('action')
        
        if action == 'update_settings':
            exam.title = request.POST.get('title', exam.title)
            exam.duration_minutes = int(request.POST.get('duration_minutes', exam.duration_minutes) or 0)
            exam.start_date = request.POST.get('start_date') or None
            exam.end_date = request.POST.get('end_date') or None
            exam.show_score = request.POST.get('show_score') == 'on'
            exam.show_answers = request.POST.get('show_answers') == 'on'
            exam.save()
            messages.success(request, 'تم تحديث إعدادات الامتحان بنجاح.')
            return HttpResponseRedirect(f'/doctor/exam/{exam.id}/questions/')
            
        elif action == 'add_question':
            question_text = request.POST.get('question_text')
            question_type = request.POST.get('question_type')
            marks = int(request.POST.get('marks', 1))
            
            if question_text:
                question = Question.objects.create(exam=exam, text=question_text, question_type=question_type, marks=marks)
                
                if question_type == 'MCQ':
                    for i in range(1, 5):
                        choice_text = request.POST.get(f'choice_{i}')
                        if choice_text:
                            is_correct = (request.POST.get('correct_choice') == str(i))
                            Choice.objects.create(question=question, text=choice_text, is_correct=is_correct)
                elif question_type == 'TF':
                    correct_tf = request.POST.get('correct_tf')
                    Choice.objects.create(question=question, text='صح', is_correct=(correct_tf == 'True'))
                    Choice.objects.create(question=question, text='خطأ', is_correct=(correct_tf == 'False'))
                
                messages.success(request, "تم إضافة السؤال بنجاح.")
                return HttpResponseRedirect(f'/doctor/exam/{exam.id}/questions/')
            
    return render(request, 'exam_manage_questions.html', {'exam': exam, 'is_locked': is_locked})


@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def delete_question(request, question_id):
    question = get_object_or_404(Question, id=question_id)
    exam_id = question.exam.id
    if question.exam.subject.professor != request.user and question.exam.creator != request.user:
        raise PermissionDenied("ليس لديك الصلاحية لحذف هذا السؤال.")
        
    is_locked = ExamAttempt.objects.filter(exam=question.exam).exists()
    if is_locked:
        messages.error(request, 'لا يمكن التعديل. بدأ الطلاب في أداء الامتحان.')
        return HttpResponseRedirect(f'/doctor/exam/{exam_id}/questions/')
        
    question.delete()
    messages.success(request, "تم حذف السؤال.")
    return HttpResponseRedirect(f'/doctor/exam/{exam_id}/questions/')

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def reset_exam_attempts(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    if exam.subject.professor != request.user and exam.creator != request.user:
        raise PermissionDenied("ليس لديك الصلاحية لمسح إجابات هذا الامتحان.")
        
    if request.method == 'POST':
        ExamAttempt.objects.filter(exam=exam).delete()
        messages.success(request, 'تم مسح جميع إجابات الطلاب وتصفير الدرجات. الامتحان الآن مفتوح للتعديل.')
        
    return HttpResponseRedirect(f'/doctor/exam/{exam.id}/questions/')

@login_required(login_url='/login/')
@user_passes_test(is_student, login_url='/login/')
def take_exam(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    
    # Security Check: Prevent taking empty exams
    if exam.questions.count() == 0:
        messages.error(request, "هذا الامتحان قيد التجهيز ولا يحتوي على أسئلة بعد.")
        return HttpResponseRedirect(f'/subject/{exam.subject.id}/')
    
    # Security Check: Prevent cross-section exam access
    if exam.exam_type == 'SECTION' and request.user.role == User.Role.STUDENT:
        if exam.subject_section.section_group != request.user.section_group:
            messages.error(request, "غير مصرح لك بدخول هذا الامتحان لأنه مخصص لسكشن آخر.")
            return HttpResponseRedirect(f'/subject/{exam.subject.id}/')
            
    now = timezone.now()
    if not exam.is_active:
        messages.error(request, "هذا الامتحان مغلق حالياً.")
        return HttpResponseRedirect(f'/subject/{exam.subject.id}/')
        
    if exam.start_date and now < exam.start_date:
        messages.error(request, "لم يبدأ موعد الامتحان بعد.")
        return HttpResponseRedirect(f'/subject/{exam.subject.id}/')
        
    if exam.end_date and now > exam.end_date:
        messages.error(request, "انتهى وقت هذا الامتحان.")
        return HttpResponseRedirect(f'/subject/{exam.subject.id}/')

    # 1. GET OR CREATE ATTEMPT (Starts the server-side clock)
    attempt, created = ExamAttempt.objects.get_or_create(student=request.user, exam=exam)
    
    if attempt.is_submitted:
        messages.warning(request, "لقد قمت بتسليم هذا الامتحان مسبقاً ولا يمكنك إعادته.")
        return HttpResponseRedirect(f'/subject/{exam.subject.id}/')
        
    # 2. CALCULATE SERVER-SIDE TIME EXPIRATION
    now = timezone.now()
    start_timestamp = getattr(attempt, 'start_time', None) or getattr(attempt, 'created_at', now)
        
    allowed_end_time = start_timestamp + timedelta(minutes=exam.duration_minutes)
    grace_period = timedelta(minutes=1) # 1 minute grace for network latency
    
    # Check if time is completely up (Security block)
    if now > (allowed_end_time + grace_period):
        attempt.is_submitted = True
        attempt.score = 0
        attempt.save()
        messages.error(request, "انتهى الوقت المسموح للامتحان. تم إغلاق المحاولة ولن يتم احتساب إجابات متأخرة.")
        return HttpResponseRedirect(f'/subject/{exam.subject.id}/')
        
    # 3. HANDLE GRADING (POST)
    if request.method == 'POST':
        score = 0
        total_marks = sum(q.marks for q in exam.questions.all())
        
        for question in exam.questions.all():
            selected_choice_id = request.POST.get(f'question_{question.id}')
            if selected_choice_id:
                try:
                    selected_choice = Choice.objects.get(id=selected_choice_id, question=question)
                    StudentAnswer.objects.update_or_create(
                        attempt=attempt, 
                        question=question, 
                        defaults={'selected_choice': selected_choice}
                    )
                    if selected_choice.is_correct:
                        score += question.marks
                except Choice.DoesNotExist:
                    pass

        attempt.score = score
        attempt.is_submitted = True
        attempt.save()
        
        if exam.show_score:
            messages.success(request, f"تم التسليم بنجاح! نتيجتك هي {score} من {total_marks}.")
        else:
            messages.success(request, "تم تسليم الامتحان بنجاح.")
            
        return HttpResponseRedirect(f'/subject/{exam.subject.id}/')

    # 4. PASS REMAINING TIME TO UI (GET)
    remaining_seconds = int((allowed_end_time - now).total_seconds())
    if remaining_seconds < 0:
        remaining_seconds = 0
        
    import random
    questions_list = list(exam.questions.all())
    rng = random.Random(attempt.id)
    rng.shuffle(questions_list)
    
    for q in questions_list:
        choices_list = list(q.choices.all())
        choice_rng = random.Random(attempt.id + q.id)
        choice_rng.shuffle(choices_list)
        q.shuffled_choices = choices_list
        
    saved_answers = {ans.question_id: ans.selected_choice_id for ans in attempt.answers.all()}
        
    return render(request, 'exam_room.html', {
        'exam': exam, 
        'remaining_seconds': remaining_seconds,
        'questions_list': questions_list,
        'saved_answers': saved_answers
    })

import json

from django.http import JsonResponse


@login_required(login_url='/login/')
@user_passes_test(is_student, login_url='/login/')
def save_exam_click(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            exam_id = data.get('exam_id')
            question_id = data.get('question_id')
            choice_id = data.get('choice_id')
            
            attempt = ExamAttempt.objects.filter(exam_id=exam_id, student=request.user, is_submitted=False).first()
            if attempt:
                StudentAnswer.objects.update_or_create(
                    attempt=attempt,
                    question_id=question_id,
                    defaults={'selected_choice_id': choice_id}
                )
                return JsonResponse({'status': 'saved'})
        except Exception as e:
            pass
    return JsonResponse({'status': 'failed'}, status=400)

@login_required(login_url='/login/')
@user_passes_test(is_student, login_url='/login/')
def review_exam(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    attempt = get_object_or_404(ExamAttempt, exam=exam, student=request.user)
    
    # Security Check
    if not attempt.is_submitted or not exam.show_answers:
        messages.error(request, "غير مصرح لك بمراجعة إجابات هذا الامتحان حالياً.")
        return HttpResponseRedirect(f'/subject/{exam.subject.id}/')
        
    return render(request, 'review_exam.html', {'exam': exam, 'attempt': attempt})

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def view_exam_results(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    if exam.subject.professor != request.user and exam.creator != request.user:
        raise PermissionDenied("ليس لديك الصلاحية لعرض نتائج هذا الامتحان.")
        
    attempts = ExamAttempt.objects.filter(exam=exam, is_submitted=True).order_by('-score')
    
    # Find Missing Students
    attempted_ids = attempts.values_list('student_id', flat=True)
    
    # Handle both Lecture and Section exam enrollment
    if getattr(exam, 'exam_type', 'LECTURE') == 'SECTION' and getattr(exam, 'subject_section', None):
        # Fallback to the ManyToMany field representing enrolled students in the section
        enrolled = User.objects.filter(role=User.Role.STUDENT, section_group=exam.subject_section.section_group, academic_year=exam.subject.academic_year)
    else:
        enrolled = exam.subject.students
        
    missing_students = enrolled.exclude(id__in=attempted_ids).order_by('first_name')
    
    return render(request, 'exam_results.html', {
        'exam': exam,
        'attempts': attempts,
        'missing_students': missing_students
    })

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def import_exam_questions(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    
    # Security: Only Professor or Creator
    if exam.subject.professor != request.user and exam.creator != request.user:
        messages.error(request, 'ليس لديك الصلاحية لتعديل هذا الامتحان.')
        return HttpResponseRedirect(f'/subject/{exam.subject.id}/')

    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        
        if not (csv_file.name.endswith('.csv') or csv_file.name.endswith('.xlsx')):
            messages.error(request, 'يرجى رفع ملف بصيغة CSV أو Excel (.xlsx) فقط.')
            return HttpResponseRedirect(f'/doctor/exam/{exam.id}/questions/')
            
        try:
            rows = []
            if csv_file.name.endswith('.csv'):
                decoded_file = csv_file.read().decode('utf-8-sig').splitlines()
                reader = csv.reader(decoded_file)
                next(reader, None) # Skip header
                rows = list(reader)
            elif csv_file.name.endswith('.xlsx'):
                wb = openpyxl.load_workbook(csv_file)
                sheet = wb.active
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    if row[0]: # If question text exists
                        # Convert all cells to string, handling None
                        rows.append([str(cell).strip() if cell is not None else "" for cell in row])

            imported_count = 0
            for row in rows:
                # Expected format: [Question Text, Type(MCQ/TF), Marks, Choice1, Choice2, Choice3, Choice4, Correct_Index]
                if len(row) < 3: continue 
                
                q_text = row[0].strip()
                q_type = row[1].strip().upper()
                marks = int(float(row[2]) if row[2] else 1) # Handled float in case excel stores as 1.0
                
                if not q_text: continue
                
                question = Question.objects.create(exam=exam, text=q_text, question_type='MCQ' if q_type == 'MCQ' else 'TF', marks=marks)
                
                if question.question_type == 'MCQ' and len(row) >= 8:
                    choices = [row[3], row[4], row[5], row[6]]
                    correct_index = str(row[7]).replace('.0', '') # Clean Excel floats
                    
                    for i, c_text in enumerate(choices, start=1):
                        if c_text:
                            Choice.objects.create(question=question, text=c_text, is_correct=(str(i) == correct_index))
                            
                elif question.question_type == 'TF' and len(row) >= 4:
                    correct_tf = str(row[3]).upper().strip()
                    Choice.objects.create(question=question, text='صح', is_correct=(correct_tf == 'TRUE' or correct_tf == 'صح'))
                    Choice.objects.create(question=question, text='خطأ', is_correct=(correct_tf == 'FALSE' or correct_tf == 'خطأ'))
                    
                imported_count += 1
                
            messages.success(request, f'تم استيراد {imported_count} سؤال بنجاح!')
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء قراءة الملف: {str(e)}')
            
    return HttpResponseRedirect(f'/doctor/exam/{exam.id}/questions/')

@login_required(login_url='/login/')
def download_csv_template(request):
    # Generates an empty template for Doctors to fill out
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="exam_template.csv"'
    response.write('﻿'.encode('utf8')) # BOM for Arabic Excel
    writer = csv.writer(response)
    writer.writerow(['نص السؤال', 'نوع السؤال (MCQ أو TF)', 'الدرجة', 'الخيار الأول (MCQ)', 'الخيار الثاني (MCQ)', 'الخيار الثالث (MCQ)', 'الخيار الرابع (MCQ)', 'رقم الإجابة الصحيحة (1/2/3/4) أو صح/خطأ'])
    writer.writerow(['ما هي عاصمة مصر؟', 'MCQ', '1', 'الإسكندرية', 'القاهرة', 'الجيزة', 'الأقصر', '2'])
    writer.writerow(['الشمس تدور حول الأرض', 'TF', '1', 'خطأ', '', '', '', ''])
    return response
