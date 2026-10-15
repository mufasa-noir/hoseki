<div align="center">

<h2><b>セレクターの探し方と設定方法</b></h2>

[English](SELECTORS.md) | [日本語](SELECTORS_ja.md)

</div>

Hoseki は、チャットサイトがどのように作られているかを事前には知りえません。そこでサイトごとに**アダプター**を用意します。アダプターとは、Hoseki が必要とするページ上の部品を指し示す、いくつかの CSS セレクターのことです。チャットサイトはページ構造を予告なく変更するため、アダプターはときどき更新が必要になります。このガイドでは、ブラウザの開発者ツールで正しいセレクターを見つける方法と、それを書き込む場所を説明します。

## セレクターを書く場所

各アダプターは、**両方の**ビルドフォルダにある `content.js` の先頭付近の `ADAPTERS` オブジェクトに入っているエントリです。

- `extension/chrome/content.js`
- `extension/firefox/content.js`

2 つは同じ内容に保ってください。そうしないと、2 つのブラウザで動作が変わってしまいます。（アダプターを別ファイルに移している場合は、そちらを編集してください。）

エントリは**ホスト名**をキーにします（`chat.z.ai` のように、`https://` やパスは付けません）。キーはそのサブドメインにも一致するので、`kimi.com` は `www.kimi.com` もカバーします。ただし**別のドメインには一致しません**。`kimi.*` のようなワイルドカードも何にも一致しません。1 つのサイトが 2 つのドメインを使う場合（Kimi は `kimi.com` と `kimi.ai` の両方）は、それぞれにキーが必要です。いちばん簡単なのは、`ADAPTERS` オブジェクトの直後で一方を他方の別名にする方法です: `ADAPTERS["kimi.ai"] = ADAPTERS["kimi.com"];`

```js
"example.ai": {
  name: "Example AI",
  verified: "2026-10-13",
  assistantMessage: "[data-role='assistant']",
  messageIdAttr: "data-message-id",
  toolBlockSelector: ".code-block",
  toolBlockLangSelector: ".code-block-lang",
  toolBlockBodySelector: "pre",
  streamingIndicator: "[data-streaming='true']",
  input: "textarea, [contenteditable='true'][role='textbox']",
  sendButton: "button[type='submit'], button[aria-label*='send' i]",
  stopButton: "button[aria-label*='stop' i]"
},
```

## 各フィールドの役割

| フィールド           | 一致させるもの                                                                     | Hoseki での使われ方                                                     |
| -------------------- | ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `assistantMessage`   | **アシスタントの返信 1 件につき 1 要素**。返信全体であり、その中の段落やコードブロックではありません | **最後の**一致を最新の返信として読み、その中の `tool` ブロックを探します |
| `messageIdAttr`      | メッセージごとに一意な ID を持つ属性の名前（例: `data-message-id`）                | 同じ返信が二度処理されるのを防ぎます。省略可能で、属性がない場合はテキストのハッシュで代用します |
| `toolBlockSelector`  | 返信内の**コードブロック 1 つにつき 1 要素**。言語の表示とコード本体の**両方**を含む外側の要素 | 最新の返信の中からこれに一致する要素を探し、言語が `tool` のものだけを読み取ります。省略可能ですが、最近のチャットサイトの多くで必要です（手順 6） |
| `toolBlockLangSelector` | 各ブロックの**中にある**、言語名（`tool` など）を表示する要素                    | そのテキストが `tool` かどうかを調べます。言語がブロック自身の `language-xxx` クラスにあるサイトでは省略できます |
| `toolBlockBodySelector` | 各ブロックの**中にある**、コード本体を持つ要素（省略時は `pre`）                | Hoseki が JSON を読み取る場所。CodeMirror のエディタなら `.cm-content` など |
| `streamingIndicator` | **モデルが生成している間だけ**存在する要素                                         | これが消えるまで、Hoseki は返信への処理を待ちます                       |
| `stopButton`         | 「生成を停止」ボタン。**モデルが生成している間だけ**存在します                     | 上と同じです。どちらかが一致していれば「まだ生成中」とみなします        |
| `input`              | 入力するチャットボックス（`textarea` または `contenteditable` 要素）               | Hoseki が `tool_result` ブロックを挿入する場所                          |
| `sendButton`         | 送信ボタン                                                                         | オプションの自動送信機能でのみ使われます                                |

