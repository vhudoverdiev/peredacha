from app.models import STATUS_DONE, STATUS_FINISHERS, STATUS_CONTRACTOR, STATUS_GUARANTEE, STATUS_NOT_STARTED, STATUS_PROBLEM

STATUS_ACTIONS = [STATUS_DONE, STATUS_FINISHERS, STATUS_CONTRACTOR, STATUS_GUARANTEE, STATUS_PROBLEM, STATUS_NOT_STARTED]


def is_problem_details_required(status: str, comment: str | None) -> bool:
    return status == STATUS_PROBLEM and not (comment or "").strip()
