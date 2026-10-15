# 調査用GeoPackageの図形型比較コピー（2026-10-15）

森林側で得られたSQL図形型宣言の知見を踏まえ、19系調査成果物の**比較用コピー5ファイル・9レイヤ**を作成しました。公開v2026.2や元の調査用GeoPackageは変更していません。補修は0件です。ArcGIS上での動作は未確認です。

| 比較用ファイル | レイヤと件数 | SQL・GeoPackage図形型 |
|---|---|---|
| `candidates-typed.gpkg` | `void_candidates` 13、`enclosing_rings` 13、`stage_differences` 293 | POLYGON |
| 同上 | `zone_reference` 19 | MULTIPOLYGON |
| `differences-typed.gpkg` | `differences` 1 | POLYGON |
| `exterior-screen-typed.gpkg` | `connectors` 15,897 | LINESTRING |
| `source-ring-evidence-typed.gpkg` | `evidence` 6 | POLYGON |
| `vector-context-typed.gpkg` | `context_polygon` 4、`context_multipolygon` 2 | POLYGON、MULTIPOLYGON |

元の `context` はPolygonとMultiPolygonが混在するため、実体型で2レイヤに分割しました。型変換や図形の再シリアライズは行わず、元のFIDを各レイヤ内に保持しています。

## 検証結果

全16,248件について、FID・図形バイナリを含む全列値の型・長さ付きSHA-256を比較しました。分割したレイヤも再結合して比較し、欠落・重複がないことを確認しました。出力を閉じて再度開いた後にも一致を確認し、元ファイルのSHA-256も変わっていません。

SQLiteの整合性・外部キー検査、SRSメタデータの一致を確認しています。別にGDALで全9レイヤを読み戻し、件数・図形型・EPSG:6668・有効で空でない図形を確認しました。

- [全列値の比較記録](comparison-verification.json)
- [GDAL読み戻し結果](gdal-readback.json)
- [今回作成物のSHA-256](SHA256SUMS.txt)

比較コピーではSQL宣言・図形型メタデータのほか、レイヤ名・説明・更新時刻・範囲を調整しています。コアSRS情報と全フィーチャ列は保持し、スタイル・補助テーブル・空間インデックスはコピーしません。元ファイルとファイル全体のハッシュが同じになる処理ではありません。

## 再実行

リポジトリのルートで、元の調査・岩礁追跡調査の成果物を用意して実行します。依存関係は既存の `scripts/geometry_audit/requirements.txt` と同じです。既存出力を上書きしないため、未作成の出力先を指定してください。

```bash
.venv/bin/python scripts/prepare_arcgis_comparison.py \
  --input output/zone-gap-audit-20261015/candidates.gpkg \
  --input output/n03-municipality-recheck-20261015/differences.gpkg \
  --input output/zone-exterior-screen-20261015/exterior-screen.gpkg \
  --input output/rock-followup-20261015/source-ring-evidence.gpkg \
  --input docs/zone-gap-audit-20261015/rock-followup/vector-context/vector-context.gpkg \
  --output output/arcgis-comparison-new
```

入力は読み取り専用で開きます。空レイヤ、NULL・空・不正な図形、GeometryCollection、Z/M付き図形などは、曖昧な宣言にせずエラーとして停止します。更新時刻が含まれるので再実行時のファイルハッシュは変わり得ます。各回の `comparison-verification.json` で全列値の同一性を確認してください。

大きなGeoPackage本体はGit管理外の `output/arcgis-comparison-20261015/` にあります。本報告書のリンクはダウンロード用添付ではありません。公開Releaseへの追加は行っていません。

## ArcGISで残る実機確認

1. 使用するGeoPackage本体のSHA-256とArcGIS Proのバージョンを記録します。利用者画面にあった公開19系ファイルの版・SHA-256も別に特定します。
2. 新しいマップへ比較コピーを追加し、上表の9レイヤがフィーチャとして認識されること、件数、図形・属性・候補IDの表示を確認します。
3. 必要な形状検査を実行し、ツール名・設定・エラー件数を記録します。修復ツールは実行しません。
4. 同じ位置・縮尺で元の調査用データと比較し、表示の違いがあればファイル名・候補ID・表示条件を記録します。

GDALでの成功だけでArcGISの互換性や検査完了を確定しません。岩礁付近2件の地物の意味・法的所属は、この型宣言比較では確定できず、原典維持・補修保留です。