セレクターはすべて、カンマ区切りのリスト（`"a, b, c"`）にできます。ページのバージョン間の小さな違いをカバーするのに便利です。`PUT_SELECTOR_HERE` というプレースホルダーが残っている場合は、実際のセレクターに置き換えてください。エントリには `name`（オーバーレイとコンソールに表示されます）と、日付の文字列 `verified` もあります。アダプターがどれくらい古いかを把握するのに役立ちます。

## 手順

チャットサイトを開き、画面上にアシスタントの返信が少なくとも 2 件になるようにメッセージを 1〜2 回送ってから、開発者ツールを開きます。**F12**（または **Ctrl+Shift+I**、macOS では **Cmd+Option+I**）です。**要素ピッカー**（**Ctrl+Shift+C**）でページ上の要素を指し、**コンソール**タブで `$$("...")` を使ってセレクターをテストします。`$$` は一致するすべての要素を返します。

### 1. `assistantMessage`

アシスタントの返信にピッカーを合わせ、Elements パネルで親をたどり、強調表示された枠が**返信全体**（テキストとコードブロック）を囲み、あなた自身のメッセージは**含まない**要素を探します。その要素に安定した属性を見つけたら、テストします。

```js
$$("YOUR_SELECTOR").length
// 画面上のアシスタントの返信数と同じになるはずです

$$("YOUR_SELECTOR").at(-1).innerText.slice(0, 200)
// 最新の返信の冒頭が表示されるはずです
```

件数が返信数より多い場合は、セレクターが内側の部品（段落やコードブロック）にも一致しています。もっと具体的にするか、親要素を選んでください。Hoseki は最後の一致だけを見るため、断片に一致するセレクターでは最後の断片しか読めません。

### 2. `messageIdAttr`

```js
$$("YOUR_ASSISTANT_SELECTOR").map(e => e.getAttribute("data-message-id"))
```

返信ごとに異なる値になるのが理想です。すべて `null` なら、そのままで構いません。フィールドは変更せず、Hoseki の代替手段に任せます。

### 3. `input`

チャットボックスをクリックし、要素ピッカーで指して、テストします。

```js
const el = document.querySelector("YOUR_SELECTOR");
el.tagName                 // "TEXTAREA" または "DIV"
el.value ?? el.textContent // ボックスに入力した内容が表示されるはずです
```

### 4. `streamingIndicator` と `stopButton`

これらは短い間しか存在しないため、いちばん難しい部分です。コンソールで次を実行してから、長めのプロンプトを送り、出力を見守ります。

```js
const t = setInterval(() => console.log(!!document.querySelector("YOUR_SELECTOR")), 500);
// 終わったら: clearInterval(t)
```

**モデルが生成している間は** `true`、**終わったら** `false` と出力される必要があります。

- **常に存在するもの**（たとえば「読み上げを停止」ボタン）に一致するセレクターでは、Hoseki が永遠に待ち続けます。
- **まったく一致しない**セレクターでは、Hoseki が書きかけの返信に対して動いてしまいます。

### 5. `sendButton`

ボタンが有効になるよう数文字入力してから、`document.querySelector("YOUR_SELECTOR")` が送信ボタンを返すことを確認します。入力欄が空のときは無効になっていることがよくあります。

### 6. `toolBlockSelector`・`toolBlockLangSelector`・`toolBlockBodySelector`

サイトのコードの見せ方は 2 通りあり、どちらかで、この 3 つのフィールドが必要かどうかが決まります。モデルが `tool` ブロックを出力した返信で、次を実行してください。

