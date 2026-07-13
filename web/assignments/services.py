"""Helpers for assignment submissions and group collaborators."""

from django.db.models import Prefetch

from .models import AssignmentCollaborator, AssignmentSubmission, AssignmentSubmissionFile


def get_effective_submission(assignment, student):
    """
    Return (submission, is_collaborator) for a student on an assignment.

    Own submissions take precedence. If the student has none but is a
    collaborator on someone else's work, return that owner's latest submission
    so status and grades are shared with the group.
    """
    files_prefetch = Prefetch(
        'attachment_files',
        queryset=AssignmentSubmissionFile.objects.order_by('order', 'id'),
    )
    own = (
        AssignmentSubmission.objects.filter(assignment=assignment, student=student)
        .prefetch_related(files_prefetch)
        .order_by('-version')
        .first()
    )
    if own is not None:
        return own, False

    if not getattr(assignment, 'allow_group_work', False):
        return None, False

    collab = (
        AssignmentCollaborator.objects.filter(
            submission__assignment=assignment,
            student=student,
        )
        .select_related('submission', 'submission__student')
        .order_by('-submission__version')
        .first()
    )
    if collab is None:
        return None, False

    owner_latest = (
        AssignmentSubmission.objects.filter(
            assignment=assignment,
            student_id=collab.submission.student_id,
        )
        .prefetch_related(files_prefetch)
        .order_by('-version')
        .first()
    )
    return (owner_latest or collab.submission), True


def map_effective_submissions(assignment, students):
    """
    Bulk resolve effective submissions for many students.

    Returns dict student_id -> {'submission': Submission|None, 'is_collaborator': bool}.
    """
    student_ids = [s.id for s in students]
    result = {
        sid: {'submission': None, 'is_collaborator': False}
        for sid in student_ids
    }
    if not student_ids:
        return result

    files_prefetch = Prefetch(
        'attachment_files',
        queryset=AssignmentSubmissionFile.objects.order_by('order', 'id'),
    )

    own_latest = {}
    for submission in (
        AssignmentSubmission.objects.filter(
            assignment=assignment,
            student_id__in=student_ids,
        )
        .prefetch_related(files_prefetch)
        .order_by('student_id', '-version')
    ):
        if submission.student_id not in own_latest:
            own_latest[submission.student_id] = submission

    for sid, submission in own_latest.items():
        result[sid] = {'submission': submission, 'is_collaborator': False}

    missing_ids = [sid for sid in student_ids if result[sid]['submission'] is None]
    if not missing_ids or not getattr(assignment, 'allow_group_work', False):
        return result

    # Collaborator -> owner_id (prefer highest version link)
    owner_by_collaborator = {}
    for collab in (
        AssignmentCollaborator.objects.filter(
            submission__assignment=assignment,
            student_id__in=missing_ids,
        )
        .select_related('submission')
        .order_by('student_id', '-submission__version')
    ):
        if collab.student_id not in owner_by_collaborator:
            owner_by_collaborator[collab.student_id] = collab.submission.student_id

    if not owner_by_collaborator:
        return result

    owner_ids = set(owner_by_collaborator.values())
    owner_latest = {}
    for submission in (
        AssignmentSubmission.objects.filter(
            assignment=assignment,
            student_id__in=owner_ids,
        )
        .prefetch_related(files_prefetch)
        .order_by('student_id', '-version')
    ):
        if submission.student_id not in owner_latest:
            owner_latest[submission.student_id] = submission

    for collaborator_id, owner_id in owner_by_collaborator.items():
        submission = owner_latest.get(owner_id)
        if submission is not None:
            result[collaborator_id] = {
                'submission': submission,
                'is_collaborator': True,
            }

    return result


def copy_collaborators(from_submission, to_submission):
    """Copy group collaborators from one submission version to another."""
    if from_submission is None or to_submission is None:
        return 0
    if from_submission.pk == to_submission.pk:
        return 0

    existing = set(
        AssignmentCollaborator.objects.filter(
            submission=to_submission,
        ).values_list('student_id', flat=True)
    )
    created = 0
    for collab in AssignmentCollaborator.objects.filter(submission=from_submission):
        if collab.student_id in existing:
            continue
        if collab.student_id == to_submission.student_id:
            continue
        AssignmentCollaborator.objects.create(
            submission=to_submission,
            student_id=collab.student_id,
        )
        created += 1
    return created
