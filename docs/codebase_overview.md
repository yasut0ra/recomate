# recomate コードベース整理メモ

この文書は `2026-07-19` 時点の実装を基準に、現役構成・残置コード・整理優先度をまとめたものです（初版: 2026-03-18）。

## 現在の全体像

- 実運用に近い本体は `api/` と `ui/` です。
- `api/` は FastAPI ベースのバックエンドで、会話・音声・ムード・メモリ・儀式・Agent リクエストを持ちます。
- `ui/` は React + TypeScript + Vite のフロントエンドで、Electron からも起動できます。
- `legacy/` には旧 Node/Express / Electron 系のコードと旧 `vtuber_model.py` を退避しています。現行 README の主系統ではありません。

## ディレクトリ別の役割

### `api/`

- 現役バックエンド。
- `api/main.py`
  - FastAPI アプリのエントリポイント。ルーティングと CORS/lifespan 設定のみを持つ薄い層です。
  - チャット系エンドポイントは同期 `def` で宣言し、FastAPI のスレッドプールで実行されるため、LLM 呼び出し中もイベントループが塞がりません。
- `api/chat_engine.py`
  - 会話オーケストレーションの本体 (`ChatEngine`)。
  - 感情分析 → ランタイムコンテキスト → プランナー+バンディットによる話題選択 → LLM 生成（`chat.completions` を主モデル→フォールバックモデルの順に試行）→ 報酬計算 → 永続化、を1ターンとして処理します。
  - 会話履歴はユーザーごとの `_UserSession`（上限50件）に分離され、リクエスト間で共有される可変状態はロックで保護されています。
  - API キーはリクエスト単位で解決し、共有クライアントを書き換えません。
  - LLM 不通時の定型フォールバック応答はバンディット学習と自動メモリ昇格の対象外です。
- `api/services/`
  - DB を使う機能単位のサービス層。
  - `speech.py` は TTS（VOICEVOX）と音声認識をチャットから分離したサービスです。
  - `rituals.py`, `memory.py`, `mood.py`, `agent_requests.py`, `album.py`, `consent.py` は比較的分離されています。
- `api/topic_bandit.py`
  - LinUCB バンディット。プランナーが絞った候補から `select_with_context` で選択し、選択時の特徴量ベクトルをそのまま更新に使います。
  - 特徴量にはプランナーのトピック別ヒューリスティックスコアを含みます。
  - 学習状態は `data/bandit_state.json`（`RECOMATE_BANDIT_STATE_PATH` で変更、`off` で無効）に保存され、再起動後も引き継がれます。
- 学習ループ（2026-09-26〜）
  - バンディットの報酬はターン直後ではなく、ユーザーの反応が分かった時点で確定します。
  - 次のユーザー発話（30分以内）: 応答品質スコア35% + 反応スコア65%（LLM 判定、失敗時は `calculate_engagement_reward`）。
  - 明示フィードバック: `POST /api/chat/feedback`（👍=1.0 / 👎=0.0、1ターン1回）。好みプロファイルにも反映。
  - 同意設定の `learning_paused` が有効なら、バンディット学習もフィードバック反映も行いません。
- `api/turn_analyzer.py`
  - 感情分析と反応判定を担当。ユーザー発話ごとに小型 LLM を1回呼び、感情（happy/sad/angry/surprised/neutral）と、評価待ちの前ターンがあればその返答への反応（engaged/neutral/dismissive + 0〜1 スコア）を JSON スキーマ（strict）で取得します。
  - アシスタントの返答の感情（キャラクターの表情用）は、返答生成と同じ呼び出しで `{reply, expression}` の JSON（strict スキーマ）として受け取ります。追加の分析呼び出しはありません。モデルがスキーマに従わなかった場合や定型フォールバック返答はキーワード判定です。
  - 1ターンの LLM 呼び出しは「分析（小型モデル）＋生成」の2回です。
  - 出力はキーワード版 `EmotionAnalyzer` と同じ形（`source: "llm" | "keyword"` を追加）なので、プランナー・報酬・バンディット・UI は変更不要です。
  - クライアント無し・タイムアウト（8秒）・不正な出力のときは `EmotionAnalyzer` + `calculate_engagement_reward` にフォールバックします。
- `api/db/`
  - SQLAlchemy モデル、接続設定、Alembic マイグレーション。

### `ui/`

- 現役フロントエンド。
- `ui/src/App.tsx`
  - チャット UI に加えて、儀式・メモリ・ムード・Agent Request の検証パネルを並べる構成です。
- `ui/src/context/ChatContext.tsx`
  - チャット送信、音声再生、文字起こし、トピック統計を束ねる中核です。
- `ui/src/components/`
  - 会話 UI と API デモパネル群。
