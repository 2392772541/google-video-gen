"""Pure Flow failure predicates shared by the worker, scheduler and task UI."""
from __future__ import annotations

FLOW_RESPONSE_UNREADABLE = "FLOW_RESPONSE_UNREADABLE"
FLOW_RESPONSE_UNREADABLE_MESSAGE = (
    "Flow 返回记录无法解析；任务可能仍在云端运行或已完成，且可能已扣额度。"
    "请先在原 Flow 项目核对或取回结果，勿直接重新生成。已停止自动重试，不切换账号。"
)


def is_flow_response_unreadable(
    error_code: str | None, error_message: str | None = "", logs: str | None = ""
) -> bool:
    """Recognize this post-submit failure, including old saved classifications.

    WireFormatError also protects outgoing frame constraints; do not classify
    those pre-network guards as accepted generations merely from the exit code.
    """
    code = (error_code or "").upper()
    if code == FLOW_RESPONSE_UNREADABLE:
        return True
    if code not in {"EXIT_7", "WIRE_FORMAT_MISMATCH", "WIREFORMATERROR"}:
        return False
    return "no generation record" in f"{error_message or ''} {logs or ''}".lower()
