from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Max
from django.core.exceptions import ValidationError
import os
from .models import Unit, Tema
from .forms import UnitForm, TemaForm, MaterialUploadForm, MaterialEditForm
from courses.models import Course, Enrollment

@login_required
def unit_list(request, course_id):
    """List all units for a course"""
    course = get_object_or_404(Course, id=course_id)
    
    # Check if user can view the course
    can_view = False
    if request.user.is_teacher() or request.user.user_type == 'admin':
        can_view = True
    elif request.user.is_student():
        # Check if student is enrolled and approved
        enrollment = Enrollment.objects.filter(
            student=request.user,
            course=course,
            status='approved'
        ).first()
        can_view = enrollment is not None
    
    if not can_view:
        messages.error(request, 'No tienes permiso para ver las unidades de este curso.')
        if request.user.is_student():
            return redirect('course_list_student')
        else:
            return redirect('course_list_teacher')
    
    # Get units - teachers see all, students only non-paused
    if request.user.is_teacher() or request.user.user_type == 'admin':
        units = Unit.objects.filter(course=course).order_by('order', 'created_at')
    else:
        units = Unit.objects.filter(course=course, is_paused=False).order_by('order', 'created_at')
    
    # Check if user can manage units
    can_manage = (
        course.instructor == request.user or
        request.user in course.collaborators.all() or
        request.user.user_type == 'admin'
    )
    
    context = {
        'course': course,
        'units': units,
        'can_manage': can_manage,
    }
    return render(request, 'units/unit_list.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def unit_create(request, course_id):
    """Create a new unit"""
    course = get_object_or_404(Course, id=course_id)
    
    # Check permissions: instructor, collaborator, or admin
    can_manage = (
        course.instructor == request.user or
        request.user in course.collaborators.all() or
        request.user.user_type == 'admin'
    )
    
    if not can_manage:
        messages.error(request, 'Solo el instructor, colaboradores o administradores pueden crear unidades.')
        return redirect('units:unit_list', course_id=course_id)
    
    if request.method == 'POST':
        form = UnitForm(request.POST, user=request.user, course=course)
        if form.is_valid():
            unit = form.save(commit=False)
            unit.course = course
            unit.created_by = request.user
            # Save the unit (validation happens in model.save())
            try:
                unit.save()
            except ValidationError as e:
                # Handle validation errors
                if hasattr(e, 'error_dict'):
                    for field, errors in e.error_dict.items():
                        for error in errors:
                            messages.error(request, f'{field}: {error}')
                else:
                    messages.error(request, str(e))
                context = {
                    'form': form,
                    'course': course,
                    'title': 'Crear Unidad',
                }
                return render(request, 'units/unit_form.html', context)
            messages.success(request, f'Unidad "{unit.title}" creada exitosamente.')
            return redirect('units:unit_list', course_id=course_id)
    else:
        # Get next order number
        max_order = Unit.objects.filter(course=course).aggregate(Max('order'))['order__max']
        next_order = (max_order or -1) + 1
        form = UnitForm(user=request.user, course=course, initial={'order': next_order})
    
    context = {
        'form': form,
        'course': course,
        'title': 'Crear Unidad',
    }
    return render(request, 'units/unit_form.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def unit_edit(request, course_id, unit_id):
    """Edit an existing unit"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    
    # Check permissions: instructor, collaborator, or admin
    if not unit.can_be_managed_by(request.user):
        messages.error(request, 'No tienes permiso para editar esta unidad.')
        return redirect('units:unit_list', course_id=course_id)
    
    if request.method == 'POST':
        form = UnitForm(request.POST, instance=unit, user=request.user, course=course)
        if form.is_valid():
            unit = form.save()
            messages.success(request, f'Unidad "{unit.title}" actualizada exitosamente.')
            return redirect('units:unit_list', course_id=course_id)
    else:
        form = UnitForm(instance=unit, user=request.user, course=course)
    
    context = {
        'form': form,
        'course': course,
        'unit': unit,
        'title': 'Editar Unidad',
    }
    return render(request, 'units/unit_form.html', context)


@login_required
@require_http_methods(["POST"])
def unit_pause(request, course_id, unit_id):
    """Pause or resume a unit"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    
    # Check permissions
    if not unit.can_be_managed_by(request.user):
        messages.error(request, 'No tienes permiso para pausar/reanudar esta unidad.')
        return redirect('units:unit_list', course_id=course_id)
    
    unit.is_paused = not unit.is_paused
    unit.save()
    
    action = 'pausada' if unit.is_paused else 'reanudada'
    messages.success(request, f'Unidad "{unit.title}" {action} exitosamente.')
    return redirect('units:unit_list', course_id=course_id)


@login_required
@require_http_methods(["GET", "POST"])
def unit_delete(request, course_id, unit_id):
    """Delete a unit (with confirmation)"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    
    # Check permissions
    if not unit.can_be_managed_by(request.user):
        messages.error(request, 'No tienes permiso para eliminar esta unidad.')
        return redirect('units:unit_list', course_id=course_id)
    
    if request.method == 'POST':
        unit_title = unit.title
        unit.delete()
        messages.success(request, f'Unidad "{unit_title}" eliminada exitosamente.')
        return redirect('units:unit_list', course_id=course_id)
    
    # GET request: show confirmation page
    context = {
        'course': course,
        'unit': unit,
    }
    return render(request, 'units/unit_delete_confirm.html', context)


@login_required
def unit_detail(request, course_id, unit_id):
    """View unit details with themes"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    
    # Check if user can view the unit
    can_view = False
    if request.user.is_teacher() or request.user.user_type == 'admin':
        can_view = True
    elif request.user.is_student():
        # Check if student is enrolled and approved, and unit is not paused
        enrollment = Enrollment.objects.filter(
            student=request.user,
            course=course,
            status='approved'
        ).first()
        can_view = enrollment is not None and unit.is_visible_to_students()
    
    if not can_view:
        messages.error(request, 'No tienes permiso para ver esta unidad.')
        if request.user.is_student():
            return redirect('course_list_student')
        else:
            return redirect('course_list_teacher')
    
    # Get themes for this unit
    if request.user.is_teacher() or request.user.user_type == 'admin':
        temas = Tema.objects.filter(unit=unit).order_by('order', 'created_at')
    else:
        temas = Tema.objects.filter(unit=unit, is_paused=False).order_by('order', 'created_at')
    
    # Check if user can manage
    can_manage = unit.can_be_managed_by(request.user)
    
    context = {
        'course': course,
        'unit': unit,
        'temas': temas,
        'can_manage': can_manage,
    }
    return render(request, 'units/unit_detail.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def tema_detail(request, course_id, unit_id, tema_id):
    """View theme details with materials and assignments"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)

    can_view = False
    if request.user.is_teacher() or request.user.user_type == 'admin':
        can_view = True
    elif request.user.is_student():
        enrollment = Enrollment.objects.filter(
            student=request.user,
            course=course,
            status='approved'
        ).first()
        can_view = enrollment is not None and tema.is_visible_to_students()

    if not can_view:
        messages.error(request, 'No tienes permiso para ver este tema.')
        if request.user.is_student():
            return redirect('course_list_student')
        return redirect('course_list_teacher')

    from materials.models import Material
    if request.user.is_teacher() or request.user.user_type == 'admin':
        materials = Material.objects.filter(tema=tema).order_by('-uploaded_at')
    else:
        materials = Material.objects.filter(tema=tema, is_published=True).order_by('-uploaded_at')

    from assignments.models import Assignment
    if request.user.is_teacher() or request.user.user_type == 'admin':
        assignments = Assignment.objects.filter(tema=tema).order_by('due_date', 'created_at')
    else:
        assignments = Assignment.objects.filter(
            tema=tema,
            is_active=True,
            is_published=True
        ).order_by('due_date', 'created_at')

    can_manage = unit.can_be_managed_by(request.user)

    context = {
        'course': course,
        'unit': unit,
        'tema': tema,
        'materials': materials,
        'assignments': assignments,
        'can_manage': can_manage,
    }
    return render(request, 'units/tema_detail.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def tema_create(request, course_id, unit_id):
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)

    if not unit.can_be_managed_by(request.user):
        messages.error(request, 'Solo el instructor, colaboradores o administradores pueden crear temas.')
        return redirect('units:unit_detail', course_id=course_id, unit_id=unit_id)

    if request.method == 'POST':
        form = TemaForm(request.POST, user=request.user, unit=unit)
        if form.is_valid():
            tema = form.save(commit=False)
            tema.unit = unit
            tema.created_by = request.user
            try:
                tema.save()
            except ValidationError as e:
                if hasattr(e, 'error_dict'):
                    for field, errors in e.error_dict.items():
                        for error in errors:
                            messages.error(request, f'{field}: {error}')
                else:
                    messages.error(request, str(e))
                context = {
                    'form': form,
                    'course': course,
                    'unit': unit,
                    'title': 'Crear Tema',
                }
                return render(request, 'units/tema_form.html', context)
            messages.success(request, f'Tema "{tema.title}" creado exitosamente.')
            return redirect('units:unit_detail', course_id=course_id, unit_id=unit_id)
    else:
        max_order = Tema.objects.filter(unit=unit).aggregate(Max('order'))['order__max']
        next_order = (max_order or -1) + 1
        form = TemaForm(user=request.user, unit=unit, initial={'order': next_order, 'is_paused': True})

    context = {
        'form': form,
        'course': course,
        'unit': unit,
        'title': 'Crear Tema',
    }
    return render(request, 'units/tema_form.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def tema_edit(request, course_id, unit_id, tema_id):
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)

    if not tema.can_be_managed_by(request.user):
        messages.error(request, 'No tienes permiso para editar este tema.')
        return redirect('units:unit_detail', course_id=course_id, unit_id=unit_id)

    if request.method == 'POST':
        form = TemaForm(request.POST, instance=tema, user=request.user, unit=unit)
        if form.is_valid():
            tema = form.save()
            messages.success(request, f'Tema "{tema.title}" actualizado exitosamente.')
            return redirect('units:tema_detail', course_id=course_id, unit_id=unit_id, tema_id=tema.id)
    else:
        form = TemaForm(instance=tema, user=request.user, unit=unit)

    context = {
        'form': form,
        'course': course,
        'unit': unit,
        'tema': tema,
        'title': 'Editar Tema',
    }
    return render(request, 'units/tema_form.html', context)


@login_required
@require_http_methods(["POST"])
def tema_pause(request, course_id, unit_id, tema_id):
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)

    if not tema.can_be_managed_by(request.user):
        messages.error(request, 'No tienes permiso para pausar/reanudar este tema.')
        return redirect('units:unit_detail', course_id=course_id, unit_id=unit_id)

    tema.is_paused = not tema.is_paused
    tema.save()

    action = 'pausado' if tema.is_paused else 'reanudado'
    messages.success(request, f'Tema "{tema.title}" {action} exitosamente.')
    return redirect('units:unit_detail', course_id=course_id, unit_id=unit_id)


@login_required
@require_http_methods(["GET", "POST"])
def tema_delete(request, course_id, unit_id, tema_id):
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)

    if not tema.can_be_managed_by(request.user):
        messages.error(request, 'No tienes permiso para eliminar este tema.')
        return redirect('units:unit_detail', course_id=course_id, unit_id=unit_id)

    if request.method == 'POST':
        tema_title = tema.title
        tema.delete()
        messages.success(request, f'Tema "{tema_title}" eliminado exitosamente.')
        return redirect('units:unit_detail', course_id=course_id, unit_id=unit_id)

    context = {
        'course': course,
        'unit': unit,
        'tema': tema,
    }
    return render(request, 'units/tema_delete_confirm.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def material_upload(request, course_id, unit_id, tema_id):
    """Upload material to a theme"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)

    if not unit.can_be_managed_by(request.user):
        messages.error(request, 'No tienes permiso para subir materiales a este tema.')
        return redirect('units:tema_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id)

    if request.method == 'POST':
        form = MaterialUploadForm(request.POST, request.FILES, user=request.user, course=course, tema=tema)
        if form.is_valid():
            material = form.save(commit=False)
            material.course = course
            material.tema = tema
            material.uploaded_by = request.user
            material.material_type = form.cleaned_data['material_type']

            if material.material_type == 'file' and material.file:
                if not material.original_filename:
                    material.original_filename = os.path.basename(material.file.name)

            material.save()

            if material.is_published and not material.scheduled_publish_at and material.send_notification_email:
                try:
                    from core.notifications import notify_material_published
                    sent = notify_material_published(material)
                    if sent > 0:
                        messages.success(request, f'Material "{material.title}" subido y publicado exitosamente. Se enviaron {sent} notificaciones por correo.')
                    else:
                        messages.success(request, f'Material "{material.title}" subido y publicado exitosamente.')
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f'Error al enviar notificaciones para material {material.id}: {e}')
                    messages.success(request, f'Material "{material.title}" subido exitosamente. (Error al enviar notificaciones)')
            else:
                if material.scheduled_publish_at:
                    messages.success(request, f'Material "{material.title}" subido exitosamente. Se publicará el {material.scheduled_publish_at.strftime("%d/%m/%Y a las %H:%M")}.')
                else:
                    messages.success(request, f'Material "{material.title}" subido exitosamente.')

            return redirect('units:tema_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id)
    else:
        form = MaterialUploadForm(user=request.user, course=course, tema=tema)

    context = {
        'form': form,
        'course': course,
        'unit': unit,
        'tema': tema,
        'title': 'Subir Material',
    }
    return render(request, 'units/material_upload.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def material_edit(request, course_id, unit_id, tema_id, material_id):
    """Edit material from a theme"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)
    from materials.models import Material
    material = get_object_or_404(Material, id=material_id, tema=tema, course=course)

    if not unit.can_be_managed_by(request.user):
        messages.error(request, 'No tienes permiso para editar este material.')
        return redirect('units:tema_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id)

    from .forms import MaterialEditForm
    if request.method == 'POST':
        form = MaterialEditForm(request.POST, request.FILES, instance=material, user=request.user, course=course, tema=tema)
        if form.is_valid():
            old_is_published = material.is_published
            material = form.save()
            
            # Si se publicó por primera vez y se solicitó notificación, enviar correos
            if not old_is_published and material.is_published and not material.scheduled_publish_at and material.send_notification_email:
                try:
                    from core.notifications import notify_material_published
                    sent = notify_material_published(material)
                    if sent > 0:
                        messages.success(request, f'Material "{material.title}" actualizado y publicado exitosamente. Se enviaron {sent} notificaciones por correo.')
                    else:
                        messages.success(request, f'Material "{material.title}" actualizado y publicado exitosamente.')
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f'Error al enviar notificaciones para material {material.id}: {e}')
                    messages.success(request, f'Material "{material.title}" actualizado exitosamente. (Error al enviar notificaciones)')
            else:
                messages.success(request, f'Material "{material.title}" actualizado exitosamente.')
            
            return redirect('units:tema_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id)
    else:
        form = MaterialEditForm(instance=material, user=request.user, course=course, tema=tema)

    context = {
        'form': form,
        'course': course,
        'unit': unit,
        'tema': tema,
        'material': material,
        'title': 'Editar Material',
    }
    return render(request, 'units/material_edit.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def material_delete(request, course_id, unit_id, tema_id, material_id):
    """Delete material from a theme"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)
    from materials.models import Material
    material = get_object_or_404(Material, id=material_id, tema=tema, course=course)

    if not unit.can_be_managed_by(request.user):
        messages.error(request, 'No tienes permiso para eliminar este material.')
        return redirect('units:tema_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id)

    if request.method == 'POST':
        material_title = material.title
        material.delete()
        messages.success(request, f'Material "{material_title}" eliminado exitosamente.')
        return redirect('units:tema_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id)

    context = {
        'course': course,
        'unit': unit,
        'tema': tema,
        'material': material,
        'has_file': bool(material.file),
    }
    return render(request, 'units/material_delete_confirm.html', context)
