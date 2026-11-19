# probeと正式v2026.3の実GUI検証を再実行する

Linuxクラウドで使用した手順です。Docker、Git、GitHub CLI、uv、Python 3.12が必要です。QGISはコンテナ内で動きます。入力データは読み取り専用、出力は別ディレクトリです。大きなZIPやGPKGはGitに保存しません。

probe v0.1.4の未変更ソースを使います。`run_recipe`も実行許可を必要とするため、この専用セッションだけ許可して、ここにあるレシピを実行します。本番プロファイルに常設しません。

リポジトリルートで、未作成の試験先を選んでください。以下のパスはこのクラウドの例です。

```sh
probe_audit_root=/workspace/scratch/probe-v2026-3-replay
mkdir -p "$probe_audit_root/downloads" "$probe_audit_root/probe-source" "$probe_audit_root/recipes"
gh release download v2026.3 --repo yo-1/japan-plane-rectangular-cs-zones \
  --pattern '*.zip' --dir "$probe_audit_root/downloads"
python scripts/probe_runtime_audit/prepare_inputs.py "$probe_audit_root"
git -C /workspace/qgis-dev-probe archive a4f54e96877bf2782b52ec302bca5ba18c1cbb9b | tar -x -C "$probe_audit_root/probe-source"
cp scripts/probe_runtime_audit/bootstrap.py scripts/probe_runtime_audit/check_live.py \
  scripts/probe_runtime_audit/run_in_container.py "$probe_audit_root/"
cp scripts/probe_runtime_audit/view_audit.py "$probe_audit_root/recipes/"
UV_CACHE_DIR=/tmp/probe-audit-uv uv venv "$probe_audit_root/mcp-venv" --python python3.12
UV_CACHE_DIR=/tmp/probe-audit-uv uv pip install --python "$probe_audit_root/mcp-venv/bin/python" \
  -e "$probe_audit_root/probe-source"
```

QGISイメージの取得と実行です。Dockerの接続先は管理環境の設定に合わせてください。このクラウドでは `/var/run/docker.sock` を使用しました。ネットワークアクセス・ローカルソケットの制限があるサンドボックスでは、承認された実行権限が必要です。

```sh
docker pull qgis/qgis@sha256:4389d5ed64d7fc89647ac5cea45f97274a7e85b35d8bb7869810be297667ed79
docker run --rm --init --network none --shm-size=1g --entrypoint /usr/bin/python3 \
  --mount "type=bind,src=$probe_audit_root,dst=/work" \
  --mount "type=bind,src=$probe_audit_root/data,dst=/work/data,readonly" \
  --mount "type=bind,src=$probe_audit_root/mcp-venv/lib/python3.12/site-packages,dst=/mcp-site,readonly" \
  --mount type=bind,src=/usr/share/fonts,dst=/usr/share/fonts/host,readonly \
  qgis/qgis@sha256:4389d5ed64d7fc89647ac5cea45f97274a7e85b35d8bb7869810be297667ed79 \
  /work/run_in_container.py
```

`results/`へ応答JSON・画像・Processing出力・終了状態を保存します。既存の結果がある場合は停止します。終了後の `lifecycle.json` でQGIS終了コード0、Xvfb停止、endpoint削除を確認してください。入力3件の実行前後SHAは `input-manifest.json` と照合してください。

- `prepare_inputs.py`：公開ZIPの固定SHAとCRCを確認し、GeoPackageとメタデータを準備します。
- `bootstrap.py`：専用プロファイルのQGISでprobeとProcessingを起動します。
- `check_live.py`：実MCP経由で表示・属性・レイヤ操作・Processingを検査します。
- `view_audit.py`：保存済みの分類・ラベル設定の確認、表示範囲の切替、合成入力の作成、アクション列挙の診断を行うレシピです。
- `run_in_container.py`：Xvfb/QGIS/クライアントの起動・終了を管理します。

既知のアクション列挙の欠落は、他の試験を止める一律のアサーションにせず診断値として保存します。表示・Processing完了と総合判定を分け、アクション列挙に欠落があれば `overall_status=partial_failure` を保存して非ゼロ終了します。既存の実応答の欠落判定にもこの分類関数を実行し、不合格を確認しました。
