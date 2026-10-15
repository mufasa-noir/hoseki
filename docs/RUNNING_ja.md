<div align="center">

<h2><b>Hoseki の動かし方: ステップバイステップ</b></h2>

[English](RUNNING.md) | [日本語](RUNNING_ja.md)

</div>

以下のステップは順番どおりに進めてください。各ステップの最後に**チェックポイント**があります。通過するまで次へ進まないでください。最初は必ず**使い捨てフォルダ**で試し、以下がすべて動くようになってから、本物のコードを対象にしてください。

ターミナルは 2 つ使います。

- **ターミナル #1**: デーモンを実行し、承認プロンプトを表示します。開いたままにしてください。
- **ターミナル #2**: それ以外のすべて（`curl` での確認、設定ファイルの編集など）に使います。

## ステップ 0: 前提条件

先に次をインストールして、確認してください。

```bash
python3 --version          # 3.11 以上が必要です
git --version              # 最近のバージョンであれば何でも OK
```

> **チェックポイント:** `python3 --version` が `Python 3.11.x` 以上を表示する。

以降の確認手順では `curl` と `jq` も使います。サンドボックス用に、次も（任意ですが）おすすめです。

```bash
docker info                # エラーになる場合は Docker 未インストールです。その場合は省略して構いません
```

## ステップ 1: コードを取得する

```bash
git clone https://github.com/mufasa-noir/hoseki.git hoseki
cd hoseki
```

> **チェックポイント:** `ls` で `pyproject.toml`、`src/`、`extension/`、`docs/`、`README.md` が表示される。

## ステップ 2: 仮想環境を作成してインストールする

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e '.[dev]'
```

> **チェックポイント:** `hoseki --version` が `hoseki 0.2.2` と表示する。`hoseki` が見つからない場合は、仮想環境に入っていません。もう一度 `source .venv/bin/activate` を実行してください。

## ステップ 3: 設定する

```bash
cp config.example.toml config.toml
```

`config.toml` をエディタで開き、最初は次の 1 行だけを設定します。

```toml
[workspace]
root = "/absolute/path/to/a/throwaway/folder"
```

今は使い捨てフォルダ（テキストファイルが 1〜2 個入っただけのディレクトリ）を使ってください。**まだ本物のコードを指定しないでください。**

> **チェックポイント:** `config.toml` が存在し、`[workspace].root` が実在する絶対パスになっている。次のコマンドで確認できます。
>
> ```bash
> ls "$(grep '^root' config.toml | cut -d'"' -f2)"
> ```
>
> フォルダの中身が一覧表示されるはずです。エラーになる場合は、パスを修正してください。

## ステップ 4: デーモンを起動する

**ターミナル #1** で実行します。

```bash
hoseki serve --config ./config.toml
```

> **チェックポイント:** 次の行が表示され、プロセスが終了せず動き続けている。
>
> ```text
> Hoseki 0.2.2 listening on http://127.0.0.1:8765  workspace=/abs/path/to/folder
> ```

**このターミナルは開いたままにしてください。** 承認プロンプトは、このあとここに表示されます。残りのステップは、2 つ目のターミナルで行います。

## ステップ 5: デーモンの動作を確認する

**ターミナル #2** で実行します。

```bash
export TOKEN=$(cat ~/.hoseki/token)
export HOSEKI=http://127.0.0.1:8765
```

まず、ヘルスチェックをします（認証は不要です）。

```bash
curl -s $HOSEKI/v1/health | jq
```

> **チェックポイント:** `{"ok": true, "service": "hoseki", "version": "0.2.2"}` が表示される。

次に、ワークスペースを一覧表示します。

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"name":"list_dir","args":{"path":".","depth":1}}' \
     $HOSEKI/v1/call | jq -r .output
```

> **チェックポイント:** 使い捨てフォルダのファイルツリーが表示される。

最後に、パスジェイルが機能していることを確認します。**これは必ず失敗しなければなりません。**

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"name":"read_file","args":{"path":"../../etc/passwd"}}' \
     $HOSEKI/v1/call | jq
```

> **チェックポイント:** `{"id": null, "ok": false, "error": "path ... resolves outside the workspace root"}` が表示される。
>
> **ファイルの中身が表示された場合は、ここで中止してください。** ジェイルが壊れているため、先に進んではいけません。

## ステップ 6: ブラウザ拡張機能を読み込む

ブラウザごとに 1 つずつビルドがあります。`extension/chrome/`（Chrome、Edge、Brave などの Chromium 系ブラウザ用）と `extension/firefox/`（Firefox 用）です。

### Chrome（または Edge/Brave）

1. `chrome://extensions` を開きます。
2. 右上の**デベロッパーモード**をオンにします。
3. **パッケージ化されていない拡張機能を読み込む**をクリックします。
4. クローンした Hoseki 内の `extension/chrome/` フォルダを選択します。
5. ツールバーの Hoseki アイコンをクリックして、ポップアップを開きます。

