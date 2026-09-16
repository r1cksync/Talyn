"""Fixed, non-sensitive messages that may be shown in the product and logs."""

MESSAGES = {
    "model_input_too_large": "Interview material exceeds the AI size limit. Use shorter documents or contact support.",
    "model_budget_exhausted": "AI request allowance exhausted. Contact support to review failed attempts before retrying.",
}


class WorkflowError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(MESSAGES[code])


def retryable_error(error: Exception) -> bool:
    return not isinstance(error, WorkflowError) or error.retryable


def public_job_error(error: Exception) -> str:
    if isinstance(error, WorkflowError):
        return MESSAGES[error.code]
    return "Task failed. Retry the task; contact support if the error continues."
