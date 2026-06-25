from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone
from datetime import timedelta
import random
import csv
import io
from .models import Subject, User, Material, SubjectSection, Assignment, Submission, Announcement, AttendanceSession, AttendanceRecord
from django.db.models import Q

def user_login(request):
    error_message = None
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                if user.role == User.Role.ADMIN:
                    return redirect('/admin/')
                elif user.role == User.Role.DOCTOR:
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
    logout(request)
    return redirect('login')

def is_doctor(user):
    # Only allow access if the user is authenticated and has the DOCTOR role
    return user.is_authenticated and user.role == User.Role.DOCTOR

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def doctor_dashboard(request):
    # Query subjects where the doctor is the main professor
    main_subjects = Subject.objects.filter(professor=request.user).prefetch_related('assignments', 'materials', 'attendance_sessions', 'subject_sections')
    
    # Query sections where the doctor is the specific instructor
    assigned_sections = SubjectSection.objects.filter(instructor=request.user).select_related('subject').prefetch_related('materials', 'assignments', 'section_attendance_sessions')
    
    # Query active PIN sessions for the doctor
    active_sessions = []
    now = timezone.now()
    possible_sessions = AttendanceSession.objects.filter(instructor=request.user).select_related('subject', 'subject_section')
    
    for session in possible_sessions:
        if session.pin_code and now <= session.created_at + timedelta(minutes=session.pin_duration_minutes):
            active_sessions.append({
                'session': session,
                'subject_id': session.subject_id,
                'section_id': session.subject_section.id if session.subject_section else None,
                'expires_at': session.created_at + timedelta(minutes=session.pin_duration_minutes)
            })

    context = {
        'main_subjects': main_subjects,
        'assigned_sections': assigned_sections,
        'active_sessions': active_sessions,
        'now': now,
        'DAYS_OF_WEEK': Subject.DAYS_OF_WEEK,
    }
    return render(request, 'doctor_dashboard.html', context)

def is_student(user):
    # Only allow access if the user is authenticated and has the STUDENT role
    return user.is_authenticated and user.role == User.Role.STUDENT

@login_required(login_url='/login/')
@user_passes_test(is_student, login_url='/login/')
def student_dashboard(request):
    # Query subjects based on student's academic year
    subjects = Subject.objects.filter(academic_year=request.user.academic_year).select_related('professor').prefetch_related('assignments', 'materials')
    
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

    attendance_records = AttendanceRecord.objects.filter(student=request.user).select_related('session', 'session__subject')
    
    for subject in subjects:
        subject_records = [r for r in attendance_records if r.session.subject_id == subject.id and (r.session.subject_section is None or r.session.subject_section.section_group == request.user.section_group)]
        subject.attendance_total = len(subject_records)
        subject.attendance_attended = sum(1 for r in subject_records if r.is_present)

    # Query active PIN sessions
    active_sessions = []
    now = timezone.now()
    possible_sessions = AttendanceSession.objects.filter(
        Q(subject_id__in=enrolled_subject_ids) &
        (Q(subject_section__isnull=True) | Q(subject_section__section_group=request.user.section_group))
    ).select_related('subject')
    
    for session in possible_sessions:
        if session.pin_code and now <= session.created_at + timedelta(minutes=session.pin_duration_minutes):
            # Check if student already submitted for this session
            if not session.records.filter(student=request.user, is_present=True).exists():
                active_sessions.append(session)

    context = {
        'subjects': subjects,
        'announcements': announcements,
        'announcements_count': announcements_count,
        'active_sessions': active_sessions,
        'now': now,
    }
    return render(request, 'student_dashboard.html', context)

