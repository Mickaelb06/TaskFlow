"""Moteur de planification : dépendances, chemin critique, prévision de fin, risques.

Fonctions déterministes (aucun appel externe) : mêmes données, mêmes résultats.
Les durées sont en jours calendaires. Une tâche n'a de « span » que si elle a au moins une date.
"""
from collections import defaultdict
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

from . import planning_engine as engine
from .models import Task

DAY = timedelta(days=1)
OVERLOAD_THRESHOLD = 4  # tâches ouvertes simultanées pour un même membre
SOON_DAYS = 7


# ---------------------------------------------------------------- dates
def span(task):
    """(début, fin) de la tâche, ou None si elle n'est pas planifiée."""
    start, due = task.start_date, task.due_date
    if start is None and due is None:
        return None
    return (start or due, due or start)


def duration(task):
    start, due = span(task)
    return (due - start).days + 1


# ---------------------------------------------------------------- graphe
def would_cycle(task, new_dependencies):
    """Ajouter ces prédécesseurs à `task` créerait-il une boucle ?"""
    seen, stack = set(), list(new_dependencies)
    while stack:
        cur = stack.pop()
        if cur.pk == task.pk:
            return True
        if cur.pk in seen:
            continue
        seen.add(cur.pk)
        stack.extend(cur.dependencies.all())
    return False


def _nodes(tasks):
    """Tâches Django → nœuds du moteur : (id, terminée, début, fin, prérequis), dates en ordinaux."""
    out = []
    for t in tasks:
        sp = span(t)
        out.append((t.pk, t.status == "done", sp[0].toordinal() if sp else None,
                    sp[1].toordinal() if sp else None, [p.pk for p in t.dependencies.all()]))
    return out


def _loop_error():
    return ValidationError("Les dépendances forment une boucle.")


# ---------------------------------------------------------------- cascade
def cascade(task):
    """Repousse (sans jamais avancer) les tâches qui dépendent de `task` et ne peuvent plus commencer à leur
    date. Les tâches terminées ne bougent pas. Le calcul est fait par le moteur (Rust ou Python) sur l'état
    enregistré en base ; `task` doit donc avoir été sauvegardée. Retourne les ids déplacés."""
    tasks = list(Task.objects.filter(project_id=task.project_id).prefetch_related("dependencies"))
    shifts = engine.cascade_shifts(_nodes(tasks), task.pk)
    for pk, start, end in shifts:
        Task.objects.filter(pk=pk).update(start_date=date.fromordinal(start), due_date=date.fromordinal(end))
    return [pk for pk, _, _ in shifts]


def replan(project, today=None):
    """« Rattraper le retard » : les tâches non terminées dont l'échéance est passée redémarrent
    aujourd'hui (durée conservée) puis les dépendances sont propagées. Retourne les ids déplacés."""
    today = today or date.today()
    late = [t for t in project.tasks.exclude(status="done") if span(t) and span(t)[1] < today]
    moved = []
    for t in sorted(late, key=lambda t: span(t)[1]):
        t.refresh_from_db()  # une propagation précédente a pu déjà la repousser
        if span(t)[1] >= today:
            continue
        length = duration(t)
        t.start_date, t.due_date = today, today + timedelta(days=length - 1)
        t.save(update_fields=["start_date", "due_date"])
        moved.append(t.pk)
        moved.extend(cascade(t))
    return list(dict.fromkeys(moved))


# ---------------------------------------------------------------- analyse
def critical_path(tasks):
    """Chemin critique (CPM) sur les tâches non terminées : séquence de tâches dépendantes la plus
    longue — tout retard sur l'une d'elles décale la fin du projet. Retourne (ids, durée en jours)."""
    try:
        return engine.critical_path(_nodes(tasks))
    except ValueError:
        raise _loop_error()


def forecast_end(tasks, today):
    """Fin prévue du projet si rien ne change : une tâche en retard finit au mieux aujourd'hui, et ce
    décalage se propage aux tâches qui en dépendent."""
    try:
        end = engine.forecast_end(_nodes(tasks), today.toordinal())
    except ValueError:
        raise _loop_error()
    return date.fromordinal(end) if end is not None else None


def _peak_load(tasks):
    """Par membre : nombre maximal de tâches ouvertes simultanées."""
    per_user = defaultdict(lambda: defaultdict(int))
    for t in tasks:
        sp = span(t)
        if t.status == "done" or sp is None or t.assignee_id is None:
            continue
        for k in range(min((sp[1] - sp[0]).days + 1, 400)):
            per_user[t.assignee_id][sp[0] + timedelta(days=k)] += 1
    return {u: max(days.values()) for u, days in per_user.items()}


def _brief(task, today):
    sp = span(task)
    return {
        "id": task.pk, "title": task.title, "status": task.status,
        "start": sp[0] if sp else None, "due": sp[1] if sp else None,
        "days_late": max(0, (today - sp[1]).days) if sp and task.status != "done" else 0,
    }


