"""User-facing errors must describe the failure without echoing input values."""


class HarnessSyncError(Exception):
    exit_code = 2


class UnsupportedError(HarnessSyncError):
    exit_code = 3


class ConflictError(HarnessSyncError):
    exit_code = 4


class TransactionError(HarnessSyncError):
    exit_code = 5
