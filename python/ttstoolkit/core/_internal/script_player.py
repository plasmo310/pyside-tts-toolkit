"""台本の合成結果から、ブラウザで聞ける再生用 HTML を作る。

呼ばれる先: core.tts_service のみ (`core` の外からは import しない)
呼ぶ先: core.settings のみ

`manifest.json` と同じ内容を、台詞ごとの再生ボタンと、先頭から通しで
再生するボタンを持つ 1 枚の HTML にする。wav は `manifest.json` と
同じディレクトリに書き出されている前提で、ファイル名だけを埋め込む
（HTML を別の場所へ動かすと参照が壊れる）。
"""

from __future__ import annotations

import json
import os

from ttstoolkit.core.settings import get_logger

_logger = get_logger(__name__)

# 台本ディレクトリに書き出すファイル名 (manifest.json と同じ階層)
PLAYER_NAME = "index.html"

_HTML_TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{color-scheme:dark;font-family:system-ui,"Yu Gothic UI",sans-serif;background:#15171b;color:#f4f5f7}
body{margin:0}
header{position:sticky;top:0;z-index:2;padding:18px max(24px,calc((100vw - 900px)/2));background:rgba(21,23,27,.94);border-bottom:1px solid #333945;backdrop-filter:blur(8px)}
h1{margin:0 0 5px;font-size:1.3rem}
.sub{color:#aeb7c4;font-size:.85rem}
.toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:14px}
button{font:inherit;border-radius:7px;border:1px solid #48515e;color:inherit;background:#252b34;padding:8px 14px;cursor:pointer}
button:hover{background:#353e4b}
button.playing{background:#155e75;border-color:#22c5e5}
#playAll.playing{background:#155e75;border-color:#22c5e5}
#stop{background:#5b2731;border-color:#a24858}
#stop:hover{background:#75313d}
main{max-width:900px;margin:0 auto;padding:22px 24px 48px}
ol{list-style:none;margin:0;padding:0}
li{display:flex;gap:14px;align-items:flex-start;padding:14px 16px;border-bottom:1px solid #262c35;transition:background .15s}
li.active{background:#1b2734}
.idx{color:#6b7686;font:.78rem ui-monospace,Consolas,monospace;width:28px;padding-top:3px;flex:none}
.body{flex:1;min-width:0}
.voice{font-weight:600;font-size:.92rem;margin-bottom:3px}
.text{color:#d7dce3;font-size:.92rem;line-height:1.55}
.dur{color:#6b7686;font-size:.72rem;margin-top:4px;font-family:ui-monospace,Consolas,monospace}
.play-line{flex:none;padding:6px 12px;font-size:.8rem}
</style>
</head>
<body>
<header>
<h1>__TITLE__</h1>
<div class="sub">__SUBTITLE__</div>
<div class="toolbar">
<button id="playAll" type="button">&#9654; 一括再生</button>
<button id="stop" type="button">&#9632; 停止</button>
</div>
</header>
<main><ol id="list"></ol></main>
<script>
const items = __ITEMS__;
let current = null;
let sequence = false;

function stop(){
  if(!current) return;
  current.audio.pause();
  current.audio.currentTime = 0;
  current.li.classList.remove("active");
  current.button.classList.remove("playing");
  current = null;
  sequence = false;
  document.querySelector("#playAll").classList.remove("playing");
}

function playIndex(i, chained){
  if(i >= items.length){ stop(); return; }
  const item = items[i];
  const li = document.querySelector('li[data-index="' + i + '"]');
  const button = li.querySelector(".play-line");
  const audio = new Audio(encodeURI(item.file));
  current = {audio, li, button, index: i};
  li.classList.add("active");
  button.classList.add("playing");
  audio.addEventListener("ended", () => {
    li.classList.remove("active");
    button.classList.remove("playing");
    if(sequence && chained){
      playIndex(i + 1, true);
    } else {
      current = null;
    }
  });
  audio.play().catch(stop);
}

function playSingle(i){
  const wasSameIndex = current && current.index === i;
  stop();
  if(wasSameIndex) return;
  sequence = false;
  playIndex(i, false);
}

function playAll(){
  const wasPlayingAll = sequence;
  stop();
  if(wasPlayingAll) return;
  sequence = true;
  document.querySelector("#playAll").classList.add("playing");
  playIndex(0, true);
}

function render(){
  const list = document.querySelector("#list");
  items.forEach((item, i) => {
    const li = document.createElement("li");
    li.dataset.index = String(i);
    const idx = document.createElement("div");
    idx.className = "idx";
    idx.textContent = String(i + 1).padStart(2, "0");
    const body = document.createElement("div");
    body.className = "body";
    const voice = document.createElement("div");
    voice.className = "voice";
    voice.textContent = item.voice;
    const text = document.createElement("div");
    text.className = "text";
    text.textContent = item.text;
    const dur = document.createElement("div");
    dur.className = "dur";
    dur.textContent = item.duration.toFixed(2) + "s";
    body.append(voice, text, dur);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "play-line";
    button.textContent = "▶ 再生";
    button.addEventListener("click", () => playSingle(i));
    li.append(idx, body, button);
    list.append(li);
  });
}

document.querySelector("#playAll").addEventListener("click", playAll);
document.querySelector("#stop").addEventListener("click", stop);
render();
</script>
</body>
</html>
"""


def build_player_html(title: str, subtitle: str, items: list[dict]) -> str:
    """台詞のリストから再生用 HTML の中身を組み立てる。

    Args:
        title: ページタイトルと見出しに使う文字列。
        subtitle: 見出しの下に出す説明文。
        items: 1 台詞ぶんの辞書のリスト
            (`voice` / `text` / `duration` / `file`)。

    Returns:
        str: 書き出せる HTML 全体。
    """
    html = _HTML_TEMPLATE.replace("__TITLE__", title)
    html = html.replace("__SUBTITLE__", subtitle)
    return html.replace("__ITEMS__", json.dumps(items, ensure_ascii=False))


def write_script_player(output_dir: str, title: str, manifest: dict) -> str:
    """台本の manifest から再生用 HTML を書き出す。

    Args:
        output_dir: `manifest.json` と wav がある書き出し先ディレクトリ。
        title: ページタイトルに使う文字列。
        manifest: `_build_script_manifest()` が組み立てた辞書。

    Returns:
        str: 書き出した HTML のパス。
    """
    items = [
        {
            "voice": item["voice"],
            "text": item["text"],
            "duration": item["duration_sec"],
            "file": os.path.basename(item["output_path"]),
        }
        for item in manifest["items"]
    ]
    subtitle = (
        f"{len(items)} lines / "
        f"total {manifest.get('total_duration_sec', 0.0):.1f}s"
    )
    html = build_player_html(title, subtitle, items)

    path = os.path.join(output_dir, PLAYER_NAME)
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write(html)
    _logger.info("wrote %s", path)
    return path
