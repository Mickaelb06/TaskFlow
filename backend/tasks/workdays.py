"""Jours ouvrés (lundi → vendredi) sans toucher au moteur de calcul.

Astuce : le moteur compte en entiers. On lui donne des *numéros de jour ouvré* au lieu de dates calendaires : le
vendredi est le n° 4, le lundi suivant le n° 5. « Le lendemain de la fin » (fin + 1) devient alors naturellement le
prochain jour ouvré, une durée de 3 jours est 3 jours ouvrés, et le week-end ne compte jamais. Un samedi ou un
dimanche prend le numéro du lundi suivant. Les résultats du moteur sont reconvertis en dates.
"""
from datetime import date


def to_index(day):
    """Date → numéro de jour ouvré (samedi et dimanche : celui du lundi suivant)."""
    week, weekday = divmod(day.toordinal() - 1, 7)  # le 1er janvier de l'an 1 est un lundi
    return week * 5 + min(weekday, 5)


def from_index(n):
    """Numéro de jour ouvré → date (toujours un jour de semaine)."""
    week, r = divmod(n, 5)
    return date.fromordinal(week * 7 + r + 1)


def is_weekend(day):
    return day.weekday() >= 5


def next_workday(day):
    return from_index(to_index(day))


def add_workdays(day, n):
    """`day` décalée de `n` jours ouvrés (n peut être négatif)."""
    return from_index(to_index(day) + n)
