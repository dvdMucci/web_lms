import calendar
from datetime import date as date_class

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_http_methods
from openpyxl import Workbook
from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas

from courses.models import Course, Enrollment
from .models import AttendanceSession, AttendanceRecord


def _user_can_manage_attendance(user, course):
    return (
        user.is_authenticated and
        (course.is_instructor_or_collaborator(user) or user.user_type == 'admin')
    )


def _get_default_month_range(today):
    start_date = today.replace(day=1)
    last_day = calendar.monthrange(today.year, today.month)[1]
    end_date = date_class(today.year, today.month, last_day)
    return start_date, end_date


def _get_date_range(request):
    today = timezone.localdate()
    start_date = parse_date(request.GET.get('start_date', ''))
    end_date = parse_date(request.GET.get('end_date', ''))

    if not start_date or not end_date:
        start_date, end_date = _get_default_month_range(today)

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    return start_date, end_date


def _get_report_mode(request):
    return 'full' if request.GET.get('mode') == 'full' else 'summary'


def _build_report_data(course, start_date, end_date):
    enrollments = Enrollment.objects.filter(
        course=course,
        status='approved'
    ).select_related('student').order_by('student__first_name', 'student__last_name', 'student__username')

    records = AttendanceRecord.objects.filter(
        session__course=course,
        session__date__range=(start_date, end_date)
    ).values('student_id').annotate(
        present_count=Count('id', filter=Q(status='present')),
        absent_count=Count('id', filter=Q(status='absent')),
        half_absent_count=Count('id', filter=Q(status='half_absent')),
    )

    summary_by_student = {
        record['student_id']: record
        for record in records
    }

    total_sessions = AttendanceSession.objects.filter(
        course=course,
        date__range=(start_date, end_date)
    ).count()

    report_rows = []
    for enrollment in enrollments:
        student = enrollment.student
        summary = summary_by_student.get(student.id, {})
        present_count = summary.get('present_count', 0)
        absent_count = summary.get('absent_count', 0)
        half_absent_count = summary.get('half_absent_count', 0)
        equivalent_absent = absent_count + (half_absent_count * 0.5)
        attendance_rate = (
            ((present_count + (half_absent_count * 0.5)) / total_sessions) * 100
            if total_sessions else 0
        )
        report_rows.append({
            'student': student,
            'present_count': present_count,
            'absent_count': absent_count,
            'half_absent_count': half_absent_count,
            'equivalent_absent': equivalent_absent,
            'attendance_rate': attendance_rate,
        })

    return report_rows, total_sessions


