from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Subject, SubjectSection, Material, Assignment, Submission, Announcement, AttendanceSession, AttendanceRecord

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'role', 'university_id', 'academic_year', 'section_group', 'is_active')
    list_filter = ('role', 'department', 'academic_year', 'section_group', 'is_staff', 'is_active')
    search_fields = ('username', 'email', 'university_id', 'first_name', 'last_name')
    actions = ['delete_selected', 'activate_users', 'deactivate_users']
    
    @admin.action(description='Activate selected users')
    def activate_users(self, request, queryset):
        queryset.update(is_active=True)
        
    @admin.action(description='Deactivate selected users')
    def deactivate_users(self, request, queryset):
        queryset.update(is_active=False)
    
    # Customizing the fieldsets to show our custom fields when editing a user
    fieldsets = BaseUserAdmin.fieldsets + (
        ('LMS Profile Information', {'fields': ('role', 'university_id', 'department', 'academic_year', 'section_group')}),
    )
    # Customizing the fieldsets when creating a new user manually via Admin
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('LMS Profile Information', {'fields': ('role', 'university_id', 'department', 'academic_year', 'section_group')}),
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

@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ('subject', 'subject_section', 'date', 'instructor')
    list_filter = ('date', 'subject')

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('session', 'student', 'is_present')
    list_filter = ('is_present', 'session__date', 'session__subject')
    search_fields = ('student__username', 'student__first_name', 'student__last_name')
