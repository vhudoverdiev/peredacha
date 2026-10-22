"""Project-authorized autocomplete from the shared remark library."""
from flask import abort, jsonify, request
from flask_login import current_user, login_required
from app.permissions import role_required
from app.models import ROLE_MANAGER
from app.routes import bp, selected_project
from app.security import hit_rate_limit
from app.services.remark_catalog import get_catalog
from app.work_points import WORK_POINT_LABELS


def project_required():
    project=selected_project()
    if project is None: abort(400, description='Сначала выберите объект.')
    if not current_user.can_access_project(project): abort(404)
    return project


@bp.get('/remarks/suggestions')
@login_required
@role_required(ROLE_MANAGER)
def remark_suggestions():
    project_required()
    if hit_rate_limit('remark-suggestions',120,60,subject=f'user:{current_user.id}'): abort(429)
    query=(request.args.get('q') or '').strip()
    if len(query)>500: abort(400)
    if len(query)<3: return jsonify(items=[])
    point=request.args.get('point','')
    items=get_catalog().suggestions(query,point=point or None)
    response=jsonify(items=[{'text':row['text'],'points':[{'number':p,'label':WORK_POINT_LABELS[p]} for p in row['points']]} for row in items])
    response.headers['Cache-Control']='private, no-store'
    return response