```js
$$("YOUR_ASSISTANT_SELECTOR").at(-1).innerText.includes("```tool")
```

- **`true`**: フェンスがそのままテキストとして残っています。3 つとも省略して構いません。Hoseki は返信のテキストを検索してブロックを見つけます。
- **`false`**: サイトがフェンスをコードブロックの部品に置き換えていて、バッククォートはページ上から消えています（DeepSeek、Kimi、GLM はどれもこの方式です）。この 3 つがないと、Hoseki はそのサイトでツール呼び出しをまったく認識できません。

見つけるには、`tool` のコードブロックに要素ピッカーを合わせ、強調表示が言語ラベルと本体の**両方**を囲むところまで親をたどってから、テストします。

```js
const blocks = $$("YOUR_BLOCK_SELECTOR");
blocks.length
// 最新の返信に含まれるコードブロックの数と同じになるはずです
const b = blocks.at(-1);

b.querySelector("YOUR_LANG_SELECTOR")?.textContent.trim()
// "tool" になるはずです。ラベル要素がない場合は b.className に
// "language-tool" のようなクラスがないか確認してください。Hoseki は
// それを自動で読み取るので、toolBlockLangSelector は省略できます。

const txt = b.querySelector("YOUR_BODY_SELECTOR").textContent.trim();
JSON.parse(txt)
// エラーなく解析できるはずです
```

注意点:

- **外側の箱を選ぶ。** セレクターがコード部分だけに一致すると、言語ラベルが一致の外にあるため、Hoseki は言語を読み取れません。言語のテキストは 1 語（英数字、`_`、`+`、`-`、20 文字まで）である必要があります。
- **思考パネルを除外する。** 推論モデルは「思考」セクションの中で `tool` ブロックを下書きすることがあり、それを実行させたくはありません。パネルに専用のコンテナクラスがあれば、GLM のアダプターのように除外してください: `".language-tool:not(.thinking-chain-container *)"`
- **コードエディタは行ごとに読まれる。** `textContent` は行を改行なしでつなげます。JSON の文字列の中には生の改行を置けないので、整形された JSON でも問題なく解析できます。
- **長いブロックは途切れることがある。** サイトによっては（GLM の CodeMirror など）、見えている範囲付近の行しか描画しないため、とても長いブロックはページ上で不完全になり、JSON の解析に失敗して何も起きません。ツール呼び出しは小さく保ってください（大きな `write_file` ではなく `apply_patch` を使います）。

`hosekiDiagnose()`（手順 7）は、最新の返信で見つけたコードブロックを言語つきで一覧にし、そこから解析できたツール呼び出しも表示します。

### 7. 再読み込みして確認する

1. `content.js` を保存します（両方のフォルダで）。
2. 拡張機能を再読み込みします。`chrome://extensions`（再読み込みアイコン）または `about:debugging#/runtime/this-firefox`（**再読み込み**）です。
3. チャットのタブを再読み込みします。
4. コンソールを開きます。次のように表示されるはずです。

```text
[Hoseki] content script active on <host> — adapter: <name> (verified: <date>) — run window.__hosekiDebug = true for verbose logs
```

5. 最新の返信にツールブロックがあるページで、コンソールに `hosekiDiagnose()` と入力して実行します。各セレクターが何個の要素に一致したかの表が表示されます。`assistantMessage`、`input`、`toolBlockSelector` は、それぞれ 1 以上になるはずです。空にしてあるセレクター（たとえば使えないサイトでの `streamingIndicator`）は `(error)` と表示されますが、想定どおりです。詳細なレポートには、`codeBlocks`（各ブロックの言語とプレビュー）と `toolBlocksInLatest`（Hoseki が実際に解析できた呼び出し）も含まれます。

そのうえで、モデルにワークスペースの一覧表示を頼み、オーバーレイが表示されて `tool_result` ブロックが入力欄に入ることを確認します。

## 長持ちするセレクターの選び方

