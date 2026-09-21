"""`python -m tts_sample` の入口。

コンソールスクリプト（Windows では tts.exe というシムが生成される）は使わない。
実行しているものが何なのかが見た目で分かるよう、モジュール実行に統一している。
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
