from django import template

from lms_app.models import ExamAttempt

register = template.Library()

@register.filter
def get_student_attempt(exam, user):
    if not user.is_authenticated or user.role != 'STUDENT':
        return None
    return ExamAttempt.objects.filter(exam=exam, student=user).first()

@register.filter
def get_total_marks(exam):
    return sum(q.marks for q in exam.questions.all())

@register.simple_tag
def get_answer_for_question(attempt, question):
    from lms_app.models import StudentAnswer
    answer = StudentAnswer.objects.filter(attempt=attempt, question=question).first()
    return answer.selected_choice if answer else None

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)
