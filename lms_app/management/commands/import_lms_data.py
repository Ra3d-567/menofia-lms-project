import csv
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from lms_app.models import User, Subject, Enrollment

class Command(BaseCommand):
    help = 'Bulk import Users, Subjects, and Enrollments from CSV files.'

    def add_arguments(self, parser):
        parser.add_argument('--users', type=str, help='Path to users CSV file')
        parser.add_argument('--subjects', type=str, help='Path to subjects CSV file')
        parser.add_argument('--enrollments', type=str, help='Path to enrollments CSV file')

    def handle(self, *args, **kwargs):
        users_file = kwargs['users']
        subjects_file = kwargs['subjects']
        enrollments_file = kwargs['enrollments']

        if not any([users_file, subjects_file, enrollments_file]):
            self.stdout.write(self.style.WARNING("Please provide at least one CSV file path (--users, --subjects, or --enrollments)."))
            return

        if users_file:
            self.import_users(users_file)
        
        if subjects_file:
            self.import_subjects(subjects_file)

        if enrollments_file:
            self.import_enrollments(enrollments_file)

    def import_users(self, filepath):
        self.stdout.write(self.style.NOTICE(f'Importing users from {filepath}...'))
        
        # Expected CSV columns: username, email, password, first_name, last_name, role, university_id, department, academic_year
        with open(filepath, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            created_count = 0
            updated_count = 0
            
            for row in reader:
                username = row.get('username')
                if not username:
                    continue
                
                # Extract and normalize fields
                role = row.get('role', 'STUDENT').upper()
                academic_year = row.get('academic_year', '').upper().strip() or None
                
                # Only STUDENTS have an academic_year, validate and map it
                if role != User.Role.STUDENT:
                    academic_year = None
                else:
                    if academic_year:
                        # Map common CSV values to our model choices
                        if 'FIRST' in academic_year or '1' in academic_year:
                            academic_year = User.AcademicYear.FIRST_YEAR
                        elif 'SECOND' in academic_year or '2' in academic_year:
                            academic_year = User.AcademicYear.SECOND_YEAR
                        elif 'THIRD' in academic_year or '3' in academic_year:
                            academic_year = User.AcademicYear.THIRD_YEAR
                        elif 'FOURTH' in academic_year or '4' in academic_year:
                            academic_year = User.AcademicYear.FOURTH_YEAR
                        else:
                            academic_year = None

                user, created = User.objects.update_or_create(
                    username=username,
                    defaults={
                        'email': row.get('email', ''),
                        'first_name': row.get('first_name', ''),
                        'last_name': row.get('last_name', ''),
                        'role': role,
                        'university_id': row.get('university_id', ''),
                        'department': row.get('department', ''),
                        'academic_year': academic_year,
                    }
                )
                
                # Set password if provided
                raw_password = row.get('password')
                if raw_password:
                    user.set_password(raw_password)
                    user.save()
                    
                if created:
                    created_count += 1
                else:
                    updated_count += 1

            self.stdout.write(self.style.SUCCESS(f'Successfully imported {created_count} new users (updated {updated_count}).'))

    def import_subjects(self, filepath):
        self.stdout.write(self.style.NOTICE(f'Importing subjects from {filepath}...'))
        
        # Expected CSV columns: code, name, description, professor_username
        with open(filepath, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            created_count = 0
            updated_count = 0
            
            for row in reader:
                code = row.get('code')
                if not code:
                    continue
                
                professor = None
                prof_username = row.get('professor_username')
                if prof_username:
                    try:
                        professor = User.objects.get(username=prof_username, role=User.Role.DOCTOR)
                    except User.DoesNotExist:
                        self.stdout.write(self.style.WARNING(f"Professor '{prof_username}' not found or not a doctor. Subject '{code}' will have no professor assigned."))

                subject, created = Subject.objects.update_or_create(
                    code=code,
                    defaults={
                        'name': row.get('name', ''),
                        'description': row.get('description', ''),
                        'professor': professor
                    }
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1
                    
            self.stdout.write(self.style.SUCCESS(f'Successfully imported {created_count} new subjects (updated {updated_count}).'))

    def import_enrollments(self, filepath):
        self.stdout.write(self.style.NOTICE(f'Importing enrollments from {filepath}...'))
        
        # Expected CSV columns: student_username, subject_code
        with open(filepath, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            created_count = 0
            
            for row in reader:
                student_username = row.get('student_username')
                subject_code = row.get('subject_code')
                
                if not student_username or not subject_code:
                    continue
                
                try:
                    student = User.objects.get(username=student_username, role=User.Role.STUDENT)
                    subject = Subject.objects.get(code=subject_code)
                    
                    enrollment, created = Enrollment.objects.get_or_create(
                        student=student,
                        subject=subject
                    )
                    if created:
                        created_count += 1
                except User.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"Student '{student_username}' not found. Skipping enrollment."))
                except Subject.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"Subject '{subject_code}' not found. Skipping enrollment."))

            self.stdout.write(self.style.SUCCESS(f'Successfully imported {created_count} new enrollments.'))
