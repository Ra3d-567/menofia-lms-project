from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('doctor/dashboard/', views.doctor_dashboard, name='doctor_dashboard'),
    path('student/dashboard/', views.student_dashboard, name='student_dashboard'),
    path('student/settings/', views.student_settings, name='student_settings'),
    path('doctor/settings/', views.doctor_settings, name='doctor_settings'),
    path('doctor/upload/<int:subject_id>/', views.upload_material, name='upload_material'),
    path('doctor/upload/book/<int:subject_id>/', views.upload_official_book, name='upload_official_book'),
    path('doctor/upload/section/<int:section_id>/', views.upload_material_section, name='upload_material_section'),
    path('doctor/delete/<int:material_id>/', views.delete_material, name='delete_material'),
    path('doctor/assignment/create/<int:subject_id>/', views.create_assignment, name='create_assignment'),
    path('doctor/assignment/create/section/<int:section_id>/', views.create_assignment_section, name='create_assignment_section'),
    path('doctor/assignment/<int:assignment_id>/submissions/', views.view_submissions, name='view_submissions'),
    path('doctor/assignment/delete/<int:assignment_id>/', views.delete_assignment, name='delete_assignment'),
    path('doctor/submission/<int:submission_id>/grade/', views.grade_submission, name='grade_submission'),
    path('student/assignment/<int:assignment_id>/submit/', views.submit_assignment, name='submit_assignment'),
    path('student/submission/<int:submission_id>/unsubmit/', views.unsubmit_assignment, name='unsubmit_assignment'),
    path('doctor/announcement/create/<int:subject_id>/', views.create_announcement, name='create_announcement'),
    path('doctor/announcement/create/section/<int:section_id>/', views.create_announcement_section, name='create_announcement_section'),
    path('doctor/announcement/delete/<int:announcement_id>/', views.delete_announcement, name='delete_announcement'),
    
    path('doctor/attendance/start/<int:subject_id>/', views.start_attendance_session, name='start_attendance_session'),
    path('doctor/attendance/start/<int:subject_id>/section/<int:section_id>/', views.start_attendance_session, name='start_attendance_session_section'),
    path('doctor/attendance/end/<int:session_id>/', views.end_attendance_session, name='end_attendance_session'),
    path('student/attendance/submit/<int:session_id>/', views.submit_attendance_pin, name='submit_attendance_pin'),
    path('doctor/attendance/edit/<int:session_id>/', views.edit_attendance, name='edit_attendance'),
    path('doctor/attendance/report/<int:session_id>/', views.attendance_report_detail, name='attendance_report_detail'),
    path('doctor/attendance/export/<int:subject_id>/', views.export_attendance_csv, name='export_attendance_csv'),
    path('doctor/attendance/export/<int:subject_id>/section/<int:section_id>/', views.export_attendance_csv, name='export_attendance_csv_section'),
    
    path('doctor/schedule/update/<int:subject_id>/', views.update_schedule, name='update_schedule'),
    path('doctor/schedule/update/<int:subject_id>/section/<int:section_id>/', views.update_schedule, name='update_schedule_section'),
    
    path('management/import-students/', views.import_students_csv, name='import_students_csv'),
]
