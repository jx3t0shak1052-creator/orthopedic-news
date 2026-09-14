# 整形外科 情報ダイジェスト

## セットアップ手順

### 1. GitHub Pages を有効化
Settings → Pages → Branch: main / root → Save

### 2. Google Gemini APIキーを登録
Settings → Secrets and variables → Actions → New repository secret
- Name: `GOOGLE_API_KEY`
- Secret: `AIza...`（aistudio.google.comから取得・無料）

### 3. 初回のみ：詳細解析を一括生成
Actions → 既存論文の詳細解析を一括生成 → Run workflow

以後は毎日6時に論文、毎週月曜6時半にインプラントニュースが自動更新されます。
