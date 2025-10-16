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
   cd recomate
   python -m venv venv
   venv\Scripts\activate  # macOS/Linux の場合は source venv/bin/activate
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
