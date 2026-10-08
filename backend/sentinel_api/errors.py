class APIError(Exception):
    def __init__(self, status, message, code="request_error"):
        super().__init__(message)
        self.status, self.code = status, code
