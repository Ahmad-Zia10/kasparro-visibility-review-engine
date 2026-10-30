from typing import Annotated

from fastapi import Depends, Header

from app.config import Identity, settings
from app.errors import Forbidden, Unauthenticated


def current_identity(authorization: Annotated[str | None, Header()] = None) -> Identity:
    token = (authorization or "").removeprefix("Bearer ")
    identity = settings.identities().get(token)
    if identity is None:
        raise Unauthenticated("missing or unknown bearer token")
    return identity


def require_analyst(identity: Annotated[Identity, Depends(current_identity)]) -> Identity:
    if identity.role != "analyst":
        raise Forbidden("analyst role required")
    return identity


def require_reviewer(identity: Annotated[Identity, Depends(current_identity)]) -> Identity:
    if identity.role != "reviewer":
        raise Forbidden("reviewer role required")
    return identity


Analyst = Annotated[Identity, Depends(require_analyst)]
Reviewer = Annotated[Identity, Depends(require_reviewer)]