### Firefox

1. `about:debugging#/runtime/this-firefox` を開きます。
2. **一時的なアドオンを読み込む…**（Load Temporary Add-on…）をクリックし、クローンした Hoseki 内の `extension/firefox/manifest.json` を選択します。一時的なアドオンは Firefox を閉じると削除されるため、次回のセッションでもう一度行ってください。
3. ツールバーから Hoseki のポップアップを開きます（見当たらない場合は、パズルピースの形の拡張機能メニューから開いてください）。

### その後、どちらのブラウザでも

次を入力します。

- **Daemon URL:** `http://127.0.0.1:8765`
- **Bearer token:** ターミナル #2 で `cat ~/.hoseki/token` を実行し、出力を貼り付けます。

**Save** をクリックします。

> **チェックポイント:** **Check health** をクリックして、`{"ok": true, ...}` が表示される。表示されない場合は次を確認してください。
>
> - `network error`: デーモンが起動していません（ステップ 4 に戻ってください）。
> - `unauthorized`: トークンの貼り付けが間違っています。`cat ~/.hoseki/token` をもう一度実行してください。

続いて **Status** をクリックします。

> **チェックポイント:** ワークスペースルートとツールの一覧が表示される。

## ステップ 7: チャットを開く

対応しているチャットを、新しいタブで開きます。

- <https://chat.z.ai>（GLM）
- <https://kimi.com>
- <https://chat.deepseek.com>（DeepSeek）

それ以外のチャットは、先にアダプターが必要です（README を参照してください）。

開発者ツール（F12）→ **Console** を開き、次の行を探します。

```text
[Hoseki] content script active for chat.z.ai adapter: GLM / z.ai (best-effort)
```

> **チェックポイント:** その行が表示される。表示されない場合は、コンテンツスクリプトが読み込まれていません。タブを再読み込みするか、`chrome://extensions` で拡張機能を再読み込みしてください（Firefox は `about:debugging`）。
>
> その行は表示されるのに、モデルがツールブロックを出力しても何も起きない場合は、サイトのセレクターの更新が必要な可能性があります。[SELECTORS_ja.md](SELECTORS_ja.md) を参照してください。

## ステップ 8: プリアンブルを貼り付ける

Hoseki のポップアップで **Copy preamble** をクリックします。それをチャットの最初のメッセージとして貼り付けて送信します。

> **チェックポイント:** チャットのメッセージ #1 がプリアンブルになっている。モデルは「了解しました」のような返事をするか、単に受け取ったことを返します。

## ステップ 9: 最初のツール呼び出しを試す

そのままチャットで、次のメッセージを送ります。

> List the files in my workspace and read the first 20 lines of the only file you find.
> （ワークスペース内のファイルを一覧表示して、見つかった唯一のファイルの最初の 20 行を読んでください。）

次のことが起こるはずです。

