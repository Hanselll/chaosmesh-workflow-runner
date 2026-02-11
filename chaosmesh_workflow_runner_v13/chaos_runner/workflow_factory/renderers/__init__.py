# -*- coding: utf-8 -*-

RENDERERS = {}

def register(name):
    def deco(fn):
        RENDERERS[name]=fn
        return fn
    return deco

def get(name):
    if name not in RENDERERS:
        raise RuntimeError("Unknown renderer: {} (available={})".format(name, sorted(RENDERERS.keys())))
    return RENDERERS[name]
from .network_then_parallel_podkill import *
from . import network_parallel_containerkill
