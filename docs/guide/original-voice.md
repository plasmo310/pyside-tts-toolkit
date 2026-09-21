# オリジナルの声を作る

実在の人物に依存しないキャラクターの声を、文章の指示だけから作る。
作った声は「マスター音声」として固定し、以後はそれをクローンして使い回す。

```
① 文章で声を設計する          --voice-design で何本か試す
        ↓
② 気に入った声をマスター音声に  長めの台詞で 1 本作って保存
        ↓
③ 以後はクローンして使う       -r にマスター音声を渡す
        ↓
④ 英語版も同じ声で            マスター音声を Qwen / Chatterbox へ
```

なぜ固定するのかというと、Voice Design は生成のたびに声が揺れるため。
一度マスター音声に落とせば、以後は参照音声からのクローンになるので安定する。
英語など別のエンジンを使う場面でも同じ声を持ち込める。

## 対応エンジン

| エンジン | Voice Design | 指示の言語 | 備考 |
|---|:---:|---|---|
| `irodori` | ○ | 日本語 | 日本語キャラクターならこれが第一候補。48 kHz |
| `qwen` | ○ | 英語推奨 | 専用チェックポイントを使う。`-r/--reference` とは併用不可 |
| `chatterbox` | × | — | 参照音声からのクローンのみ |

`chatterbox` に `--voice-design` を渡すと、黙って無視されず明示的にエラーになる。

---

## ① 文章で声を設計する

### Irodori（日本語）

```powershell
tts synth -e irodori --seed 42 `
    --voice-design "落ち着いた低めの女性の声。丁寧で穏やかな話し方。" `
    -t "この声でどうでしょうか。名前は霊夢といいます。" `
    -l ja -o input\voices -O try01.wav
```

指示の文章を変えて何本か作り、聴き比べる。

```powershell
tts synth -e irodori --seed 42 `
    --voice-design "元気で明るい少女の声。やや早口で、楽しそうに話す。" `
    -t "この声でどうでしょうか。名前は魔理沙といいます。" `
    -l ja -o input\voices -O try02.wav

tts synth -e irodori --seed 42 `
    --voice-design "少し掠れた低い男性の声。ぶっきらぼうだが芯がある。" `
    -t "この声でどうでしょうか。" `
    -l ja -o input\voices -O try03.wav
```

#### 指示文の書き方

効くのは次のような軸。全部を詰め込むより、3〜4 要素に絞るほうが安定する。

| 軸 | 例 |
|---|---|
| 性別・年齢 | 若い女性、少年、中年の男性、老人 |
| 声の高さ・質 | 低め、高め、掠れた、澄んだ、ハスキー、太い |
| 話し方 | 丁寧、ぶっきらぼう、早口、ゆっくり、淡々と |
| 感情・態度 | 楽しそうに、呆れたように、落ち着いて、緊張気味に |

```
落ち着いた低めの女性の声。丁寧で穏やかな話し方。
元気で明るい少女の声。やや早口で、楽しそうに話す。
少し掠れた低い男性の声。ぶっきらぼうだが芯がある。
```

> [!tip] シードを固定して指示文だけ変える
> `--seed` を固定しておくと、声の違いが指示文によるものだと切り分けられる。
> 逆に指示文を固定してシードを変えると、同じ方向性で別の声が出る。
> 気に入った指示が見つかったら、シードを振って好みの 1 本を選ぶとよい。

### Qwen（英語中心）

Qwen は専用のチェックポイント（`Qwen3-TTS-12Hz-1.7B-VoiceDesign`）を使う。
初回は 4GB 前後のダウンロードが入る。

```powershell
tts synth -e qwen --seed 42 `
    --voice-design "A calm, low-pitched female voice. Speaks politely and gently." `
    -t "Hello. This is a designed voice." `
    -l en -o input\voices -O try_en.wav
```

Qwen の Voice Design は**参照音声と併用できない**。声の出どころが
指示文か参照音声のどちらか 1 つに決まるためで、両方渡すとエラーになる。

日本語のキャラクターを作るなら Irodori のほうが確実。Qwen の Voice Design は
英語・中国語中心に学習されているため、日本語の指示では安定しにくい。

---

## ② マスター音声を作る

声が決まったら、**長めの台詞で 1 本だけ**生成して保存する。これが以後の基準になる。

```powershell
tts synth -e irodori --seed 42 `
    --voice-design "落ち着いた低めの女性の声。丁寧で穏やかな話し方。" `
    -f input\voices\master_script.txt `
    -l ja -o input\voices -O reimu_master.wav
