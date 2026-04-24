def student_view(request):
    """Expone viewing_as_student a todos los templates."""
    return {
        'viewing_as_student': getattr(request, 'viewing_as_student', False),
    }