1. モデルが、フェンスコードブロックの `tool` ブロックで返信します（例: `` ```tool {"id":"c1","name":"list_dir",...} ``）。
2. 1〜2 秒以内に、チャット画面の右下に Hoseki のオーバーレイが浮かび、`✓ c1: ...` と表示されます。
3. `tool_result` ブロックがチャットの入力欄に挿入されます。

> **チェックポイント:** オーバーレイに緑のチェックが表示され、入力欄に `tool_result` ブロックが入っている。

**送信はあなた自身が押します。** これがデフォルトの半自動モードです。自動で送信されることはありません。

その後、モデルが結果を読んで続行します。2 つ目のファイルが必要になれば、別のツールブロックを出力し、このやり取りが繰り返されます。

## ステップ 10: 書き込みを試す（承認フロー）

チャットで、次のメッセージを送ります。

> Create a file called HELLO.txt with the content "it works".
> （内容を "it works" とした HELLO.txt というファイルを作成してください。）

次のことが起こるはずです。

1. モデルが `write_file` のツールブロックを出力します。
2. **デーモンのターミナル**（ステップ 4）に、次のように表示されます。

   ```text
   ========================================================================
   HOSEKI APPROVAL REQUIRED — write_file
     write HELLO.txt (8 bytes, new file)
   ------------------------------------------------------------------------
   --- /dev/null
   +++ b/HELLO.txt
   @@ -0,0 +1,1 @@
   +it works
   ------------------------------------------------------------------------
   Approve? [y/N]
   ```

3. デーモンはここで止まり、あなたの入力を待っています。`y` を入力して Enter を押します。

> **チェックポイント:** デーモンが `-> APPROVED` と表示して再開する。チャットのオーバーレイに ✓ が表示され、入力欄に成功を示す `tool_result` が入る。

ファイルが存在することを確認します。

```bash
ls "$(grep '^root' config.toml | cut -d'"' -f2)/HELLO.txt"
```

> **チェックポイント:** ファイルが存在し、内容が `it works` になっている。

次は、わざと拒否してみます。次のメッセージを送ります。

> Overwrite HELLO.txt with "second try".
> （HELLO.txt を "second try" で上書きしてください。）

承認プロンプトが表示されたら、`n` を入力して Enter を押します。

> **チェックポイント:** オーバーレイに `✗ ... denied by operator` と表示され、`cat HELLO.txt` は今も `it works` のままになっている。

## ステップ 11: コマンドを試す（任意）

これには `config.toml` の変更が必要です。ターミナル #2 で実行します。

```bash
# 許可リストに "ls" を追加します（ワークスペースが git リポジトリなら "git status" でも可）
nano config.toml
```

`[commands]` を探し、プレフィックスを 1 つコメント解除します。例:

```toml
allowlist = [ "ls" ]
```

保存してからデーモンを再起動します（ターミナル #1 で Ctrl-C を押し、もう一度 `hoseki serve --config ./config.toml` を実行）。

チャットで、次のメッセージを送ります。

> Run ls in the workspace and show me the output.
> （ワークスペースで ls を実行して、出力を見せてください。）

デーモンのターミナルに承認プロンプトが表示されます。表示された argv を確認してから、`y` を入力してください。

> **チェックポイント:** オーバーレイにディレクトリの一覧が表示される。

拒否されるはずのものも試します。

> Run rm -rf / in the workspace.
> （ワークスペースで rm -rf / を実行してください。）

> **チェックポイント:** 承認プロンプトには到達せず、即座に `command not in allow-list` または `contains shell operator` で失敗する。これは正しい動作です。許可リストが、あなたの目に触れる前に拒否しました。

## ステップ 12: 普段の使い方

使い捨てフォルダでステップ 1〜11 がすべて通ったら、普段の使い方は次のとおりです。

1. ターミナル #1: `cd hoseki && source .venv/bin/activate && hoseki serve --config ./config.toml`
2. チャットのタブを開き、プリアンブルを貼り付けて作業します。
3. デーモンのターミナルで、承認プロンプトを見守ります。
4. オーバーレイが入力欄に結果を入れたら、チャットで送信を押します。

プロジェクトフォルダを変更するか、再インストールしない限り、ステップ 3〜6 をやり直す必要はありません。

## トラブルシューティング早見表

| 症状                                                    | 考えられる原因と対処                                                              |
| ------------------------------------------------------- | --------------------------------------------------------------------------------- |
| `hoseki: command not found`                             | 仮想環境に入っていません。`source .venv/bin/activate` を実行してください。        |
| ポップアップに `network error` と表示される             | デーモンが起動していません。起動してください（ステップ 4）。                      |
| ポップアップに `unauthorized` と表示される              | トークンの貼り付けが間違っています。`cat ~/.hoseki/token` を再実行して貼り直してください。 |
| コンソールに `[Hoseki] content script active` が出ない  | チャットのタブ、または `chrome://extensions` で拡張機能を再読み込みしてください。 |
| ジェイルの確認でファイルの中身が表示される              | **中止してください。** パスジェイルが壊れています。本物のコードには使わないでください。 |
| コマンドが `command not in allow-list` で失敗する       | 許可リストにないものは想定どおりです。`[commands]` にプレフィックスを追加してください（ステップ 11）。 |
| モデルがツールブロックを出力しても何も起きない | サイトのセレクターが古くなっている可能性があります。[SELECTORS_ja.md](SELECTORS_ja.md) を参照してください。 |
| ポップアップまたはオーバーレイに `origin not allowed by daemon` と表示される | デーモンがブラウザの拡張機能のオリジン（`chrome-extension://<id>` または `moz-extension://<uuid>`）を拒否しています。デーモンの許可オリジンに追加してください。 |
| Firefox: `[Hoseki] content script active` の行が出ない | サイトへのアクセスが許可されていない可能性があります。`about:addons` → Hoseki → **権限** を開いてください。一時的なアドオンがまだ読み込まれているかも確認してください。 |
