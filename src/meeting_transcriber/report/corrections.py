"""名词纠错：错词=正确词映射全文替换（E-3）。

条目格式：单个字符串可含多条映射，逗号分隔（"错1=正1,错2=正2"）；
非法条目（缺 "=" 或空错词）跳过，不中断后续有效映射。
"""
from __future__ import annotations


def apply_corrections(text: str, corrections: list[str]) -> str:
    """按 corrections 映射对 text 做全文替换。"""
    for entry in corrections:
        for pair in str(entry).split(","):
            if "=" not in pair:
                continue  # 非法条目：跳过不中断
            wrong, right = pair.split("=", 1)
            wrong, right = wrong.strip(), right.strip()
            if not wrong:
                continue
            text = text.replace(wrong, right)
    return text
