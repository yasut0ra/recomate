# recomate コードベース整理メモ

この文書は `2026-03-18` 時点の実装を基準に、現役構成・残置コード・整理優先度をまとめたものです。

## 現在の全体像

- 実運用に近い本体は `api/` と `ui/` です。
- `api/` は FastAPI ベースのバックエンドで、会話・音声・ムード・メモリ・儀式・Agent リクエストを持ちます。
- `ui/` は React + TypeScript + Vite のフロントエンドで、Electron からも起動できます。
- `src/` と `electron/` には旧 Node/Express 系のコードが残っていますが、現行 README の主系統ではありません。

## ディレクトリ別の役割

### `api/`

- 現役バックエンド。
- `api/main.py`
  - FastAPI アプリのエントリポイント。
  - ルーティング定義と `VtuberAI` 実装が同居しており、責務が集中しています。
- `api/services/`
  - DB を使う機能単位のサービス層。
  - `rituals.py`, `memory.py`, `mood.py`, `agent_requests.py`, `album.py`, `consent.py` は比較的分離されています。
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

### `src/`

- 旧 Node/Express 系の残置コードです。
- `src/server.ts` と `src/routes/topics.ts` はダミー API に近く、現行 README の起動手順では使いません。

### `electron/`

- 旧 Electron 起動コードです。
- `electron/main.js` は Python プロセスを直接起動する実装ですが、現行 `ui/electron-main.js` と役割が重複しています。

## 実装済みの主な機能

- 会話 API: `/api/chat`
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

## 整理の観点で重要なポイント

### 1. `api/main.py` に責務が集まりすぎている

- ルーティング
- Pydantic モデル
- `VtuberAI`
- 音声・感情・会話オーケストレーション

この構成だと、会話機能の変更が API 層と強く結びつきます。次の整理では `chat`, `audio`, `topics` を router/service 単位へ切り出すのが自然です。

### 2. 現役コードと旧コードが同居している

- 現役: `api/`, `ui/`
- 旧構成の残置候補: `src/`, `electron/main.js`

いまの混在状態だと、新しく入る人が「どれが本番系なのか」を見誤りやすいです。

### 3. フロントエンドは検証パネルが多く、プロダクト UI と開発 UI が混ざっている

- チャット体験そのもの
- API 検証用のパネル

役割は明確なので、将来的には「通常 UI」と「開発/検証 UI」を分けると読みやすくなります。

## 2026-03-18 時点のチェック結果

- `python -m compileall api`: 成功
- `ui` の `npm run lint`: 成功
- `ui` の `npm run build`: 成功
- ビルド時に 500 kB 超のチャンク警告あり

## 次にやると効果が大きい整理

1. `api/main.py` を router ごとに分割する
2. `src/` と `electron/main.js` を `legacy/` へ移すか削除方針を決める
3. UI の API デモパネルを `features/devtools` 的にまとめる
4. pytest と最小限のフロントテストを追加する
5. `TopicBandit` と `EmotionAnalyzer` の OpenAI 呼び出しをサービス境界の内側に寄せる
