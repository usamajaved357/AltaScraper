"""domain/job_owner.py -- whose job is this?

WHY THIS EXISTS
Long-running work (image generation, auto-fix) is deliberately server-side: it
keeps going when the browser is closed, and any of your own tabs can watch the
same job. That was the right design for one user.

With several users it leaked. The registries recorded what a job was doing but
never who started it, so /genimage/jobs_active returned EVERY running job and the
floating status bar -- polled every two seconds on every page -- showed the owner
their VA's image generation. Stop All stopped everyone's work, from anyone.

One helper, used by both registries, so the two cannot answer this differently.

DELIBERATE: A MANAGER SEES EVERYTHING
Someone who can manage users is running the operation and is accountable for what
it costs, so hiding a runaway job from them would be unhelpful. Everyone else
sees only their own. Jobs recorded before this existed carry no owner and stay
visible to everyone -- invisible in-flight work would be worse than shared work.
"""
try:
    from flask import has_request_context, session
except Exception:
    def has_request_context():
        return False
    session = None

UNOWNED = ""          # a job started before owners were recorded, or by background work


def current():
    """The signed-in user's id, or "" when there is nobody to attribute work to
    (the shared-password owner, or a background thread)."""
    if not has_request_context() or session is None:
        return UNOWNED
    try:
        return str(session.get("uid") or UNOWNED)
    except Exception:
        return UNOWNED


def person(config_path, uid=None):
    """WHO A USER ID IS: {"id", "name", "email"}, or {} when unknown.

    The ONE lookup behind every "who did it" label (Rule 12): the upload
    history (upload_log.uploader), the activity log (activity.person) and Dr
    PPC's records all name people through this. `uid` None = the signed-in
    user. Each caller chooses how to word the label; the lookup is shared."""
    try:
        uid = current() if uid is None else str(uid or "")
        if not uid:
            return {}
        from auth import users
        u = users.get_user(config_path, uid) or {}
        return {"id": uid, "name": str(u.get("name") or ""), "email": str(u.get("email") or "")}
    except Exception:
        return {}


def label(config_path, uid=None):
    """The person as the RECORDS name them: email, else name, else the id; ""
    when nobody is signed in (the shared-password owner, or background work).
    Upload history, Dr PPC, the repricer's manual prices and the error log all
    use this one wording."""
    p = person(config_path, uid)
    if not p:
        return ""
    return p["email"] or p["name"] or p["id"]


def _is_manager(config_path):
    """Can the caller manage users? They see everything."""
    try:
        from auth import users
        uid = current()
        if not uid:
            # The shared-password owner is the only user, so nothing is hidden
            # from them either.
            return True
        u = users.get_user(config_path, uid)
        return bool(u and users.has_permission(u, "manage_users"))
    except Exception:
        # Never let a permissions lookup failure hide someone's own work.
        return False


def may_see(job, config_path=None):
    """Should this job appear to the caller?"""
    if not isinstance(job, dict):
        return False
    owner = str(job.get("owner") or UNOWNED)
    if not owner:
        return True                      # legacy / background work
    if owner == current():
        return True
    return _is_manager(config_path)


def mine_only(job):
    """Strict ownership, for actions rather than for viewing.

    Stopping is not watching: a manager may need to SEE a runaway job, but
    cancelling someone else's work by pressing a button labelled "Stop all" is
    never what was meant.
    """
    if not isinstance(job, dict):
        return False
    owner = str(job.get("owner") or UNOWNED)
    return (not owner) or owner == current()


def stamp(job):
    """Record the owner on a job being created. Returns the same dict."""
    if isinstance(job, dict):
        job["owner"] = current()
    return job
