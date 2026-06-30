from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (AdminDevice, Announcement, Assignment, Material, Subject,
                     SubjectSection, Submission, User)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'role', 'university_id', 'academic_year', 'section_group', 'is_active')
    list_filter = ('role', 'department', 'academic_year', 'section_group', 'is_staff', 'is_active')
    search_fields = ('username', 'email', 'university_id', 'first_name', 'last_name')
    actions = ['delete_selected', 'activate_users', 'deactivate_users', 'promote_to_next_year']
    
    @admin.action(description='Activate selected users')
    def activate_users(self, request, queryset):
        queryset.update(is_active=True)
        
    @admin.action(description='Deactivate selected users')
    def deactivate_users(self, request, queryset):
        queryset.update(is_active=False)

    @admin.action(description='ترقية الطلاب المحددين للفرقة التالية')
    def promote_to_next_year(self, request, queryset):
        promoted_count = 0
        from django.contrib import messages
        
        for user in queryset:
            if user.role == User.Role.STUDENT and user.academic_year:
                if user.academic_year < 4:
                    user.academic_year += 1
                    user.save(update_fields=['academic_year'])
                    
                    user.registered_subjects.clear()
                    subjects = Subject.objects.filter(academic_year=user.academic_year)
                    if subjects.exists():
                        user.registered_subjects.set(subjects)
                    
                    promoted_count += 1
                    
        self.message_user(request, f"Successfully promoted {promoted_count} students to the next academic year.", level=messages.SUCCESS)
    
    filter_horizontal = ('registered_subjects',)
    
    # Customizing the fieldsets to show our custom fields when editing a user
    fieldsets = BaseUserAdmin.fieldsets + (
        ('LMS Profile Information', {'fields': ('role', 'university_id', 'department', 'academic_year', 'section_group', 'registered_subjects')}),
    )
    # Customizing the fieldsets when creating a new user manually via Admin
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('LMS Profile Information', {'fields': ('role', 'university_id', 'department', 'academic_year', 'section_group', 'registered_subjects')}),
    )

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'professor', 'academic_year')
    list_filter = ('professor', 'academic_year')
    search_fields = ('name', 'code', 'professor__username', 'professor__first_name', 'professor__last_name')

@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject', 'material_type', 'created_at')
    list_filter = ('material_type', 'subject', 'created_at')
    search_fields = ('title', 'subject__name', 'subject__code')

@admin.register(SubjectSection)
class SubjectSectionAdmin(admin.ModelAdmin):
    list_display = ('subject', 'section_group', 'instructor')
    list_filter = ('subject', 'section_group', 'instructor')
    search_fields = ('subject__code', 'subject__name', 'instructor__username')

@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject', 'subject_section', 'due_date', 'max_grade')
    list_filter = ('subject', 'due_date')
    search_fields = ('title', 'subject__name', 'subject__code')

@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('assignment', 'student', 'grade', 'submitted_at')
    list_filter = ('assignment', 'submitted_at')
    search_fields = ('student__username', 'assignment__title')

@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject', 'subject_section', 'author', 'created_at')
    list_filter = ('subject', 'created_at', 'author')
    search_fields = ('title', 'content', 'subject__name', 'author__username')



@admin.register(AdminDevice)
class AdminDeviceAdmin(admin.ModelAdmin):
    list_display = ('user', 'device_name', 'created_at', 'device_token')
    search_fields = ('user__username', 'device_name')
    list_filter = ('created_at',)
    readonly_fields = ('device_token', 'created_at')


from .models import Choice, Exam, ExamAttempt, Question, StudentAnswer


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 4

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('text', 'exam', 'question_type', 'marks')
    list_filter = ('exam', 'question_type')
    inlines = [ChoiceInline]

@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject', 'start_date', 'end_date', 'is_active')
    list_filter = ('subject', 'is_active')

@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ('student', 'exam', 'score', 'is_submitted', 'start_time')
    list_filter = ('exam', 'is_submitted')

@admin.register(StudentAnswer)
class StudentAnswerAdmin(admin.ModelAdmin):
    list_display = ('attempt', 'question', 'selected_choice')
    list_filter = ('attempt__exam',)

