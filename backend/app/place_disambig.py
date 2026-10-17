"""Deterministic place disambiguation for the navigation chat.

"明远楼" matches five different teaching buildings and nothing in the sentence
says which one. Left alone the language model picks one, and the resulting route
looks plausible while being wrong, so ambiguity is answered from the catalog
here instead of being delegated to the model.

Three cases are handled:
  - a family stem named without its distinguishing part (明远楼 -> A~E栋);
  - names that legitimately repeat at different spots (瑞幸咖啡 x3);
  - duplicate survey nodes of one gate, which must not become a question.
"""
import math
import re

from .place_search import normalize
from .trip_planner import distance

# The shortest stem that still identifies a building family; one character
# collides with ordinary words.
STEM = 2
# Two entries with the same name this close are one physical place, usually a
# duplicated OSM node for a gate.
SAME_PLACE = 80
NUMBER = {'一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
          '六': '6', '七': '7', '八': '8', '九': '9', '十': '10'}
WEST_EAST = ('偏西', '偏东')
SOUTH_NORTH = ('偏南', '偏北')
MIDDLE = ('偏西', '居中', '偏东'), ('偏南', '居中', '偏北')


def terms(item):
    """Normalized names and aliases with empty strings dropped."""
    out = {normalize(item['name'])}
    out.update(normalize(alias) for alias in (item.get('aliases') or []))
    out.discard('')
    return out


def _distinct(group):
    """Collapse duplicate survey nodes of the same physical place."""
    kept = []
    for item in group:
        if not any(item['name'] == seen['name'] and distance(item, seen) < SAME_PLACE for seen in kept):
            kept.append(item)
    return kept


def families(items):
    """Groups sharing both a two-character stem and a location type."""
    groups = {}
    for item in items:
        name = normalize(item['name'])
        if len(name) >= STEM:
            groups.setdefault((item.get('location_type'), name[:STEM]), []).append(item)
    return [kept for kept in (_distinct(group) for group in groups.values()) if len(kept) > 1]


def discriminating(item, group):
    """Terms only this member owns, so saying one of them picks it out."""
    others = set()
    for member in group:
        if member is not item:
            others |= terms(member)
    return terms(item) - others


def _common_prefix(names):
    prefix = names[0]
    for name in names[1:]:
        while prefix and not name.startswith(prefix):
            prefix = prefix[:-1]
    return prefix


def _order(name):
    """Chinese numerals first, then zero-padded digits so 7 sorts before 10."""
    name = ''.join(NUMBER.get(char, char) for char in name)
    return re.sub(r'\d+', lambda match: match.group().zfill(3), name)


def _shadowed(stem, heard, items, group):
    """A longer catalog name starting with this stem resolves the mention elsewhere.

    Without this, "滋兰苑餐厅" would be treated as a mention of the 滋兰 parking
    family, because its name happens to start with the same two characters.
    """
    members = {id(item) for item in group}
    for item in items:
        if id(item) in members:
            continue
        if any(len(term) > len(stem) and term.startswith(stem) and term in heard for term in terms(item)):
            return True
    return False


def _marks(group):
    """Position labels that stay distinct; rank along the widest axis."""
    longitudes = [item['longitude'] for item in group]
    latitudes = [item['latitude'] for item in group]
    east_west = (max(longitudes) - min(longitudes)) * math.cos(math.radians(sum(latitudes) / len(latitudes)))
    north_south = max(latitudes) - min(latitudes)
    if east_west >= north_south:
        ordered = sorted(group, key=lambda item: item['longitude'])
        sides = WEST_EAST if len(group) == 2 else MIDDLE[0]
    else:
        ordered = sorted(group, key=lambda item: item['latitude'])
        sides = SOUTH_NORTH if len(group) == 2 else MIDDLE[1]
    return [f'{item["name"]}（{sides[min(index, len(sides) - 1)]}）' for index, item in enumerate(ordered)]


def _ask(group, items):
    group = sorted(group, key=lambda item: _order(item['name']))
    prefix = _common_prefix([item['name'] for item in group])
    labels = [item['name'][len(prefix):] for item in group]
    if all(labels) and len(set(labels)) == len(group):
        listed = '、'.join(labels[:8]) + ('等' if len(labels) > 8 else '')
        return f'{prefix}有{len(group)}个可选位置：{listed}。你要去哪里？'
    return f'校园里有{len(group)}个同名地点：{"、".join(_marks(group))}。你要去哪一个？'


def clarify(text, items, item=None):
    """A question when the sentence leaves the place open, otherwise ''.

    `item` is the catalog entry the model already chose. When given, only that
    entry's family is judged, and a place with a unique name never asks.
    """
    heard = normalize(text)
    groups = families(items)
    if item is None:
        for group in groups:
            stem = normalize(group[0]['name'])[:STEM]
            if stem not in heard or _shadowed(stem, heard, items, group):
                continue
            if any(any(term in heard for term in discriminating(member, group)) for member in group):
                continue
            return _ask(group, items)
        return ''
    for group in groups:
        if not any(item is member for member in group):
            continue
        if normalize(item['name'])[:STEM] not in heard:
            # The model probably resolved an alias; nothing to judge on.
            return ''
        if any(term in heard for term in discriminating(item, group)):
            return ''
        return _ask(group, items)
    return ''
