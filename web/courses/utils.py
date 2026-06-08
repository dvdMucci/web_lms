"""
Utility helpers for course-level access checks.
"""


def can_view_course_as_teacher(user, course):
    """
    Returns True if `user` may view `course` with teacher-level (read-only) access.

    Covers:
    - Global teacher / admin / observer roles  (user.can_view_as_teacher())
    - Course-specific observers               (course.observers M2M)
    """
    if user.can_view_as_teacher():
        return True
    return course.observers.filter(pk=user.pk).exists()
