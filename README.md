# recomate
会話トピック推薦と能動会話可能なAI

## プロジェクトビジョン / ロードマップ

- 相棒AIへの進化計画と優先タスクは `docs/recomate_codex_brief_v1.md` にまとめています。


## URL（完成版とは異なります）

### ホームページ
https://recomate-landing.netlify.app/

### デモ
https://spontaneous-cascaron-d7c26e.netlify.app/

## 開発環境の起動方法

1. Python の仮想環境を作成し、依存関係をインストールします。

   ```bash
   python -m venv venv
   source venv/bin/activate        # Windows の場合は venv\Scripts\activate
   pip install -r api/requirements.txt
   ```

2. FastAPI サーバーを起動します。

   ```bash
   python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
   ```

   - OpenAI API キーは `.env` で `OPENAI_API_KEY` として指定するか、UI の設定モーダルから入力できます。
   - 音声合成（VOICEVOX）を使用しない場合はデフォルトで無効です。有効化したい場合は `ENABLE_TTS=true` を環境変数に設定してください。

3. 別ターミナルでフロントエンドを起動します。

   ```bash
   cd recomate/ui
   npm install
   npm run dev
   ```

4. Electron で実行する場合は、FastAPI が `http://127.0.0.1:8000` で稼働していることを確認してください。

> 旧来の Node/Express サーバーは廃止しました。バックエンドは Python/FastAPI に統一されています。

## データベース / マイグレーション

- Postgres をローカルに用意し、`DATABASE_URL`（例: `postgresql+psycopg://postgres:postgres@localhost:5432/recomate`）を `.env` に設定します。
- 初期スキーマは Alembic で管理しています。
  ```bash
  # 初回
  alembic upgrade head

  # 変更時（例）
  alembic revision -m "add new table"
  alembic upgrade head
  ```
- `alembic.ini` の `sqlalchemy.url` はフォールバック用です。環境変数が優先されます。

## API スニペット

- **儀式**: `GET /api/rituals/morning?mood=%E9%99%BD%E6%B0%97`（朝）/`GET /api/rituals/night?mood=%E5%BF%83%E9%85%8D`（夜）
- **メモリ書き戻し**: `POST /api/memory/commit` Body `{"episode_id": "...", "summary": "...", "keywords": ["..."], "pinned": false}`
- **メモリ検索**: `GET /api/memory/search?q=keyword&user_id=<uuid>&limit=20`
- **同意設定**: `GET /api/consent?user_id=<uuid>` / `PATCH /api/consent?user_id=<uuid>` Body `{"night_mode": true, ...}`
