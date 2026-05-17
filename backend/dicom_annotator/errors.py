from fastapi import HTTPException


class ApiError(HTTPException):
    def __init__(self, status_code: int, error: str, message: str, **details):
        super().__init__(
            status_code=status_code,
            detail={"error": error, "message": message, "details": details},
        )


def case_not_found(case_id: str) -> ApiError:
    return ApiError(404, "case_not_found", f"No case with id {case_id!r}", case_id=case_id)


def label_unknown(label_id: int | str) -> ApiError:
    return ApiError(404, "label_unknown", f"No label with id {label_id!r}", label_id=label_id)


def shape_mismatch(expected: tuple, got: tuple) -> ApiError:
    return ApiError(422, "shape_mismatch", "Mask shape does not match reference geometry",
                    expected=list(expected), got=list(got))


def invalid_envelope(message: str) -> ApiError:
    return ApiError(422, "invalid_envelope", message)


def invalid_project(message: str) -> ApiError:
    return ApiError(400, "invalid_project", message)


def geometry_error(message: str) -> ApiError:
    return ApiError(500, "geometry_error", message)
