class VIRBaseError(Exception):
    def __init__(self, error_code: str, message: str, http_status: int = 500):
        self.error_code = error_code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


class MissingIdentifierError(VIRBaseError):
    def __init__(self):
        super().__init__("VIR-ERR-001", "At least one identifier must be provided", 400)


class InvalidRegistrationFormatError(VIRBaseError):
    def __init__(self, detail: str = ""):
        super().__init__("VIR-ERR-002", f"Invalid registration format. {detail}".strip(), 422)


class InvalidVINFormatError(VIRBaseError):
    def __init__(self, detail: str = ""):
        super().__init__("VIR-ERR-003", f"Invalid VIN format. {detail}".strip(), 422)


class UnsupportedCountryError(VIRBaseError):
    def __init__(self, country: str = ""):
        super().__init__("VIR-ERR-004", f"Unsupported country: {country}".strip(), 422)


class ProviderUnavailableError(VIRBaseError):
    def __init__(self):
        super().__init__("VIR-ERR-005", "Provider unavailable", 503)


class ProviderRateLimitedError(VIRBaseError):
    def __init__(self):
        super().__init__("VIR-ERR-006", "Provider rate limited", 429)


class AmbiguousVehicleIdentityError(VIRBaseError):
    def __init__(self):
        super().__init__("VIR-ERR-007", "Several vehicle configurations match the supplied information", 409)


class ContradictoryVehicleIdentityError(VIRBaseError):
    def __init__(self):
        super().__init__("VIR-ERR-008", "Conflicting vehicle identity data detected", 409)


class ExternalLookupNotAuthorizedError(VIRBaseError):
    def __init__(self):
        super().__init__("VIR-ERR-009", "External lookup not authorized", 403)