def team_status(project, tasks, today):
    """Pour chaque membre : sur quoi il travaille, ce qui est en retard, ce qui arrive, et un statut global.
    Statuts : late (au moins une tâche en retard) > overloaded (trop de tâches en parallèle) > ok > free."""
    peaks = _peak_load(tasks)
    rows = []
    for m in project.membership_set.select_related("user").order_by("user__username"):
        mine = [t for t in tasks if t.assignee_id == m.user_id]
        open_ = [t for t in mine if t.status != "done"]
        late = [t for t in open_ if span(t) and span(t)[1] < today]
        current = [t for t in open_ if t not in late and (
            t.status == "doing" or (span(t) and span(t)[0] <= today <= span(t)[1]))]
        upcoming = sorted((t for t in open_ if span(t) and span(t)[0] > today), key=lambda t: (span(t)[0], t.pk))
        if late:
            state = "late"
        elif peaks.get(m.user_id, 0) >= OVERLOAD_THRESHOLD:
            state = "overloaded"
        elif not open_:
            state = "free"
        else:
            state = "ok"
        rows.append({
            "user_id": m.user_id, "username": m.user.username, "role": m.role, "state": state,
            "total": len(mine), "done": len(mine) - len(open_), "open": len(open_), "peak": peaks.get(m.user_id, 0),
            "late": [_brief(t, today) for t in sorted(late, key=lambda t: span(t)[1])],
            "current": [_brief(t, today) for t in current],
            "upcoming": [_brief(t, today) for t in upcoming[:3]],
            "unscheduled": sum(1 for t in open_ if not span(t)),
        })
    order = {"late": 0, "overloaded": 1, "ok": 2, "free": 3}
    rows.sort(key=lambda r: (order[r["state"]], r["username"]))
    return rows


def _local_day(moment):
    return timezone.localtime(moment).date()


def stats(tasks, today, days=30):
    """Données de graphiques : répartition, courbe créées/terminées sur `days` jours, vélocité, échéances."""
    done = [t for t in tasks if t.status == "done"]
    done_days = [_local_day(t.completed_at) for t in done if t.completed_at]
    created_days = [_local_day(t.created_at) for t in tasks]
    series = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        series.append({"date": d, "created": sum(1 for x in created_days if x <= d),
                       "done": sum(1 for x in done_days if x <= d)})
    in_range = lambda x, a, b: today - timedelta(days=a) <= x <= today - timedelta(days=b)
    open_tasks = [t for t in tasks if t.status != "done"]
    recent = sorted((t for t in done if t.completed_at), key=lambda t: t.completed_at, reverse=True)[:5]
    due_soon = sorted((t for t in open_tasks if span(t) and today <= span(t)[1] <= today + timedelta(days=7)),
                      key=lambda t: (span(t)[1], t.pk))
    return {
        "status_counts": {k: sum(1 for t in tasks if t.status == k) for k in ("todo", "doing", "done")},
        "priority_counts": {str(k): sum(1 for t in open_tasks if t.priority == k) for k in (1, 2, 3)},
        "burnup": series,
        "velocity": {"this_week": sum(1 for x in done_days if in_range(x, 6, 0)),
                     "last_week": sum(1 for x in done_days if in_range(x, 13, 7))},
        "recent_done": [{"id": t.pk, "title": t.title, "who": t.assignee.username if t.assignee else None,
                         "at": t.completed_at} for t in recent],
        "due_soon": [{**_brief(t, today), "who": t.assignee.username if t.assignee else None} for t in due_soon[:8]],
    }


def health(ins):
    """Santé d'un projet : done / empty / late (fin prévue après l'échéance) / risk / ok."""
    if ins["total"] == 0:
        return "empty"
    if ins["done"] == ins["total"]:
        return "done"
    if (ins["slip_days"] or 0) > 0:
        return "late"
    if ins["late_count"] or any(r["severity"] in ("high", "medium") for r in ins["risks"]):
        return "risk"
    return "ok"


