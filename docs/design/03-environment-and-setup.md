# 03. 環境構築・必要なソフトウェア — PixelForge

対象読者: 実装者・導入担当者。
関連: `01-architecture.md`（技術スタックの選定理由・Pythonを採用した経緯）。

---

## 1. 前提条件

| 項目 | 要件 |
|---|---|
| Python | 3.10以上を推奨 |
| pip / venv | Pythonに同梱のもので可。仮想環境（`venv`）の利用を推奨 |
| OS | Windows / macOS / Linux（`rembg`・`onnxruntime`はいずれもクロスプラットフォーム対応の配布がある。§4） |
| ディスク容量 | `rembg`が初回実行時に自動ダウンロードするモデル分の空き容量が必要（§3） |
| GPU | 不要（CPU推論で動作する想定）。`rembg`はGPU拡張（`pip install rembg[gpu]`）にも対応しているが必須ではない |
| ネットワーク | 初回セットアップ時（`pip install`・モデル自動ダウンロード）のみ必要。以降の変換処理自体は完全オフラインで動作する |

Agent Village本体（Node.js 18+、`docs/setup.md` §2）とは**別ランタイム**になる点に注意。両方を同じマシンで動かす場合、Node.jsとPythonの両方がインストールされている必要がある（`01-architecture.md` §1で明記した唯一のトレードオフ）。

## 2. 必要なpipパッケージ

調査で実在・仕様を確認済みの候補（`01-architecture.md` §3）:

| パッケージ | 役割 | 備考 |
|---|---|---|
| `fastapi` | ローカルサーバー（APIフレームワーク） | `uvicorn`と組み合わせて起動する |
| `uvicorn` | ASGIサーバー | FastAPIアプリの実行に必要 |
| `python-multipart` | 画像アップロード受信 | FastAPIでファイルアップロードを扱うために必要 |
| `Pillow` | 画像のリサイズ・クロップ・パレット量子化 | `Image.quantize()`で減色まで標準機能で完結する（追加の減色専用ライブラリ不要） |
| `rembg` | 背景除去（被写体抽出） | MITライセンス（確認済み）。内部でONNXモデル（u2net/u2netp/isnet-general-use等）を使用し、初回実行時に自動ダウンロードする |
| `numpy` | 配列演算 | bounding box計算、輪郭強調の画素走査などの補助 |
| `requests` または `httpx` | Agent Villageへの直接送信（任意機能） | `05-agent-village-integration.md`の連携方法Bでのみ使用 |

`requirements.txt`の例:

```
fastapi
uvicorn
python-multipart
Pillow
rembg
numpy
requests
```

## 3. 背景除去モデルの用意（Node版から大きく簡略化）

Node.js + `onnxruntime-node`を検討していた旧版では、ONNXモデルファイルの手動配置が必要だった。**`rembg`を採用したことでこの手間がなくなる**:

- `rembg`は初回実行時に、指定したモデル（既定は`u2net`、軽量版が良ければ`u2netp`）を自動的に`~/.u2net/`にダウンロードして配置する。実装側が意識する必要があるのは、初回起動時にダウンロードが走るためネットワーク接続と多少の待ち時間が発生する、という点だけ。
- モデル選択はコード上で`rembg.new_session("u2net")`のように文字列で指定するだけで切り替えられる（軽量版`u2netp`にすれば処理速度とダウンロード量を抑えられる。既定値は実装時に実測して決める）。
- **`rembg`パッケージ自体はMITライセンス**（確認済み）。ただし内部で使うモデルの**重み**自体は別プロジェクト（U^2-Net等）由来であり、そのライセンス条項は`rembg`のライセンスとは別に確認が必要（`04-constraints-and-limitations.md` §1）。

## 4. クロスプラットフォーム対応の確認（実装前に要確認）

`rembg`・`onnxruntime`はいずれもネイティブバイナリを含む配布のため、実装に着手する前に対象OS（Windows/macOS/Linux）・CPUアーキテクチャ（x64/arm64、特にApple Silicon）でのインストール可否を実機で確認すること。Agent Village自体が確立した「hookのペイロード形状を実測してから実装する」という方針（`05-hooks-state-writer.md`）と同じく、**ここも決め打ちせず実機確認を先に行う。**

## 5. 起動方法（案）

```bash
cd pixel-forge
python -m venv .venv
.venv\Scripts\activate          # Windows。macOS/Linuxは `source .venv/bin/activate`
pip install -r requirements.txt
uvicorn app.main:app --port 4273
```

ブラウザで `http://localhost:4273` を開く。

初回起動時、`rembg`のモデルダウンロードが未完了であれば、その旨をターミナル/ブラウザ両方に分かりやすく表示する（Agent Villageの「エージェント定義が0件のとき求人募集の立て看板を出す」という空状態UXの考え方、`01-visual-concept.md` §6.3、を踏襲）。