@login_required
@user_passes_test(is_student, login_url='/login/')
def student_settings(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Important!
            messages.success(request, 'Your password was successfully updated!')
            return redirect('student_settings')
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'student_settings.html', {'form': form})

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
    return redirect('doctor_dashboard')

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
    return redirect('doctor_dashboard')

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
            material.file.delete(save=False) # Delete the file from storage
        material.delete() # Delete the object
        
    return redirect('doctor_dashboard')

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
        allowed_extensions = request.POST.get('allowed_extensions', 'pdf,zip,docx,rar')

        if title and due_date:
            Assignment.objects.create(
                subject=subject,
                title=title,
                description=description,
                due_date=due_date,
                max_grade=max_grade,
                requirements_text=requirements_text,
                max_file_size_mb=max_file_size_mb,
                allowed_extensions=allowed_extensions
            )
    return redirect('doctor_dashboard')

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
        allowed_extensions = request.POST.get('allowed_extensions', 'pdf,zip,docx,rar')

        if title and due_date:
            Assignment.objects.create(
                subject=section.subject,
                subject_section=section,
                title=title,
                description=description,
                due_date=due_date,
                max_grade=max_grade,
                requirements_text=requirements_text,
                max_file_size_mb=max_file_size_mb,
                allowed_extensions=allowed_extensions
            )
    return redirect('doctor_dashboard')

@login_required(login_url='/login/')
@user_passes_test(is_student, login_url='/login/')
def submit_assignment(request, assignment_id):
    if request.method == 'POST':
        assignment = get_object_or_404(Assignment, id=assignment_id)
        
        if timezone.now() > assignment.due_date:
            messages.error(request, "Deadline has passed. You cannot submit this assignment.")
            return redirect('student_dashboard')
            
        submitted_file = request.FILES.get('file')

        if submitted_file:
            import os
            ext = os.path.splitext(submitted_file.name)[1][1:].lower()
            allowed_exts = [e.strip().lower() for e in assignment.allowed_extensions.split(',')]
            if ext not in allowed_exts:
                messages.error(request, f"Invalid file format. Allowed formats: {assignment.allowed_extensions}")
                return redirect('student_dashboard')
            
            if submitted_file.size > assignment.max_file_size_mb * 1024 * 1024:
                messages.error(request, f"File size exceeds the maximum limit of {assignment.max_file_size_mb} MB.")
                return redirect('student_dashboard')

            Submission.objects.update_or_create(
                assignment=assignment,
                student=request.user,
                defaults={'submitted_file': submitted_file}
            )
            messages.success(request, "Assignment submitted successfully.")
    return redirect('student_dashboard')

@login_required(login_url='/login/')
@user_passes_test(is_student, login_url='/login/')
def unsubmit_assignment(request, submission_id):
    if request.method == 'POST':
        # Strictly enforce ownership by filtering by student=request.user
        submission = get_object_or_404(Submission, id=submission_id, student=request.user)
        
        if submission.grade is not None:
            messages.error(request, "You cannot unsubmit an assignment that has already been graded.")
        else:
            submission.submitted_file.delete()
            submission.delete()
            messages.success(request, "Your submission has been cancelled. You may re-upload a new file.")
            
    return redirect('student_dashboard')

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
            submission.grade = float(grade)
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

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def start_attendance_session(request, subject_id, section_id=None):
    if request.method == 'POST':
        subject = get_object_or_404(Subject, id=subject_id)
        section = None
        is_makeup = request.POST.get('is_makeup') == 'on'
        
        scheduled_day = None
        if section_id:
            section = get_object_or_404(SubjectSection, id=section_id, subject=subject, instructor=request.user)
            scheduled_day = section.section_day
        else:
            if subject.professor != request.user:
                raise PermissionDenied("You do not have permission to start a session for this subject.")
            scheduled_day = subject.lecture_day
            
        today_weekday = timezone.now().weekday()
        
        if scheduled_day is not None and scheduled_day != today_weekday and not is_makeup:
            messages.error(request, "Cannot start attendance outside the scheduled day. Please check 'Makeup Class' or update the official schedule.")
            return redirect('doctor_dashboard')
        
        pin_code = str(random.randint(1000, 9999))
        duration = int(request.POST.get('duration_minutes', 5))
        session = AttendanceSession.objects.create(
            subject=subject,
            subject_section=section,
            instructor=request.user,
            pin_code=pin_code,
            pin_duration_minutes=duration,
            is_makeup_class=is_makeup
        )
        messages.success(request, f"Attendance session started! Active PIN: {pin_code}")
    return redirect('doctor_dashboard')

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def end_attendance_session(request, session_id):
    if request.method == 'POST':
        session = get_object_or_404(AttendanceSession, id=session_id)
        if session.instructor != request.user:
            raise PermissionDenied("You do not have permission to end this session.")
            
        session.pin_duration_minutes = 0
        session.save()
        messages.success(request, "Attendance session ended successfully.")
    return redirect('doctor_dashboard')

