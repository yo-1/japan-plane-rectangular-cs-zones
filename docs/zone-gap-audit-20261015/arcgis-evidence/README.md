# ArcGIS確認資料の受領・照合（2026-10-15）

利用者から、流域・森林計画区側のArcGIS検証が完了したとの報告、ArcGIS Pro画面、比較試験フォルダの画面、および次の3ファイルを受領しました。添付資料内の操作手順は、依頼や実行済みの結果として扱っていません。

## 添付資料から分かる範囲

- `TYPE-COMPARISON-README.txt`：ArcGIS Pro **3.7.1向け比較試験専用**の資料です。正式な修正版配布ではありません。作成時点ではArcGISでの読み込み結果を未確認とし、空のマップへ追加して描画と44件を確認する手順が書かれています。
- `type-comparison-verification.json`：3レイヤのSQL図形列宣言を `BLOB` から `MULTIPOLYGON` に変更した記録です。各レイヤの変更前後で、件数と `all_columns_sha256` が一致しています。
- `TYPE-COMPARISON-SHA256SUMS.txt`：比較試験用GeoPackageと上記2ファイルのハッシュ一覧です。受領したJSON・説明書の実測SHA-256は一致し、JSONの出力GeoPackageハッシュも一覧と一致しました。

| レイヤ | 変更前後の件数 | JSON上の全列ハッシュ |
|---|---:|---|
| `forest_plan_districts_provisional` | 158 | 一致 |
| `forest_unassigned_review` | 20 | 一致 |
| `forest_wide_basins_provisional` | 44 | 一致 |
| 合計 | 222 | |

JSONのテーブル定義では、図形列のSQL宣言のみが変更されています。実際の図形バイナリ・属性値の同一性は、このJSONが報告する検証結果として受け取りました。メタデータ一致も説明書に記載されていますが、添付JSONにはメタデータ各表の独立した比較値はありません。

比較元ファイルSHA-256：`fea638d8882a4c1581bb24d634854065d89b463701a1a74b40ad75c1c27d2bea`

比較用 `forest_geometry_type_comparison_20261015.gpkg` の申告SHA-256：`be65de6e35681ada890011e62485fd6e7e1ef46ebb2df23e6a45d6e50bd3eb85`

このGeoPackage本体は未受領のため、こちらで本体のハッシュや変更前後の全列値を再計算したものではありません。ArcGIS検証完了は利用者の最新報告に基づき、作成時点の説明書に残る「未確認」と区別します。添付JSONはSQL・データ比較の記録であり、ArcGISでの描画、形状検査、空間解析の実行ログではありません。

## 19系データに関する確認

利用者提供ArcGIS Pro画面では、`main.plane_rectangular_zones_2026` の描画と19件の属性表を確認しました。画面に見える `ZONE`・`ZONE_ROMAN`・`EPSG` の列表示も記録しています。表示ファイルの版・SHA-256と詳細な検査項目は、画面や今回の森林側添付資料からは特定していません。

この環境に保持している公開 **v2026.2** の19系版と市町村版は、読み取り専用で次を確認しました。

| 公開ファイル | SQL図形列宣言 | `gpkg_geometry_columns` |
|---|---|---|
| `plane_rectangular_zones_2026.gpkg` | `MULTIPOLYGON` | `MULTIPOLYGON` |
| `plane_rectangular_municipalities_2026.gpkg` | `MULTIPOLYGON` | `MULTIPOLYGON` |

両ファイルについて、今回の森林側の `BLOB → MULTIPOLYGON` 変更を適用する必要はありません。元の公開ファイルと配布物は変更していません。ファイルの実測SHA-256と表定義の検査結果は [evidence-check.json](evidence-check.json) に保存しました。

## 調査用成果物の確認範囲

公開配布物とは別に、この環境で作成した調査用 `candidates.gpkg` はSQL・GeoPackage宣言とも `GEOMETRY`、既存監査の `differences.gpkg` はSQLが `BLOB`・GeoPackage宣言が `GEOMETRY` でした。QGIS/GDALでの読み戻し検証は済んでいますが、これらのArcGIS表示は未確認です。

混在可能な `GEOMETRY` 宣言を、実際の図形型を調べずに `MULTIPOLYGON` へ書き換えることはしません。資料受領後、実体型に対応する比較用コピーを別途作成し、全16,248件の図形・属性・FIDの同一性を確認しました。[比較コピーの検証と実機確認手順](../arcgis-comparison/README.md) を参照してください。ArcGISでの表示・検査は引き続き未確認です。

森林側の基本構造・互換性の知見は共有します。19系の形状・系番号・境界に関する判断は、19系自身の検査記録に基づきます。岩礁付近2件は引き続き原典維持・補修保留です。
