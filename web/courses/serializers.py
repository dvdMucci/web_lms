from rest_framework import serializers
from .models import Course, Enrollment
from django.conf import settings

class CourseSerializer(serializers.ModelSerializer):
    instructor_name = serializers.CharField(source='instructor.get_full_name', read_only=True)
    current_enrollments = serializers.ReadOnlyField()
    available_spots = serializers.ReadOnlyField()

    class Meta:
        model = Course
        fields = [
            'id', 'title', 'description', 'instructor', 'instructor_name',
            'created_at', 'updated_at', 'enrollment_limit', 'is_active',
            'schedule', 'current_enrollments', 'available_spots'
        ]
        read_only_fields = ['created_at', 'updated_at', 'instructor_name', 'current_enrollments', 'available_spots']

    def create(self, validated_data):
        # Set the instructor to the current user (must be a teacher)
        validated_data['instructor'] = self.context['request'].user
        return super().create(validated_data)

    def validate_instructor(self, value):
        if not value.is_teacher():
            raise serializers.ValidationError("Solo los profesores pueden crear cursos.")
        return value


class EnrollmentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.get_full_name', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)

    class Meta:
        model = Enrollment
        fields = [
            'id', 'student', 'student_name', 'course', 'course_title',
            'enrolled_at', 'status'
        ]
        read_only_fields = ['enrolled_at', 'student_name', 'course_title']

    def create(self, validated_data):
        # Set the student to the current user (must be a student)
        validated_data['student'] = self.context['request'].user
        return super().create(validated_data)

    def validate_student(self, value):
        if not value.is_student():
            raise serializers.ValidationError("Solo los estudiantes pueden inscribirse en cursos.")
        return value

    def validate(self, data):
        course = data.get('course')
        student = data.get('student', self.context['request'].user)

        if course and student:
            # Check if student is already enrolled
            if Enrollment.objects.filter(student=student, course=course).exists():
                raise serializers.ValidationError("Ya estás inscrito en este curso.")

            # Check if course is at capacity
            if course.current_enrollments >= course.enrollment_limit:
                raise serializers.ValidationError("El curso ha alcanzado su límite de inscripción.")

        return data