@login_required
@require_http_methods(["GET", "POST"])
def attendance_take(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    if not _user_can_manage_attendance(request.user, course):
        messages.error(request, 'No tienes permiso para gestionar la asistencia de este curso.')
        return redirect('course_detail', course_id=course.id)

    date_value = request.POST.get('date') or request.GET.get('date')
    selected_date = parse_date(date_value) if date_value else timezone.localdate()

    if not selected_date:
        selected_date = timezone.localdate()
        messages.warning(request, 'Fecha inválida, se usó la fecha actual.')

    session = AttendanceSession.objects.filter(course=course, date=selected_date).first()
    enrollments = Enrollment.objects.filter(
        course=course,
        status='approved'
    ).select_related('student').order_by('student__first_name', 'student__last_name', 'student__username')

    records_by_student = {}
    if session:
        records_by_student = {
            record.student_id: record
            for record in session.records.select_related('student')
        }

    selected_status = {}
    selected_notes = {}
    errors = []
    note_errors = []
    valid_statuses = ['present', 'absent', 'half_absent']

    if request.method == 'POST':
        for enrollment in enrollments:
            student_id = enrollment.student_id
            status = request.POST.get(f'status_{student_id}')
            note = (request.POST.get(f'note_{student_id}') or '').strip()
            if status not in valid_statuses:
                errors.append(enrollment.student.get_full_name() or enrollment.student.username)
            if status == 'half_absent' and not note:
                note_errors.append(enrollment.student.get_full_name() or enrollment.student.username)
            selected_status[student_id] = status
            selected_notes[student_id] = note

        if errors:
            messages.error(
                request,
                'Debes seleccionar presente, ausente o media falta para: ' + ', '.join(errors)
            )
        if note_errors:
            messages.error(
                request,
                'Debes indicar una nota para la media falta de: ' + ', '.join(note_errors)
            )
        if not errors and not note_errors:
            with transaction.atomic():
                if not session:
                    session = AttendanceSession.objects.create(
                        course=course,
                        date=selected_date,
                        created_by=request.user,
                        updated_by=request.user,
                    )
                else:
                    session.updated_by = request.user
                    session.save(update_fields=['updated_by', 'updated_at'])

                for enrollment in enrollments:
                    student = enrollment.student
                    status = selected_status.get(student.id)
                    note = selected_notes.get(student.id) if status == 'half_absent' else ''
                    AttendanceRecord.objects.update_or_create(
                        session=session,
                        student=student,
                        defaults={
                            'status': status,
                            'note': note,
                            'updated_by': request.user,
                        }
                    )

            messages.success(request, 'Asistencia guardada correctamente.')
            return redirect(
                f"{reverse('attendance:attendance_take', kwargs={'course_id': course.id})}"
                f"?date={selected_date}"
            )

    attendance_rows = []
    for enrollment in enrollments:
        student = enrollment.student
        if selected_status:
            status = selected_status.get(student.id)
            note = selected_notes.get(student.id, '')
        else:
            record = records_by_student.get(student.id)
            status = record.status if record else 'present'
            note = record.note if record else ''
        attendance_rows.append({
            'student': student,
            'status': status,
            'note': note,
        })

    context = {
        'course': course,
        'selected_date': selected_date,
        'attendance_rows': attendance_rows,
        'session': session,
    }
    return render(request, 'attendance/attendance_take.html', context)


@login_required
def attendance_report(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    if not _user_can_manage_attendance(request.user, course):
        messages.error(request, 'No tienes permiso para ver la asistencia de este curso.')
        return redirect('course_detail', course_id=course.id)

    start_date, end_date = _get_date_range(request)
    report_rows, total_sessions = _build_report_data(course, start_date, end_date)

    context = {
        'course': course,
        'report_rows': report_rows,
        'start_date': start_date,
        'end_date': end_date,
        'total_sessions': total_sessions,
    }
    return render(request, 'attendance/attendance_report.html', context)


@login_required
def attendance_report_excel(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    if not _user_can_manage_attendance(request.user, course):
        messages.error(request, 'No tienes permiso para ver la asistencia de este curso.')
        return redirect('course_detail', course_id=course.id)

    start_date, end_date = _get_date_range(request)
    report_rows, total_sessions = _build_report_data(course, start_date, end_date)
    report_mode = _get_report_mode(request)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Asistencia'

    if report_mode == 'full':
        sheet.append(['Estudiante', 'Fecha', 'Estado', 'Nota'])
        records = AttendanceRecord.objects.filter(
            session__course=course,
            session__date__range=(start_date, end_date)
        ).select_related('session', 'student').order_by('student__first_name', 'student__last_name', 'session__date')

        for record in records:
            student_name = record.student.get_full_name() or record.student.username
            sheet.append([
                student_name,
                record.session.date.strftime('%Y-%m-%d'),
                record.get_status_display(),
                record.note,
            ])
    else:
        sheet.append([
            'Estudiante',
            'Presentes',
            'Ausentes',
            'Media falta',
            'Inasistencias equivalentes',
            'Porcentaje asistencia',
            'Total sesiones',
        ])

        for row in report_rows:
            student_name = row['student'].get_full_name() or row['student'].username
            sheet.append([
                student_name,
                row['present_count'],
                row['absent_count'],
                row['half_absent_count'],
                row['equivalent_absent'],
                row['attendance_rate'],
                total_sessions,
            ])

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = (
        f'attachment; filename="asistencia_{course.id}_{start_date}_{end_date}.xlsx"'
    )
    workbook.save(response)
    return response


@login_required
def attendance_report_pdf(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    if not _user_can_manage_attendance(request.user, course):
        messages.error(request, 'No tienes permiso para ver la asistencia de este curso.')
        return redirect('course_detail', course_id=course.id)

    start_date, end_date = _get_date_range(request)
    report_rows, total_sessions = _build_report_data(course, start_date, end_date)
    report_mode = _get_report_mode(request)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="asistencia_{course.id}_{start_date}_{end_date}.pdf"'
    )

    pdf = canvas.Canvas(response, pagesize=landscape(letter))
    width, height = landscape(letter)
    y_position = height - 50

    pdf.setFont('Helvetica-Bold', 14)
    pdf.drawString(40, y_position, f'Informe de Asistencia - {course.title}')
    y_position -= 20
    pdf.setFont('Helvetica', 10)
    pdf.drawString(40, y_position, f'Rango: {start_date} a {end_date}')
    y_position -= 20

    if report_mode == 'full':
        headers = ['Estudiante', 'Fecha', 'Estado', 'Nota']
        column_positions = [40, 320, 420, 520]
    else:
        headers = [
            'Estudiante',
            'Presentes',
            'Ausentes',
            'Media falta',
            'Inasist. equiv.',
            '% asistencia',
            'Total sesiones',
        ]
        column_positions = [40, 300, 380, 450, 520, 590, 670]
    pdf.setFont('Helvetica-Bold', 10)
    for header, x_position in zip(headers, column_positions):
        pdf.drawString(x_position, y_position, header)
    y_position -= 15
    pdf.setFont('Helvetica', 10)

    if report_mode == 'full':
        records = AttendanceRecord.objects.filter(
            session__course=course,
            session__date__range=(start_date, end_date)
        ).select_related('session', 'student').order_by('student__first_name', 'student__last_name', 'session__date')

        for record in records:
            if y_position < 50:
                pdf.showPage()
                y_position = height - 50
                pdf.setFont('Helvetica-Bold', 10)
                for header, x_position in zip(headers, column_positions):
                    pdf.drawString(x_position, y_position, header)
                y_position -= 15
                pdf.setFont('Helvetica', 10)

            student_name = record.student.get_full_name() or record.student.username
            pdf.drawString(column_positions[0], y_position, student_name[:60])
            pdf.drawString(column_positions[1], y_position, record.session.date.strftime('%Y-%m-%d'))
            pdf.drawString(column_positions[2], y_position, record.get_status_display())
            pdf.drawString(column_positions[3], y_position, (record.note or '')[:50])
            y_position -= 14
    else:
        for row in report_rows:
            if y_position < 50:
                pdf.showPage()
                y_position = height - 50
                pdf.setFont('Helvetica-Bold', 10)
                for header, x_position in zip(headers, column_positions):
                    pdf.drawString(x_position, y_position, header)
                y_position -= 15
                pdf.setFont('Helvetica', 10)

            student_name = row['student'].get_full_name() or row['student'].username
            pdf.drawString(column_positions[0], y_position, student_name[:60])
            pdf.drawString(column_positions[1], y_position, str(row['present_count']))
            pdf.drawString(column_positions[2], y_position, str(row['absent_count']))
            pdf.drawString(column_positions[3], y_position, str(row['half_absent_count']))
            pdf.drawString(column_positions[4], y_position, str(row['equivalent_absent']))
            pdf.drawString(column_positions[5], y_position, f"{row['attendance_rate']:.1f}%")
            pdf.drawString(column_positions[6], y_position, str(total_sessions))
            y_position -= 14

    pdf.showPage()
    pdf.save()
    return response


@login_required
def attendance_student_view(request, course_id):
    course = get_object_or_404(Course, id=course_id)

    if not request.user.is_student():
        messages.error(request, 'Esta página es solo para estudiantes.')
        return redirect('course_detail', course_id=course.id)

    enrollment = Enrollment.objects.filter(
        course=course,
        student=request.user,
        status='approved'
    ).first()

    if not enrollment:
        messages.error(request, 'No tienes acceso a la asistencia de este curso.')
        return redirect('course_detail', course_id=course.id)

    records = AttendanceRecord.objects.filter(
        session__course=course,
        student=request.user
    ).select_related('session').order_by('-session__date')

    total_present = records.filter(status='present').count()
    total_absent = records.filter(status='absent').count()
    total_half_absent = records.filter(status='half_absent').count()
    equivalent_absent = total_absent + (total_half_absent * 0.5)

    context = {
        'course': course,
        'records': records,
        'total_present': total_present,
        'total_absent': total_absent,
        'total_half_absent': total_half_absent,
        'equivalent_absent': equivalent_absent,
    }
    return render(request, 'attendance/attendance_student.html', context)


@login_required
def attendance_student_detail(request, course_id, student_id):
    course = get_object_or_404(Course, id=course_id)
    if not _user_can_manage_attendance(request.user, course):
        messages.error(request, 'No tienes permiso para ver la asistencia de este curso.')
        return redirect('course_detail', course_id=course.id)

    start_date, end_date = _get_date_range(request)

    User = get_user_model()
    student = get_object_or_404(User, id=student_id, user_type='student')

    enrollment = Enrollment.objects.filter(
        course=course,
        student=student,
        status='approved'
    ).first()

    if not enrollment:
        messages.error(request, 'El estudiante no está aprobado en este curso.')
        return redirect('attendance:attendance_report', course_id=course.id)

    records = AttendanceRecord.objects.filter(
        session__course=course,
        session__date__range=(start_date, end_date),
        student=student
    ).select_related('session').order_by('-session__date')

    total_present = records.filter(status='present').count()
    total_absent = records.filter(status='absent').count()
    total_half_absent = records.filter(status='half_absent').count()
    equivalent_absent = total_absent + (total_half_absent * 0.5)

    context = {
        'course': course,
        'student': student,
        'records': records,
        'start_date': start_date,
        'end_date': end_date,
        'total_present': total_present,
        'total_absent': total_absent,
        'total_half_absent': total_half_absent,
        'equivalent_absent': equivalent_absent,
    }
    return render(request, 'attendance/attendance_student_detail.html', context)
