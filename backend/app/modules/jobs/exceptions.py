"""Job-specific exception hierarchy.

Handlers raise these to communicate failure semantics to the runner:
- RetryableError  → schedule retry with exponential backoff
- NonRetryableError → mark job FAILED immediately
"""


class JobError(Exception):
    """Base exception for job processing errors."""


class RetryableError(JobError):
    """Transient failure: network timeout, rate limit, 5xx upstream.

    The runner will schedule a retry with exponential backoff
    unless max attempts are exhausted.
    """


class NonRetryableError(JobError):
    """Fatal failure: corrupt file, schema violation, unsupported type.

    The runner will immediately mark the job as FAILED.
    """

