"""The WhatsApp extension router: routes that exist only on WhatsApp.

Text and media limits, the contact and coordinate validators, Template info
and ``/health`` sit behind one router whose dependency, ``whatsapp_only``,
answers 501 under any other Platform's path. Every route that serves more than
one Platform lives one level up in ``wappa/api/routes/`` and gates on a
capability instead. Media info and delete are ``IMediaLibrary`` methods, so
they are shared routes, not extension routes.
"""

from fastapi import APIRouter, Depends

from wappa.api.dependencies.whatsapp_dependencies import whatsapp_only

from .health import router as _health_router
from .limits import router as _limits_router
from .template_info import router as _template_info_router
from .validators import router as _validators_router

whatsapp_extension_router = APIRouter(dependencies=[Depends(whatsapp_only)])
whatsapp_extension_router.include_router(_health_router)
whatsapp_extension_router.include_router(_limits_router)
whatsapp_extension_router.include_router(_validators_router)
whatsapp_extension_router.include_router(_template_info_router)

__all__ = ["whatsapp_extension_router"]
