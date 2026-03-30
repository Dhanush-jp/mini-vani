from typing import Any, Optional, Type, TypeVar
from fastapi import HTTPException, status
from loguru import logger
from schemas.api_response import StandardResponse

T = TypeVar("T")

def success_response(data: Any = None, message: str = "Operation successful") -> StandardResponse:
    return StandardResponse(success=True, message=message, data=data)

def error_response(message: str, errors: list = None, status_code: int = status.HTTP_400_BAD_REQUEST):
    raise HTTPException(status_code=status_code, detail=message) # The global handler will wrap this
