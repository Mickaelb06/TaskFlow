"""Modèles de projet : quatre modèles fournis + les modèles enregistrés par l'utilisateur.

Une tâche de modèle : {ref, title, description, priority, offset, duration, depends_on: [ref], milestone, recurrence}.
`offset` = jours après le démarrage (en jours ouvrés si le modèle l'est), `duration` en jours (≥ 1), None = sans date.
"""
from datetime import date, timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from tasks import workdays as wd
from tasks.models import Task

from .models import Project, ProjectTemplate
from .services import create_project, get_role, Membership

MAX_TEMPLATES = 20
MAX_TASKS = 80


def _t(ref, title, offset, duration, deps=(), priority=2, milestone=False, description=""):
    return {"ref": ref, "title": title, "description": description, "priority": priority, "offset": offset,
            "duration": duration, "depends_on": list(deps), "milestone": milestone, "recurrence": ""}


BUILTIN = {
    "site-web": {
        "name": "Site web", "description": "Du cadrage à la mise en ligne.", "skip_weekends": True,
        "tasks": [
            _t("a", "Cadrage et besoins", 0, 3, priority=1), _t("b", "Maquettes", 3, 5, ["a"], 1), _t("c", "Charte graphique", 3, 3, ["a"]),
            _t("d", "Collecte des contenus", 3, 8, ["a"], 3), _t("e", "Intégration des pages", 11, 8, ["b", "c", "d"], 1),
            _t("f", "Mentions légales et RGPD", 8, 2, ["a"], 2), _t("g", "Recette", 19, 3, ["e", "f"], 1),
            _t("h", "Mise en ligne", 22, 1, ["g"], 1, True),
        ]},
    "evenement": {
        "name": "Organiser un événement", "description": "Lieu, intervenants, communication, jour J, bilan.", "skip_weekends": False,
        "tasks": [
            _t("a", "Définir le format et le budget", 0, 4, priority=1), _t("b", "Réserver le lieu", 4, 5, ["a"], 1),
            _t("c", "Inviter les intervenants", 4, 7, ["a"]), _t("d", "Plan de communication", 6, 6, ["a"], 2),
            _t("e", "Ouverture de la billetterie", 12, 1, ["b", "d"], 1, True), _t("f", "Logistique (matériel, traiteur)", 11, 12, ["b", "c"], 2),
            _t("g", "Répétition générale", 28, 1, ["f"], 2), _t("h", "Jour J", 30, 1, ["g", "e"], 1, True), _t("i", "Bilan et remerciements", 31, 5, ["h"], 3),
        ]},
    "sprint": {
        "name": "Sprint de 2 semaines", "description": "Planification, développement, revue, rétrospective.", "skip_weekends": True,
        "tasks": [
            _t("a", "Planification du sprint", 0, 1, priority=1), _t("b", "Développement — lot 1", 1, 4, ["a"], 1),
            _t("c", "Développement — lot 2", 5, 4, ["b"], 1), _t("d", "Tests et corrections", 9, 1, ["c"], 1),
            _t("e", "Revue de sprint", 9, 1, ["c"], 2, True), _t("f", "Rétrospective", 10, 1, ["e"], 3),
        ]},
    "lancement": {
        "name": "Lancement de produit", "description": "Préparer, communiquer, lancer, mesurer.", "skip_weekends": True,
        "tasks": [
            _t("a", "Positionnement et message", 0, 4, priority=1), _t("b", "Page produit", 4, 6, ["a"], 1),
            _t("c", "Contenus (vidéo, articles)", 4, 8, ["a"]), _t("d", "Campagne e-mail", 12, 4, ["b", "c"], 2),
            _t("e", "Tests finaux", 12, 3, ["b"], 1), _t("f", "Lancement", 16, 1, ["d", "e"], 1, True),
            _t("g", "Suivi des premiers retours", 17, 5, ["f"], 2), _t("h", "Bilan à 30 jours", 40, 2, ["g"], 3),
        ]},
}


def catalog(user):
    """Modèles proposés à `user` : fournis d'abord, puis les siens."""
    out = [{"key": f"builtin:{k}", "name": v["name"], "description": v["description"], "builtin": True,
            "tasks": len(v["tasks"]), "skip_weekends": v["skip_weekends"]} for k, v in BUILTIN.items()]
    out += [{"key": str(t.pk), "name": t.name, "description": t.description, "builtin": False,
             "tasks": len(t.tasks), "skip_weekends": t.skip_weekends} for t in ProjectTemplate.objects.filter(owner=user)]
    return out


