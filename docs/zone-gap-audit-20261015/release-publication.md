# 検証用Releaseの再生成・公開

クラウド環境では通常のGitHub APIにプラットフォーム認証が自動で補われるため、APIの成功だけでは登録したアップロード用トークンの有効性を確認できませんでした。添付先の `uploads.github.com` は401を返しました。旧設定の参照やトークンそのものが原因だとは確定していません。

GitHub Actionsの `Publish zone gap investigation` を手動実行すると、ハッシュ固定のN03・v2026.2から調査データを再生成し、検証後に既存の調査用下書きRelease `zone-gap-audit-20261015` へ添付します。正式データ・原典の補修は行いません。個人トークンの登録は不要です。

- 再生成は読み取り権限で実行し、添付・公開のジョブだけに `contents: write` を与えます。
- mainからの手動実行のみ許可し、他のReleaseや任意のタグを操作する入力は設けていません。
- 入力SHA-256、調査成果物、全テスト、比較コピーの全列値、ZIP内全ファイルを検証します。失敗すれば公開しません。
- 既存の6件のベクトル比較図形は `context-features.geojson` から復元し、初回記録の図形BLOB・属性・FIDのハッシュと一致することを検証します。画像やベクトルの最新版への置き換えはしません。
- 添付後にGitHub側のSHA-256とサイズを照合してからPre-releaseとして公開し、正式最新版v2026.2は維持します。同名添付の上書きは行いません。

再生成時刻や差分のFID順序により、初回ZIPとハッシュが異なる場合があります。今回のZIP内の `PACKAGE-MANIFEST.json`、添付 `SHA256SUMS.txt` と `package-verification.json` が今回の生成物を特定します。`docs/` にある初回検証記録と、新たな `output/` の結果を区別してください。

GitHubのActions画面から上記ワークフローを選び、mainで「Run workflow」を実行できます。CLIでは次を使います。

```bash
gh workflow run publish-zone-gap-audit.yml --ref main
```

失敗時はActionsログを確認してください。検証済みZIPはActions artifactにも14日間保持します。再実行時に既存添付のハッシュが異なる場合は停止するので、その状態を調べずに添付を削除しないでください。