```

`voices/master_script.txt` の中身は、声の特徴が出るように書く。

```
こんにちは。私はこのキャラクターの声です。
今日はよろしくお願いします。
数字も読みます。一、二、三、十、百、千。
少し長めの文章を読むと、話し方の癖や間の取り方がよく分かります。
```

### マスター音声の条件

| エンジン | 推奨する長さ | 備考 |
|---|---|---|
| `irodori` | 30 秒以上 | 上限は合計 120 秒。長いほど安定する |
| `qwen` | 3 秒〜 | 書き起こしがあると品質が上がる |
| `chatterbox` | 10 秒前後 | 書き起こし不要 |

Irodori で 30 秒に届かない場合は、台本を足して長くする。

**使った指示文とシードは必ず控えておく。** マスター音声を作り直したくなったとき、
同じ条件から始められる。`cast.toml` に書いておくのが手軽。

---

## ③ 以後はクローンして使う

マスター音声ができたら、`--voice-design` ではなく `-r/--reference` を使う。

```powershell
tts synth -e irodori `
    -r input\voices\reimu_master.wav `
    -t "これはマスター音声から再現した声です。" `
    -l ja -O line01.wav
```

台本から使う場合は `cast.toml` に書く。

```toml
[voices."霊夢"]
engine = "irodori"
reference_audio = "../voices/reimu_master.wav"
language = "ja"
seed = 42
# 作ったときの指示文を記録しておく（コメント）
# voice_design = "落ち着いた低めの女性の声。丁寧で穏やかな話し方。"
```

台本での使い方は [script.md](script.md) を参照。

---

## ④ 英語版も同じ声で

Irodori は英語を出せないので、英語版はマスター音声を Qwen か Chatterbox に
渡してクロスリンガルにクローンする。

```powershell
# Qwen（書き起こしを渡すと品質が上がる）
tts synth -e qwen -l en `
    -r input\voices\reimu_master.wav `
    --reference-text "こんにちは。私はこのキャラクターの声です。今日はよろしくお願いします。" `
    -t "This is the same character speaking English." `
    -O line01_en.wav

# Chatterbox（書き起こし不要。軽くて速い）
tts synth -e chatterbox -l en `
    -r input\voices\reimu_master.wav `
    -t "This is the same character speaking English." `
    -O line01_en.wav
```

> [!warning] 同一人物に聞こえるかは耳で確認する
> 日本語と英語で音響モデルが違うため、機械的には「同じ参照音声」でも
> 聴感上は別人になることがある。両方を並べて聴いて判断すること。
> 違和感が大きい場合は、日英とも Qwen に統一するほうが揃いやすい。

---

## キャラクターを増やすときの流れ

1. `voices/` に試作を並べて聴き比べる（`try01.wav`, `try02.wav`, ...）
2. 採用した指示文とシードでマスター音声を作る（`<名前>_master.wav`）
3. `cast.toml` にキャラクターを追加する
4. 台本に台詞を足す

`voices/` はマスター音声の置き場として使う。サイズが大きいので
`.gitignore` に入れておき、指示文とシードだけを `cast.toml` に残しておけば
いつでも作り直せる。

## 声の設計を使わない選択肢

収録した実在の声を使う場合は、Voice Design を経由せず最初から `-r/--reference` に
その音声を渡せばよい。

```powershell
tts synth -e irodori -r input\voices\actor_take01.wav `
    -t "収録した声をクローンしています。" -l ja -O a.wav
```

**その場合は本人の同意と利用範囲の確認が必要。** モデルの重みは商用利用可
（Apache-2.0 / MIT）だが、声素材そのものの権利はそれとは別である。

## トラブルシュート

### `エンジン 'chatterbox' は Voice Design に対応していません`

Chatterbox は参照音声からのクローンのみ。別のエンジンで声を作ってから、
その音声を Chatterbox に `-r/--reference` で渡す。

### `Qwen3-TTS では --voice-design と -r は併用できません`

Qwen は指示文か参照音声のどちらか一方しか使えない。
文章から声を作るなら `-r/--reference` を外す。

なお Irodori は併用できる。その場合は**声質が参照音声・話し方が指示文**になる。

```powershell
tts synth -e irodori -r input\voices\reimu_master.wav `
    --voice-design "怒っている。強い口調で。" `
    -t "いい加減にしなさい！" -l ja -O angry.wav
```

### 毎回違う声になる

Voice Design は生成ごとに揺れる。`--seed` を固定し、決まったら
マスター音声に落として以後は `-r/--reference` を使う。

### 指示どおりの声にならない

- 要素を詰め込みすぎている。3〜4 要素に絞る
- Qwen に日本語で指示している。日本語なら Irodori を使う
- 同じ指示でシードを何本か振って、当たりを選ぶ
