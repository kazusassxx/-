"""pytest 全局配置：
- 确保 src 可导入（与 pyproject.toml 的 pythonpath 双保险）
- Windows 上 %TEMP% 目录权限受限，把 pytest 临时目录改到项目内
"""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def pytest_configure(config):
    base = Path(__file__).resolve().parent.parent / ".pytest_tmp"
    config.option.basetemp = str(base)
