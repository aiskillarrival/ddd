"""Application layer.

Orchestrates use cases. It depends only on the domain layer and on
abstract ports (interfaces). It knows nothing about SQLite, HTTP or any
other infrastructure concern. Infrastructure is *injected* in.
"""