@login_required(login_url='/login/')
@user_passes_test(is_student, login_url='/login/')
def submit_attendance_pin(request, session_id):
    if request.method == 'POST':
        session = get_object_or_404(AttendanceSession, id=session_id)
        entered_pin = request.POST.get('pin_code')
        
        now = timezone.now()
        if session.pin_code and now <= session.created_at + timedelta(minutes=session.pin_duration_minutes):
            if entered_pin == session.pin_code:
                AttendanceRecord.objects.update_or_create(
                    session=session,
                    student=request.user,
                    defaults={'is_present': True}
                )
                messages.success(request, f"Attendance marked successfully for {session.subject.name}!")
            else:
                messages.error(request, "Invalid PIN code. Please try again.")
        else:
            messages.error(request, "This attendance session has expired or is invalid.")
        return redirect('student_dashboard')

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def edit_attendance(request, session_id):
    session = get_object_or_404(AttendanceSession, id=session_id, instructor=request.user)
    
    # Query all students supposed to be in this session
    if session.subject_section:
        students = User.objects.filter(role=User.Role.STUDENT, academic_year=session.subject.academic_year, section_group=session.subject_section.section_group)
    else:
        students = User.objects.filter(role=User.Role.STUDENT, academic_year=session.subject.academic_year)
        
    # Get existing records
    records = {record.student_id: record.is_present for record in session.records.all()}
    
    # Attach present status to student objects for template
    for student in students:
        student.is_present = records.get(student.id, False)
        
    if request.method == 'POST':
        present_student_ids = request.POST.getlist('present_students')
        
        records_to_create = []
        for student in students:
            is_present = str(student.id) in present_student_ids
            # Instead of bulk create which might fail on unique constraints, use update_or_create
            AttendanceRecord.objects.update_or_create(
                session=session,
                student=student,
                defaults={'is_present': is_present}
            )
            
        return redirect('doctor_dashboard')

    context = {
        'session': session,
        'students': students,
    }
    return render(request, 'edit_attendance.html', context)

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def export_attendance_csv(request, subject_id, section_id=None):
    subject = get_object_or_404(Subject, id=subject_id)
    section = None
    
    if section_id:
        section = get_object_or_404(SubjectSection, id=section_id, subject=subject, instructor=request.user)
    else:
        if subject.professor != request.user:
            raise PermissionDenied("You do not have permission to export attendance for this subject.")
            
    students = User.objects.filter(role=User.Role.STUDENT, academic_year=subject.academic_year)
    sessions = AttendanceSession.objects.filter(subject=subject)
    
    filename = f"{subject.code}_attendance.csv"
    
    if section_id:
        students = students.filter(section_group=section.section_group)
        sessions = sessions.filter(subject_section=section).order_by('created_at')
        filename = f"{subject.code}_section_{section.section_group}_attendance.csv"
    else:
        sessions = sessions.filter(subject_section__isnull=True).order_by('created_at')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['Name', 'National ID', 'Attended', 'Conducted', 'Percentage (%)'])
    
    total_sessions = sessions.count()
    
    for student in students:
        attended = AttendanceRecord.objects.filter(student=student, session__in=sessions, is_present=True).count()
        percentage = round((attended / total_sessions * 100) if total_sessions > 0 else 0, 1)
        
        name = f"{student.first_name} {student.last_name}".strip() or student.username
        writer.writerow([name, student.university_id, attended, total_sessions, percentage])
        
    return response

