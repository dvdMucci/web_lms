from django import forms
from courses.models import Enrollment
from .models import ForumPost, ForumReply


class ForumPostForm(forms.ModelForm):
    send_email = forms.BooleanField(
        required=False,
        label='Enviar notificación por email',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    class Meta:
        model = ForumPost
        fields = ['title', 'content', 'is_private', 'student_participant']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Título de la discusión',
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Escribe tu mensaje...',
            }),
            'is_private': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id': 'id_is_private',
            }),
            'student_participant': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_student_participant',
            }),
        }
        labels = {
            'title': 'Título',
            'content': 'Contenido',
            'is_private': 'Mensaje privado (solo visible para el alumno y docentes)',
            'student_participant': 'Alumno destinatario',
        }

    def __init__(self, *args, user=None, course=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.course = course

        if user and user.is_student():
            # Students can't select a target student — it will always be themselves.
            self.fields.pop('student_participant')
            # Students replying to a general post never trigger emails, but for
            # private posts they can notify the teacher.
            # We handle this at the view level; for safety hide send_email here
            # and show it only on private post creation (handled in template via JS).
            self.fields.pop('send_email')
        else:
            # Teachers / admins: populate student list for private posts.
            if course:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                student_ids = Enrollment.objects.filter(
                    course=course, status='approved'
                ).values_list('student_id', flat=True)
                self.fields['student_participant'].queryset = User.objects.filter(
                    pk__in=student_ids
                ).order_by('last_name', 'first_name', 'username')
            self.fields['student_participant'].required = False
            self.fields['student_participant'].empty_label = (
                '-- Seleccionar alumno (solo si el mensaje es privado) --'
            )


class ForumReplyForm(forms.ModelForm):
    send_email = forms.BooleanField(
        required=False,
        label='Enviar notificación por email',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    class Meta:
        model = ForumReply
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Escribe tu respuesta...',
            }),
        }
        labels = {'content': 'Respuesta'}

    def __init__(self, *args, user=None, post=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Students replying in the general (public) forum never send emails.
        if user and user.is_student() and post and not post.is_private:
            self.fields.pop('send_email')
