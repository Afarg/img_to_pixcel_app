# img_to_pixcel_app (PixelForge)

任意のキャラクター画像（写真・イラスト・背景ありの画像を含む）から、レトロ風ドット絵（ピクセルアート）キャラクター画像を自動生成するローカルWebアプリ。

> A deterministic image-processing pipeline that turns any character photo/illustration into a retro pixel-art sprite — background removal → crop/center → downsample → color quantization → outline enhancement.

3プロジェクトから成るパイプラインの1段目にあたるツール（[agent-village](https://github.com/Afarg/agent-village) のダッシュボードで使うピクセルキャラクターを生成する、生成物は [ani_convert_app](https://github.com/Afarg/ani_convert_app) がまばたき・歩行アニメーションの差分フレームを作る際の入力にもなる）。単体でも汎用的な「画像→ピクセルキャラ」変換ツールとして使える。

## 特徴

- **背景除去 → 自動トリミング/中央寄せ → ダウンサンプリング → 減色/パレット量子化 → 輪郭強調 → 書き出し**という決定論的パイプライン（AI生成は使わず、無料・オフラインで完結）。
- 画像アップロード → 自動処理 → プレビュー → パラメータ調整（`grid_size` / `colors` / `output_size`）→ エクスポート、という一連のUIを持つローカルWebアプリ。
- 正面のみ（フェーズ1）／正面＋斜め（フェーズ2）／正面＋斜め＋横向き＋後ろ向き（フェーズ3・フル）という3段階の入力構成に対応。1枚の画像から未提供のアングルを捏造することはしない、という方針を徹底。
- 「入っていない情報は作らない」という一貫した設計方針（詳細は `docs/design/` 参照）。

## 技術スタック

- Python / FastAPI（`uvicorn`）
- 画像処理: Pillow, `rembg`（背景除去, ONNX Runtime）, NumPy, SciPy

## セットアップ

```bash
python -m venv .venv
.venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

詳細は `docs/design/03-environment-and-setup.md` を参照。

## ドキュメント

設計ドキュメント一式は `docs/design/` にあり、全体像・アーキテクチャ・変換パイプラインの詳細設計・制約事項・Agent Villageとの連携方法・複数アングル入力の仕様をカバーしている。

| ドキュメント | 内容 |
|---|---|
| `00-overview.md` | 全体像・スコープ・動機 |
| `01-architecture.md` | システム構成・技術スタック・配布形態 |
| `02-conversion-pipeline.md` | 画像→ピクセルアート変換パイプラインの詳細設計 |
| `03-environment-and-setup.md` | 環境構築手順 |
| `04-constraints-and-limitations.md` | 制約・入力画像のガイドライン・既知の限界 |
| `05-agent-village-integration.md` | Agent Villageへの取り込み方法 |
| `06-multi-angle-input.md` | 3フェーズ構成・複数アングル入力の仕様 |
