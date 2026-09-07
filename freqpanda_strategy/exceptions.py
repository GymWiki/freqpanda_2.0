class StrategyValidationError(ValueError):
    """Raised when a strategy definition fails semantic validation.

    Pydantic already rejects structurally invalid definitions (wrong types,
    missing required fields, ...). This error is for validation that needs
    knowledge of the indicator registry, e.g. "unknown indicator name" or
    "condition references a column that no indicator produces".
    """
