# -*- coding: utf-8 -*-
"""Llista de temes per cares. Es pot importar d'un projecte de VinylTracklist (.vtracklist)."""
import itertools
import json
import os
import re
import unicodedata

from .wavinfo import read_wav_info

WAV_EXTS = (".wav", ".wave", ".bwf")
_ids = itertools.count(1)
_PREFIX_RE = re.compile(r"^\s*(?:[A-Da-d]\s?\d{1,2}|\d{1,3})(?:\s*[-.)]\s*|\s+)+")


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def filename_key(path):
    name = unicodedata.normalize("NFKD", os.path.basename(path))
    name = "".join(c for c in name if not unicodedata.combining(c))
    return natural_key(name)


def title_from_filename(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    s = stem.replace("_", " ")
    s2 = _PREFIX_RE.sub("", s, count=1)
    s2 = re.sub(r"\s+", " ", s2).strip(" -")
    return s2 or stem


class TrackItem(object):
    def __init__(self, path, title=None):
        self.id = next(_ids)
        self.path = path
        self.title = title or title_from_filename(path)
        self.header = read_wav_info(path)

    @property
    def duration(self):
        return self.header.duration if self.header.ok else 0.0


class Project(object):
    def __init__(self):
        self.sides = {"A": [], "B": []}
        self.artist = ""
        self.album = ""
        self.source = ""   # projecte .vtracklist d'origen, si n'hi ha

    def names(self):
        return sorted(self.sides.keys())

    def all(self):
        for name in self.names():
            for i, t in enumerate(self.sides[name]):
                yield name, i, t

    def is_empty(self):
        return not any(self.sides.values())

    def add_files(self, side, paths):
        self.sides[side].extend(TrackItem(p) for p in paths)
        self.sides[side].sort(key=lambda t: filename_key(t.path))

    def locate(self, tid):
        for name in self.names():
            for i, t in enumerate(self.sides[name]):
                if t.id == tid:
                    return name, i
        return None, -1

    def shift(self, tid, delta):
        name, i = self.locate(tid)
        if name is None:
            return
        j = i + delta
        lst = self.sides[name]
        if 0 <= j < len(lst):
            lst[i], lst[j] = lst[j], lst[i]

    def move_other(self, tid):
        name, i = self.locate(tid)
        if name is None:
            return
        t = self.sides[name].pop(i)
        self.sides["B" if name == "A" else "A"].append(t)

    def remove(self, tid):
        name, i = self.locate(tid)
        if name is not None:
            del self.sides[name][i]

    def clear(self):
        self.sides = {"A": [], "B": []}
        self.artist = self.album = self.source = ""


def import_vtracklist(path):
    """Llegeix un projecte de VinylTracklist i en retorna un Project amb l'ordre de cares."""
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    if d.get("app") not in ("VinylTracklist", "VinylPrep"):
        raise ValueError("No és un projecte de VinylTracklist")
    base = os.path.dirname(os.path.abspath(path))
    p = Project()
    p.artist = d.get("artist", "")
    p.album = d.get("album", "")
    p.source = path
    for sd in d.get("sides", []):
        name = sd.get("name", "A")
        if name not in p.sides:
            p.sides[name] = []
        for item in sd.get("tracks", []):
            fp = item.get("path", "")
            rel = item.get("relpath")
            if not os.path.exists(fp) and rel:
                cand = os.path.normpath(os.path.join(base, rel))
                if os.path.exists(cand):
                    fp = cand
            p.sides[name].append(TrackItem(fp, item.get("title")))
    return p
