from rest_framework import serializers
from .models import Material
from django.conf import settings

class MaterialSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source="uploaded_by.get_full_name", read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Material
        fields = [
            "id", "title", "description", "course", "course_title",
            "uploaded_by", "uploaded_by_name", "file", "file_url",
            "visibility", "uploaded_at", "file_size", "file_type"
        ]
        read_only_fields = ["uploaded_at", "uploaded_by", "uploaded_by_name", "course_title", "file_url", "file_size", "file_type"]

    def get_file_url(self, obj):
        if obj.file:
            return obj.file.url
        return None

    def create(self, validated_data):
        # Set the uploaded_by to the current user
        validated_data["uploaded_by"] = self.context["request"].user
        return super().create(validated_data)

    def validate_course(self, value):
        user = self.context["request"].user
        if not (value.instructor == user or user.user_type == 'admin'):
            raise serializers.ValidationError("Solo puedes subir materiales a cursos que impartes.")
        return value


class MaterialUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Material
        fields = ["title", "description", "course", "file", "visibility"]

    def create(self, validated_data):
        validated_data["uploaded_by"] = self.context["request"].user
        return super().create(validated_data)

    def validate_course(self, value):
        user = self.context["request"].user
        if not (value.instructor == user or user.user_type == 'admin'):
            raise serializers.ValidationError("Solo puedes subir materiales a cursos que impartes.")
        return value

    def validate_file(self, value):
        # Basic file validation
        max_size = 50 * 1024 * 1024  # 50MB
        if value.size > max_size:
            raise serializers.ValidationError("El archivo no puede ser mayor a 50MB.")

        allowed_types = [
            'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx',
            'txt', 'jpg', 'jpeg', 'png', 'gif', 'mp4', 'avi', 'mov'
        ]
        file_extension = value.name.split('.')[-1].lower()
        if file_extension not in allowed_types:
            raise serializers.ValidationError(f"Tipo de archivo no permitido. Tipos permitidos: {', '.join(allowed_types)}")

        return value