"""
Global error handling middleware.
Catches unhandled exceptions and returns consistent JSON error responses.
"""

from fastapi import Request
from fastapi.responses import JSONResponse


# TODO: register_error_handlers(app) -> attach exception handlers to the FastAPI app
# TODO: handle generic Exception -> 500 with {"detail": "Internal server error"}
# TODO: handle ValueError -> 400 with {"detail": str(e)}
