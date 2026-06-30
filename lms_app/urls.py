from django.urls import path

from . import views

urlpatterns = [
    path('', views.home_redirect, name='home'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('bulk-assignment/', views.bulk_academic_assignment, name='bulk_academic_assignment'),
    path('doctor/dashboard/', views.doctor_dashboard, name='doctor_dashboard'),
    path('student/dashboard/', views.student_dashboard, name='student_dashboard'),
    path('subject/<int:subject_id>/', views.subject_detail, name='subject_detail'),
    path('subject/<int:subject_id>/roster/', views.subject_roster, name='subject_roster'),
    path('subject/<int:subject_id>/update_grade/', views.update_subject_grade, name='update_subject_grade'),
    path('section/<int:section_id>/update_grade/', views.update_section_grade, name='update_section_grade'),
    path('section/<int:section_id>/', views.section_detail, name='section_detail'),
    path('section/<int:section_id>/roster/', views.section_roster, name='section_roster'),
    path('lecture/<int:lecture_id>/', views.lecture_detail, name='lecture_detail'),
    path('lecture/edit/<int:lecture_id>/', views.edit_lecture, name='edit_lecture'),
    path('student/settings/', views.student_settings, name='student_settings'),
    path('doctor/settings/', views.doctor_settings, name='doctor_settings'),
    path('notification/delete/<int:notification_id>/', views.delete_notification, name='delete_notification'),
    path('doctor/upload/<int:subject_id>/', views.upload_material, name='upload_material'),
    path('doctor/upload/book/<int:subject_id>/', views.upload_official_book, name='upload_official_book'),
    path('doctor/upload/section/<int:section_id>/', views.upload_material_section, name='upload_material_section'),
    path('doctor/delete/<int:material_id>/', views.delete_material, name='delete_material'),
    path('doctor/assignment/create/<int:subject_id>/', views.create_assignment, name='create_assignment'),
    path('doctor/assignment/create/section/<int:section_id>/', views.create_assignment_section, name='create_assignment_section'),
    path('doctor/assignment/<int:assignment_id>/submissions/', views.view_submissions, name='view_submissions'),
    path('doctor/assignment/<int:assignment_id>/download-all/', views.download_all_submissions, name='download_all_submissions'),
    path('doctor/assignment/edit/<int:assignment_id>/', views.edit_assignment, name='edit_assignment'),
    path('doctor/assignment/toggle/<int:assignment_id>/', views.toggle_assignment_status, name='toggle_assignment_status'),
    path('doctor/assignment/delete/<int:assignment_id>/', views.delete_assignment, name='delete_assignment'),
    path('doctor/submission/<int:submission_id>/grade/', views.grade_submission, name='grade_submission'),
    path('student/assignment/<int:assignment_id>/submit/', views.submit_assignment, name='submit_assignment'),
    path('student/submission/<int:submission_id>/unsubmit/', views.unsubmit_assignment, name='unsubmit_assignment'),
    path('doctor/announcement/create/<int:subject_id>/', views.create_announcement, name='create_announcement'),
    path('doctor/announcement/create/section/<int:section_id>/', views.create_announcement_section, name='create_announcement_section'),
    path('doctor/announcement/bulk-create/', views.bulk_create_announcement, name='bulk_create_announcement'),
    path('doctor/announcement/delete/<int:announcement_id>/', views.delete_announcement, name='delete_announcement'),
    

    
    path('doctor/schedule/update/<int:subject_id>/', views.update_schedule, name='update_schedule'),
    path('doctor/schedule/update/<int:subject_id>/section/<int:section_id>/', views.update_schedule, name='update_schedule_section'),
    
    path('doctor/grades/export/<int:subject_id>/', views.export_grades_csv, name='export_grades_csv'),
    path('doctor/grades/export/<int:subject_id>/section/<int:section_id>/', views.export_grades_csv, name='export_grades_csv_section'),
    path('doctor/book/delete/<int:subject_id>/', views.delete_official_book, name='delete_official_book'),
    
    path('management/import-students/', views.import_students_csv, name='import_students_csv'),
    
    # Exams
    path('doctor/exam/create/<int:subject_id>/', views.create_exam, name='create_exam'),
    path('doctor/exam/<int:exam_id>/toggle/', views.toggle_exam_status, name='toggle_exam_status'),
    path('doctor/exam/delete/<int:exam_id>/', views.delete_exam, name='delete_exam'),
    path('doctor/exam/<int:exam_id>/questions/', views.manage_exam_questions, name='manage_exam_questions'),
    path('doctor/exam/<int:exam_id>/results/', views.view_exam_results, name='view_exam_results'),
    path('doctor/exam/<int:exam_id>/import/', views.import_exam_questions, name='import_exam_questions'),
    path('doctor/exam/<int:exam_id>/reset/', views.reset_exam_attempts, name='reset_exam_attempts'),
    path('doctor/exam/template/download/', views.download_csv_template, name='download_csv_template'),
    path('doctor/question/delete/<int:question_id>/', views.delete_question, name='delete_question'),
    path('student/exam/<int:exam_id>/take/', views.take_exam, name='take_exam'),
    path('student/exam/save-click/', views.save_exam_click, name='save_exam_click'),
    path('student/exam/<int:exam_id>/review/', views.review_exam, name='review_exam'),
]