@user_passes_test(lambda u: u.is_superuser, login_url='/login/')
def import_students_csv(request):
    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            messages.error(request, 'Please upload a CSV file.')
            return redirect('import_students_csv')
            
        if not csv_file.name.endswith('.csv'):
            messages.error(request, 'File must be a CSV.')
            return redirect('import_students_csv')

        def get_section(name):
            if not name:
                return None
            first_letter = name.strip()[0]
            if first_letter in ['أ', 'إ', 'آ', 'ا', 'ب', 'ت', 'ث']:
                return 1
            elif first_letter in ['ج', 'ح', 'خ', 'د', 'ذ', 'ر', 'ز']:
                return 2
            elif first_letter in ['س', 'ش', 'ص', 'ض', 'ط', 'ظ', 'ع', 'غ']:
                return 3
            elif first_letter in ['ف', 'ق', 'ك', 'ل', 'م']:
                return 4
            elif first_letter in ['ن', 'ه', 'و', 'ي']:
                return 5
            return None

        data_set = csv_file.read().decode('UTF-8')
        io_string = io.StringIO(data_set)
        
        reader = csv.DictReader(io_string, delimiter=',', quotechar='"')
        
        success_count = 0
        skip_count = 0
        failed_count = 0
        
        for raw_row in reader:
            # 1. Normalize Headers
            row = {k.strip().lower(): v.strip() for k, v in raw_row.items() if k is not None}
            
            try:
                # 2. Flexible Fallback Keys
                national_id = row.get('national_id') or row.get('id') or row.get('ssn') or row.get('username')
                name = row.get('first_name') or row.get('firstname') or row.get('name') or row.get('student_name')
                last_name = row.get('last_name') or row.get('lastname') or ''
                email = row.get('email') or row.get('email_address') or ''
                academic_year_raw = row.get('academic_year') or row.get('year') or row.get('level') or ''
                
                if not name or not national_id:
                    failed_count += 1
                    continue
                
                # If they only provided 'name', split it. If they provided first_name and last_name, use them.
                if not last_name and ' ' in name:
                    name_parts = name.split(maxsplit=1)
                    first_name = name_parts[0]
                    last_name = name_parts[1]
                else:
                    first_name = name
                
                try:
                    academic_year = int(academic_year_raw)
                except ValueError:
                    academic_year = 1
                
                if User.objects.filter(username=national_id).exists():
                    skip_count += 1
                    continue
                
                section = get_section(first_name)
                
                user = User(
                    username=national_id,
                    university_id=national_id,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    role=User.Role.STUDENT,
                    academic_year=academic_year,
                    section_group=section
                )
                user.set_password(national_id)
                user.save()
                success_count += 1
            except Exception as e:
                failed_count += 1
                
        messages.success(request, f'Finished! Imported {success_count} students. Skipped {skip_count} existing. Failed {failed_count} rows.')
        return redirect('import_students_csv')
        
    return render(request, 'import_students.html')

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def upload_official_book(request, subject_id):
    if request.method == 'POST':
        subject = get_object_or_404(Subject, id=subject_id, professor=request.user)
        uploaded_file = request.FILES.get('official_book')
        
        if uploaded_file:
            subject.official_book = uploaded_file
            subject.save()
            messages.success(request, 'Official course book uploaded successfully.')
    return redirect('doctor_dashboard')

@login_required(login_url='/login/')
@user_passes_test(is_doctor, login_url='/login/')
def attendance_report_detail(request, session_id):
    session = get_object_or_404(AttendanceSession, id=session_id)
    
    is_professor = session.subject.professor == request.user
    is_instructor = session.subject_section and session.subject_section.instructor == request.user
    if not (is_professor or is_instructor or session.instructor == request.user):
        raise PermissionDenied("You do not have permission to view this report.")

    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    students_query = User.objects.filter(role='STUDENT', academic_year=session.subject.academic_year)
    if session.subject_section:
        students_query = students_query.filter(section_group=session.subject_section.section_group)
    
    expected_students = students_query.order_by('first_name', 'last_name')
    present_records = set(AttendanceRecord.objects.filter(session=session, is_present=True).values_list('student_id', flat=True))
    
    roster = []
    present_count = 0
    for student in expected_students:
        is_present = student.id in present_records
        if is_present:
            present_count += 1
        roster.append({
            'student': student,
            'is_present': is_present
        })
    
    total_students = expected_students.count()
    absent_count = total_students - present_count
    attendance_rate = (present_count / total_students * 100) if total_students > 0 else 0

    context = {
        'session': session,
        'roster': roster,
        'total_students': total_students,
        'present_count': present_count,
        'absent_count': absent_count,
        'attendance_rate': round(attendance_rate, 1)
    }
    return render(request, 'attendance_report_detail.html', context)
