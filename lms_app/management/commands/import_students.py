import csv
import random
from django.core.management.base import BaseCommand
from lms_app.models import User

def get_section(name):
    if not name:
        return 5
    first_char = name.strip()[0]
    
    group_1 = ['أ', 'إ', 'آ', 'ا', 'ب', 'ت', 'ث']
    group_2 = ['ج', 'ح', 'خ', 'د', 'ذ', 'ر', 'ز']
    group_3 = ['س', 'ش', 'ص', 'ض', 'ط', 'ظ']
    group_4 = ['ع', 'غ', 'ف', 'ق', 'ك', 'ل']
    
    if first_char in group_1:
        return 1
    elif first_char in group_2:
        return 2
    elif first_char in group_3:
        return 3
    elif first_char in group_4:
        return 4
    else:
        return 5

class Command(BaseCommand):
    help = 'Import students from a specialized CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the students CSV file')

    def handle(self, *args, **kwargs):
        csv_file = kwargs['csv_file']

        self.stdout.write(self.style.NOTICE(f'Importing students from {csv_file}...'))

        try:
            with open(csv_file, mode='r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                created_count = 0
                updated_count = 0
                failed_count = 0

                for raw_row in reader:
                    # 1. Normalize Headers
                    row = {k.strip().lower(): v.strip() for k, v in raw_row.items() if k is not None}
                    
                    try:
                        # 2. Flexible Fallback Keys
                        national_id = row.get('national_id') or row.get('id') or row.get('ssn') or row.get('username')
                        name = row.get('first_name') or row.get('firstname') or row.get('name') or row.get('student_name')
                        last_name = row.get('last_name') or row.get('lastname') or ''
                        academic_year_raw = row.get('academic_year') or row.get('year') or row.get('level') or ''
                        email = row.get('email') or row.get('email_address') or ''

                        if not name or not national_id:
                            self.stdout.write(self.style.WARNING(f"Skipping row missing Name or National_ID: {raw_row}"))
                            failed_count += 1
                            continue

                        # If they only provided 'name', split it. If they provided first_name and last_name, use them.
                        if not last_name and ' ' in name:
                            name_parts = name.split(maxsplit=1)
                            first_name = name_parts[0]
                            last_name = name_parts[1]
                        else:
                            first_name = name

                    # Determine Section Group
                    section_group = get_section(name)

                    # Map Academic Year safely
                    academic_year = None
                    if 'FIRST' in academic_year_raw or '1' in academic_year_raw:
                        academic_year = User.AcademicYear.FIRST_YEAR
                    elif 'SECOND' in academic_year_raw or '2' in academic_year_raw:
                        academic_year = User.AcademicYear.SECOND_YEAR
                    elif 'THIRD' in academic_year_raw or '3' in academic_year_raw:
                        academic_year = User.AcademicYear.THIRD_YEAR
                    elif 'FOURTH' in academic_year_raw or '4' in academic_year_raw:
                        academic_year = User.AcademicYear.FOURTH_YEAR

                    # Generate Academic Code (university_id)
                    # 'STU-' + last 4 of National ID + random 3 digits
                    last_4_nid = national_id[-4:] if len(national_id) >= 4 else national_id.zfill(4)
                    random_3 = f"{random.randint(0, 999):03d}"
                    university_id = f"STU-{last_4_nid}-{random_3}"

                    # Create or Update User
                    user, created = User.objects.update_or_create(
                        username=national_id,
                        defaults={
                            'first_name': first_name,
                            'last_name': last_name,
                            'email': email,
                            'role': User.Role.STUDENT,
                            'academic_year': academic_year,
                            'section_group': section_group,
                        }
                    )

                    # We must preserve the randomly generated university_id if created
                    # If updated, we might not want to overwrite an existing university_id unless it's empty
                    if created or not user.university_id:
                        # Ensure uniqueness just in case
                        while User.objects.exclude(pk=user.pk).filter(university_id=university_id).exists():
                            random_3 = f"{random.randint(0, 999):03d}"
                            university_id = f"STU-{last_4_nid}-{random_3}"
                        
                        user.university_id = university_id

                    # Set password as National_ID
                    user.set_password(national_id)
                    user.save()

                    if created:
                        created_count += 1
                        self.stdout.write(self.style.SUCCESS(
                            f"Created Student: {first_name} {last_name} | Username: {national_id} | Academic Code: {user.university_id}"
                        ))
                    else:
                        updated_count += 1
                        self.stdout.write(self.style.SUCCESS(
                            f"Updated Student: {first_name} {last_name} | Username: {national_id} | Academic Code: {user.university_id}"
                        ))

                    except Exception as e:
                        failed_count += 1
                        self.stdout.write(self.style.ERROR(f"Error processing row {raw_row}: {str(e)}"))

                self.stdout.write(self.style.SUCCESS(f'\nFinished! Created {created_count}, updated {updated_count}, and failed {failed_count} students.'))

        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"File not found: {csv_file}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"An error occurred: {str(e)}"))