def _resolve(user, key):
    key = str(key or "")
    if key.startswith("builtin:"):
        tpl = BUILTIN.get(key.split(":", 1)[1])
        if tpl is None:
            raise ValidationError("Modèle introuvable.")
        return tpl["name"], tpl["description"], tpl["skip_weekends"], tpl["tasks"]
    tpl = ProjectTemplate.objects.filter(pk=key if key.isdigit() else 0, owner=user).first()
    if tpl is None:
        raise ValidationError("Modèle introuvable.")  # même message qu'un modèle d'un autre utilisateur : on ne révèle rien
    return tpl.name, tpl.description, tpl.skip_weekends, tpl.tasks


@transaction.atomic
def create_from_template(user, key, name=None, start=None, description=None):
    """Crée un projet (dont `user` est propriétaire) avec les tâches, dates et dépendances du modèle."""
    tpl_name, tpl_desc, workdays, tasks = _resolve(user, key)
    start = start or date.today()
    project = create_project(user, (name or tpl_name)[:150], tpl_desc if description is None else description)
    project.skip_weekends = workdays
    project.save(update_fields=["skip_weekends"])
    base = wd.to_index(start) if workdays else start.toordinal()
    created = {}
    for t in tasks:
        a = b = None
        if t.get("offset") is not None:
            first, last = base + t["offset"], base + t["offset"] + max(1, t.get("duration") or 1) - 1
            a, b = (wd.from_index(first), wd.from_index(last)) if workdays else (date.fromordinal(first), date.fromordinal(last))
        created[t["ref"]] = Task.objects.create(
            project=project, title=t["title"][:200], description=t.get("description", ""), priority=t.get("priority", 2),
            start_date=a, due_date=b, is_milestone=bool(t.get("milestone")), recurrence=t.get("recurrence", ""))
    for t in tasks:
        deps = [created[r] for r in t.get("depends_on", []) if r in created]
        if deps:
            created[t["ref"]].dependencies.set(deps)
    return project


@transaction.atomic
def save_as_template(user, project, name, description=""):
    """Enregistre la structure d'un projet (tâches, durées, dépendances, décalages) ; réservé au propriétaire."""
    if get_role(user, project) != Membership.Role.OWNER:
        raise PermissionDenied("Réservé au propriétaire du projet.")
    name = (name or "").strip()
    if not name:
        raise ValidationError("Donnez un nom au modèle.")
    if ProjectTemplate.objects.filter(owner=user).count() >= MAX_TEMPLATES:
        raise ValidationError(f"{MAX_TEMPLATES} modèles au plus : supprimez-en un d'abord.")
    tasks = list(project.tasks.prefetch_related("dependencies").order_by("id"))
    if not tasks:
        raise ValidationError("Le projet n'a aucune tâche.")
    if len(tasks) > MAX_TASKS:
        raise ValidationError(f"Un modèle contient {MAX_TASKS} tâches au plus.")
    workdays = project.skip_weekends
    enc = wd.to_index if workdays else date.toordinal
    dated = [t for t in tasks if t.start_date or t.due_date]
    origin = min((enc(t.start_date or t.due_date) for t in dated), default=0)
    ref = {t.pk: f"t{i}" for i, t in enumerate(tasks)}
    out = []
    for t in tasks:
        a, b = t.start_date or t.due_date, t.due_date or t.start_date
        out.append({"ref": ref[t.pk], "title": t.title, "description": t.description, "priority": t.priority,
                    "offset": enc(a) - origin if a else None, "duration": (enc(b) - enc(a) + 1) if a else None,
                    "depends_on": [ref[d.pk] for d in t.dependencies.all() if d.pk in ref], "milestone": t.is_milestone,
                    "recurrence": t.recurrence})
    return ProjectTemplate.objects.create(owner=user, name=name[:120], description=description or project.description,
                                          skip_weekends=workdays, tasks=out)


def delete_template(user, template):
    if template.owner_id != user.pk:
        raise PermissionDenied("Ce modèle n'est pas le vôtre.")
    template.delete()
