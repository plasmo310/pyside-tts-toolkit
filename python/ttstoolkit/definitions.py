"""画面に並べる選択肢の定義。

呼ばれる先: gui/widgets/
呼ぶ先: なし

値はそのまま処理モジュールに渡せる文字列にしてあるので、画面と処理側の
あいだで変換を挟まない。エンジンの選択肢 (`EngineType`) と中身
(どのモデルをどの仮想環境で動かすか) は `core.engine` にある。
"""

from __future__ import annotations

from enum import Enum


class LanguageType(Enum):
    """言語の選択肢。

    Attributes:
        code (str): エンジンに渡す言語コード。空文字ならエンジンに任せる。
        label (str): プルダウンに出す表示名。
    """

    AUTO = ("", "Auto")
    JAPANESE = ("ja", "Japanese (ja)")
    ENGLISH = ("en", "English (en)")

    def __init__(self, code: str, label: str) -> None:
        """メンバを作る。

        Args:
            code: エンジンに渡す言語コード。
            label: プルダウンに出す表示名。
        """
        self.code = code
        self.label = label

    @classmethod
    def from_code(cls, code: str | None) -> LanguageType:
        """言語コードから種別を返却する。該当が無ければ AUTO。"""
        for member in cls:
            if member.code == (code or ""):
                return member
        return cls.AUTO


class VoiceSourceType(Enum):
    """声をどこから決めるかの選択肢。

    Attributes:
        key (str): 保存や分岐に使う識別子。
        label (str): プルダウンに出す表示名。
    """

    PRESET = ("preset", "Preset voice")
    REFERENCE = ("reference", "Clone from reference audio")
    DESIGN = ("design", "Design from a description")

    def __init__(self, key: str, label: str) -> None:
        """メンバを作る。

        Args:
            key: 保存や分岐に使う識別子。
            label: プルダウンに出す表示名。
        """
        self.key = key
        self.label = label

    @classmethod
    def from_key(cls, key: str | None) -> VoiceSourceType:
        """識別子から種別を返却する。該当が無ければ PRESET。"""
        for member in cls:
            if member.key == key:
                return member
        return cls.PRESET