- `ui/electron-main.js`
  - Vite 開発サーバーを表示するシンプルな Electron エントリ。

### `legacy/node-express/`

- 旧 Node/Express 系の残置コードです。
- `legacy/node-express/src/server.ts` と `legacy/node-express/src/routes/topics.ts` はダミー API に近く、現行 README の起動手順では使いません。

### `legacy/electron/`

- 旧 Electron 起動コードです。
- `legacy/electron/main.js` は Python プロセスを直接起動する実装ですが、現行 `ui/electron-main.js` と役割が重複しています。

## 実装済みの主な機能

- 会話 API: `/api/chat`
- 会話フィードバック: `/api/chat/feedback`
- 音声合成: `/api/text-to-speech`
- 音声文字起こし: `/api/transcribe`
- トピック統計: `/api/topics/stats`
- リチュアル: `/api/rituals/morning`, `/api/rituals/night`
- メモリ: `/api/memory/commit`, `/api/memory/search`
- 同意設定: `/api/consent`
- 週次アルバム: `/api/album/weekly/generate`
- ムード遷移: `/api/mood/transition`, `/api/mood/history`
- Agent リクエスト: `/api/agent/request`, `/api/agent/ack`

## 仕様と実装のズレ

- `docs/recomate_codex_brief_v1.md` は将来像を含む設計文書です。
- 現在のフロントエンドは Next.js ではなく Vite/React です。
- 現在の会話系実装は WebRTC/WS 中心ではなく、REST と軽量 WebSocket の混在です。
- ベクトル DB や S3 互換ストレージは未実装で、メモリ・アルバムは PostgreSQL 前提の軽量実装です。

## 2026-07-19 の整理で解消済みの項目

- `api/main.py` の責務集中: `ChatEngine` / `SpeechService` へ分割し、REST と WebSocket は同じ `handle_turn` を共有。
- グローバル会話状態の混線: 履歴・感情・報酬をユーザー別セッションとターン戻り値に分離。
- Responses API の不正な `content` 形式による常時フォールバック: `chat.completions`（主→フォールバックモデル）に一本化。
- メモリ検索の自己強化ループ: 候補取得を `created_at` 基準に変更（`last_ref` は利用記録のみ）。
- バンディットのデッドコード化: プランナー候補からの LinUCB 選択に接続。未使用の gpt-3.5-turbo 系メソッドは削除。
- UI: `user_id` を送信し、サーバー履歴でローカルメッセージを置き換える挙動を廃止。
- その他: 起動時の2秒スリープ削除、エラー詳細のクライアント漏洩防止、`print` の logger 化、voice_cache 上限（200ファイル）、ビルドチャンク分割。

## 整理の観点で残っているポイント

### 1. 現役コードと旧コードが同居している

- 現役: `api/`, `ui/`
- 旧構成の退避先: `legacy/node-express/`, `legacy/electron/`, `legacy/vtuber_model.py`

いまの混在状態だと、新しく入る人が「どれが本番系なのか」を見誤りやすいです。

### 2. フロントエンドは検証パネルが多く、プロダクト UI と開発 UI が混ざっている

- チャット体験そのもの
- API 検証用のパネル

役割は明確なので、将来的には「通常 UI」と「開発/検証 UI」を分けると読みやすくなります。

## 2026-07-19 時点のチェック結果

- `python -m pytest tests`: 54 件成功（エンドポイントテスト含む）
- `ui` の `npm run lint`: 成功
- `ui` の `npm run build`: 成功（チャンク分割済み、500 kB 警告なし）
- 実サーバーでの `/health` / `/api/chat`（主モデル経由の実応答・エピソード永続化・ユーザー別履歴・バンディット学習）を確認

## ローカル開発の現行導線

- 推奨起動はルートからの `npm run dev`
- Web のみなら `npm run dev:web`
- どちらも FastAPI を含めて起動する
- UI 単体確認が必要な場合だけ `ui/` 配下のスクリプトを直接使う

## 依存関係の現行方針

- `api/requirements.txt`
  - API の最小起動に必要な依存のみ
- `api/requirements-optional.txt`
  - 音声合成、音声認識、実験用ローカル機能の依存
- `api/requirements-dev.txt`
  - `pytest` と `httpx`（FastAPI TestClient 用）。回帰テスト実行用

## 次にやると効果が大きい整理

1. `legacy/` 配下の旧構成を削除するか、資料として残すか方針を決める
2. UI の API デモパネルを `features/devtools` 的にまとめる
3. 最小限のフロントテストを追加する
4. ユーザー別セッション履歴の永続化（現状はプロセス内メモリ + episodes テーブル）
5. WebSocket 経路の UI 利用（現状 UI は REST のみ。WS は API として維持）