def user_dashboard(user, today=None):
    """Tableau de bord personnel : ce qui me concerne dans tous mes projets."""
    from projects.models import Membership, Project

    from .models import Task

    today = today or date.today()
    projects = list(Project.objects.filter(membership__user=user).distinct().order_by("name"))
    roles = dict(Membership.objects.filter(user=user).values_list("project_id", "role"))
    mine = list(Task.objects.filter(project__in=projects, assignee=user).exclude(status="done").select_related("project"))

    def brief(t):
        return {**_brief(t, today), "project_id": t.project_id, "project": t.project.name}

    late = sorted((t for t in mine if span(t) and span(t)[1] < today), key=lambda t: span(t)[1])
    active = [t for t in mine if t not in late and (t.status == "doing" or (span(t) and span(t)[0] <= today <= span(t)[1]))]
    week = [{"date": today + timedelta(days=i),
             "tasks": [brief(t) for t in mine if span(t) and span(t)[1] == today + timedelta(days=i)]} for i in range(7)]
    upcoming_n = sum(1 for t in mine if t not in late and t not in active
                     and span(t) and today < span(t)[1] <= today + timedelta(days=6))

    cards, alerts = [], []
    for p in projects:
        ins = insights(p, today)
        cards.append({
            "id": p.pk, "name": p.name, "role": roles.get(p.pk), "health": health(ins), "progress": ins["progress"],
            "total": ins["total"], "done": ins["done"], "late_count": ins["late_count"],
            "forecast_end": ins["forecast_end"], "deadline": ins["deadline"], "slip_days": ins["slip_days"],
            "members": len(ins["team"]), "my_open": sum(1 for t in mine if t.project_id == p.pk),
            "team_late": sum(1 for m in ins["team"] if m["state"] == "late"),
        })
        for m in ins["team"]:
            if m["state"] == "late" and m["user_id"] != user.pk:
                worst = max(m["late"], key=lambda t: t["days_late"])
                alerts.append({"project_id": p.pk, "project": p.name, "user": m["username"], "task": worst["id"],
                               "title": worst["title"], "days_late": worst["days_late"], "count": len(m["late"])})
    alerts.sort(key=lambda a: -a["days_late"])

    mine_done = Task.objects.filter(assignee=user, project__in=projects, status="done", completed_at__isnull=False)
    done_days = [_local_day(t.completed_at) for t in mine_done]
    done_series = [{"date": today - timedelta(days=i), "count": sum(1 for x in done_days if x == today - timedelta(days=i))}
                   for i in range(13, -1, -1)]
    return {
        "kpis": {
            "today": len(active), "late": len(late), "upcoming": upcoming_n,
            "unscheduled": sum(1 for t in mine if not span(t)),
            "done_this_week": sum(1 for x in done_days if today - timedelta(days=6) <= x <= today),
            "done_last_week": sum(1 for x in done_days if today - timedelta(days=13) <= x <= today - timedelta(days=7)),
        },
        "focus": [brief(t) for t in late + active][:12],
        "week": week,
        "projects": cards,
        "alerts": alerts[:6],
        "done_series": done_series,
    }


def insights(project, today=None):
    today = today or date.today()
    tasks = list(project.tasks.select_related("assignee").prefetch_related("dependencies"))
    open_tasks = [t for t in tasks if t.status != "done"]

    weight = lambda t: duration(t) if span(t) else 1
    total_w = sum(weight(t) for t in tasks)
    done_w = sum(weight(t) for t in tasks if t.status == "done")
    spans = [span(t) for t in tasks if span(t)]
    planned_end = max((s[1] for s in spans), default=None)
    forecast = forecast_end(tasks, today)
    reference = project.deadline or planned_end
    slip = (forecast - reference).days if forecast and reference else None

    crit_ids, crit_days = critical_path(tasks)
    risks = []
    for t in open_tasks:
        sp = span(t)
        if sp and sp[1] < today:
            risks.append({"type": "late", "severity": "high", "task": t.pk,
                          "message": f"« {t.title} » devait finir il y a {(today - sp[1]).days} j."})
        late_preds = [p for p in t.dependencies.all() if p.status != "done" and span(p) and span(p)[1] < today]
        if late_preds and not (sp and sp[1] < today):
            risks.append({"type": "blocked", "severity": "medium", "task": t.pk,
                          "message": f"« {t.title} » est menacée : « {late_preds[0].title} » est en retard."})
        if sp and t.assignee_id is None and sp[0] <= today + timedelta(days=SOON_DAYS):
            risks.append({"type": "unassigned", "severity": "low", "task": t.pk,
                          "message": f"« {t.title} » démarre bientôt et n'a pas de responsable."})
    peaks = _peak_load(tasks)
    members = {m.user_id: m.user.username for m in project.membership_set.select_related("user")}
    workload = []
    for uid, name in sorted(members.items(), key=lambda x: x[1]):
        workload.append({"user_id": uid, "username": name, "peak": peaks.get(uid, 0),
                         "open": sum(1 for t in open_tasks if t.assignee_id == uid)})
        if peaks.get(uid, 0) >= OVERLOAD_THRESHOLD:
            risks.append({"type": "overload", "severity": "medium", "task": None,
                          "message": f"{name} a jusqu'à {peaks[uid]} tâches en parallèle."})
    if project.deadline and forecast and forecast > project.deadline:
        risks.append({"type": "deadline", "severity": "high", "task": None,
                      "message": f"La fin prévue ({forecast:%d/%m/%Y}) dépasse l'échéance du projet ({project.deadline:%d/%m/%Y})."})
    order = {"high": 0, "medium": 1, "low": 2}
    risks.sort(key=lambda r: order[r["severity"]])

    return {
        "total": len(tasks),
        "done": len(tasks) - len(open_tasks),
        "progress": round(100 * done_w / total_w) if total_w else 0,
        "planned_end": planned_end,
        "deadline": project.deadline,
        "forecast_end": forecast,
        "slip_days": slip,
        "late_count": sum(1 for r in risks if r["type"] == "late"),
        "critical_path": {"task_ids": crit_ids, "duration_days": crit_days},
        "risks": risks,
        "workload": workload,
        "team": team_status(project, tasks, today),
        "stats": stats(tasks, today),
        "unassigned": {
            "open": sum(1 for t in open_tasks if t.assignee_id is None),
            "late": sum(1 for t in open_tasks if t.assignee_id is None and span(t) and span(t)[1] < today),
        },
    }
