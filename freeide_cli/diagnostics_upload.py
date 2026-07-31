"""Diagnostics-upload client (removed).

This module previously hosted the opt-in ``freeide debug share`` destination
that uploaded gzipped debug bundles to the managed Portal account service.
That commercial destination has been removed; ``freeide debug share`` now only
targets the public paste path (and ``--local``). The module is kept as an
importable stub so any lingering ``import`` does not break the build.
"""