- **安定した手がかりを優先する**: `data-*` 属性、`role`、`aria-label`、意味のあるタグ名です。`css-1k3x9a` や `_7436101` のような自動生成のクラス名は、サイトの更新のたびに変わりがちなので避けてください。
- **文言には緩く一致させる**: `[aria-label*='stop' i]` は「Stop」「Stop generating」「stop response」のすべてに一致します（`i` は大文字小文字を区別しない指定です）。
- **UI の言語に注意する。** `aria-label` の文字列はサイトの言語に従います。サイトを英語に設定するか、両方の表記を並べてください。
- **短く保つ。** `div > div > div > span` のような長い連鎖は、レイアウトが少し変わっただけで壊れます。
- **カンマ区切りのリストでバリエーションをカバーする**: `"[data-role='assistant'], .message-assistant"`。
- **アダプターに日付を入れる。** `verified` フィールドに最後に確認した日付（`"YYYY-MM-DD"`）を入れておけば、どれくらい古いかが分かります。
- **ブラウザの対応状況に注意する。** `:has()` は Chrome 105 以降、Firefox 121 以降が必要ですが、Firefox ビルドの対象は 115 以降です。`:has()` に頼るアダプター（DeepSeek のもの）は、Firefox 115〜120 では動きません。

## 新しいサイトを追加する

1. `extension/chrome/` と `extension/firefox/` の**両方**の `content.js` にある `ADAPTERS` に、ホスト名をキーとしてエントリを追加します（ドメインごとに 1 つのキーです。このガイドの冒頭を参照してください）。
2. サイトの URL パターン（たとえば `https://chat.example.ai/*`）を、**両方の** `manifest.json` の `content_scripts[0].matches` に追加します。Firefox のマニフェストがホスト権限としてもサイトを列挙している場合は、そちらにも追加してください。
3. 拡張機能とチャットのタブを再読み込みし、上の手順を順に行います。

## トラブルシューティング

| 症状                                                 | 確認すること                                                                               |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| コンソールに `[Hoseki] content script active` が出ない | サイトのホスト名がアダプターのキーに一致していないか、URL がマニフェストの `matches` にない |
| その行は出るが、モデルがツールブロックを出力しても何も起きない | 手順 1 をやり直してください。`assistantMessage` が最新の返信に一致していない可能性があります。次に手順 4 です。生成中の判定が張り付いていると、Hoseki は待ち続けます |
| `assistantMessage` は正しそうなのに、やはり何も起きない | `$$("YOUR_SELECTOR").at(-1).innerText.includes("```tool")` を実行してください。`false` なら、サイトがフェンスをコードブロックの部品の中に隠しているので、3 つの `toolBlock*` フィールドが必要です（手順 6）。そのうえで `hosekiDiagnose().toolBlocksInLatest` を確認します |
| `hosekiDiagnose()` にコードブロックは出るが `lang` が空 | `toolBlockLangSelector` がブロックの中の何にも一致していません。修正するか、ブロックに `language-xxx` クラスがないか確認してください（手順 6） |
| 短いツール呼び出しは動くが、長いものは何も起きない   | サイトが長いコードブロックの一部しかページ上に描画しておらず、JSON が不完全になっています。呼び出しは小さく保ってください（大きな `write_file` ではなく `apply_patch`） |
| モデルの思考中の内容からツール呼び出しが実行される   | ブロックのセレクターが「思考」パネルの中にも一致しています。`:not(...)` で除外してください（手順 6） |
| コンソールに `[Hoseki] no adapter for <host>` が出る  | そのホストにアダプターのキーがありません。追加してください。キーはサブドメインには一致しますが、別のドメインやワイルドカードには一致しません |
| オーバーレイが「チャット入力欄が見つからない」と表示する | `input` を修正してください（手順 3）                                                       |
| 結果は入力欄に入るが、送信されない                   | 想定どおりです。デフォルトは半自動なので、送信は自分で押します                             |
| 完了判定を今すぐやり直したい                         | ページのコンソールで `window.dispatchEvent(new Event("hoseki:trigger"))` を実行します（生成中は引き続き待ちます） |