class AuthError(Exception):
    def __init__(self, message: str) -> 'AuthError':
        self.message = message
