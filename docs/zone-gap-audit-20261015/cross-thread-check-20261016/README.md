# 森林側の既存実機検査との照合・重複除外（2026-10-16）

**既存のArcGIS実機結果を再利用し、一括再検査は依頼しません。** 森林側で描画できた同梱19系レイヤはv2026.2由来で、今回取得したv0.3同梱版も全19行の図形BLOB・属性・FID・列定義・図形型・SRSが公開19系版と完全一致しました。ファイル全体のSHA-256が異なるのは、スタイル表等を含む別ファイルだからです。

また、先行試験の計画区020と拡張21件中の020は、**図形BLOBが完全一致**しました。属性・レイヤ構成は異なるので同一ファイルとは呼びません。先行020のESRI検査結果を既存証拠として再利用し、020を新規の図形候補として数え直しません。

調査範囲は両リポジトリのmain、森林側PR #3/#4、関連Releaseの説明・添付、以前受領した資料です。別チャットの本文を直接読む機能はこの環境にありません。GitHub未反映の追加結果は「未照合」とし、検査が行われていないとは断定しません。

## 後続の実機結果を受領

この照合後、2026-10-16の利用者申し送りで、v0.3のFile GDB変換と、拡張21候補に対するESRI検査も実施済みと確認しました。拡張版の残件は米代川025の自己交差1件です。公開GitHub説明の「未実施」は更新待ちとして扱います。[追加実機結果と19系への申し送り](../forest-runtime-handoff-20261016/README.md) を優先してください。

## 既存結果と使える範囲

| 対象 | 既存の実機・処理記録 | 今回の同一性確認 | 重複を避けた扱い |
|---|---|---|---|
| 森林の図形型比較コピー3レイヤ | ArcGIS Pro 3.7.1で158/44/20件の図形認識・描画・日本語属性、計画区のEPSG:6668、拡大縮小・同時表示を確認 | 利用者提供比較JSONと公開v0.3検証JSONで全222行の全列ハッシュが一致 | 認識・描画・当該属性の基本確認は再利用。全体を未確認に戻さない |
| 森林パッケージ同梱の19系区域 | 森林側のArcGIS報告に「同梱の平面直角座標系GeoPackageは図形として描画できた」。利用者画面も19行を表示 | v0.3同梱版と正式v2026.2で全列・図形BLOB・列定義・型・SRSが一致。スタイル表は異なる | 19系の基本読込・描画の既存証拠を再利用。ファイルSHAの不足だけで再描画を依頼しない |
| 先行の計画区020候補 → GDB `iwate01` | ESRI方式Check Geometry、`NO_PROBLEMS_FOUND`、問題0行。実機ログ・画面を要約したJSONあり | 先行GPKGの020と拡張版020の図形BLOBが完全一致。属性は異なる | 先行020の実機結果は検査済み証拠。拡張版GDBの出力条件まで確認済みとはしない |
| 拡張候補21件および対照21件 | QGIS 3.40.6 Check validity、GEOS方式・リング自己交差を無視しない設定。各21件有効 | 添付結果JSONの設定・対象を確認 | 同じ入力・方式の検査をここから繰り返さない。GUI描画やESRI方式とは区別 |
| 拡張21候補のGDB出力とESRI検査 | 後続の利用者申し送りで実施済み。米代川025の自己交差1件が残る | コード025を公開候補の属性と照合。今回の元GDB JSON・全ログは未受領 | 21件の再実行は依頼せず、025の解析結果を森林側の本流・Claude側から受領する |
| 19系の調査用候補・差分・接続線コピー | GDAL、SQLite、型宣言、16,248件の同一性は検証済み | 既存の森林計画区や正式19系とは別の調査用レイヤ | 使用する新規レイヤ固有の確認が必要な場合だけ対象を絞る。原本・コピー17レイヤの一括再検査は行わない |

森林側の集約・精度処理の結果を、19系自体の穴・所属・境界が正しいという根拠にはしません。19系の形状に関する結論は既存の19系独自監査を維持します。

## 19系レイヤの直接比較

森林 `review-v0.3-20261015` のZIPを取得し、公開APIのasset digestと実測SHA-256を照合してから、同梱19系GeoPackageだけを別名で展開しました。双方をSQLiteの読み取り専用で開いて比較しています。

| 項目 | 正式v2026.2 | 森林v0.3同梱 |
|---|---|---|
| ファイルSHA-256 | `9392e5e3fecedbab7ba774dc89c81bc353c265d16d66a1c86f6e341b5946eafc` | `7f8b35c97d4796cdcbb7a203e5c07c68cd6595597ee5e1f284f9b809587c00d3` |
| 件数 | 19 | 19 |
| FIDを含む全列値ハッシュ | `70fdd44ba879e4afa53d8fa089983899774532233b937d7a77571574d75aeb23` | 同左 |
| fid順の図形BLOB連結ハッシュ | `23fa2d62f395ce192857e2a69444e639e24d4f89c30f4da17d0976b0acb3a02b` | 同左 |
| SQL・GeoPackage図形型 | MULTIPOLYGON | MULTIPOLYGON |
| EPSG | 6668 | 6668 |
| スタイル表の行数 | 1 | 2 |

列の並びを名前で正規化し、値の型と長さを区別した行ハッシュを並べ替えて全列値ハッシュを求めます。重複行の数とFIDも保持します。図形BLOBの連結ハッシュは森林側の公開検証方法とも一致しました。[直接比較結果](zone-layer-comparison.json) を参照してください。これはファイル全体の一致でも、ユーザー画面で開いた実ファイルのSHAを逆算したものでもありません。

## 計画区020の重複確認

先行候補 `district020_precision_1e9` と拡張候補 `districts_upstream_trial` の `district_code='020'` を比較しました。自動FIDの偶然の一致を識別根拠にしていません。

- 生の図形BLOB SHA-256は両方 `e528dc86bbb5ab7f41a801bf24b9ddc23ccd523cc274e1917a36da8885eb75b8`。
- 正規化座標も許容差0で完全一致。EPSG:6668、MULTIPOLYGON、Z/Mなしです。
- 拡張版には `source_district_fid=20`、流域情報等が追加されています。全属性・列定義は同一ではありません。
- 既存実機結果は先行GDB `iwate01` に対するものです。入力GPKGとGDBのバイナリ一致、拡張版GDBの格子・出力条件、全国・他20件を保証するものではありません。

[図形と属性の比較](pilot-expanded-020-comparison.json)、[選択条件付きの全列比較](selected-020-content-comparison.json)、公開ZIPから取得した[既存実機結果](arcgis-district020-runtime-result.json) を保存しました。

## 過去の未了Issueとの区別

19系側の [Issue #15](https://github.com/yo-1/japan-plane-rectangular-cs-zones/issues/15) と [Issue #18](https://github.com/yo-1/japan-plane-rectangular-cs-zones/issues/18) は、旧v2026.1の系・都道府県・市町村3種類の確認や、過去のQGIS試験ファイルとのSHA照合を対象にしています。今回のv2026.2・19系の証拠だけで全受入条件を満たしたとは判定せず、Issueは閉じません。同時に、古い未了記載をそのまま新しい再検査依頼に転記せず、既存ログの追加照合を優先します。

## 根拠と再実行

- [森林側のArcGIS報告（固定コミット）](https://github.com/yo-1/japan-forest-planning-zones/blob/d6474648736fa76c15e06a4b32b9f9861c09664b/docs/ARCGIS_PRO_20261015.md)
- [森林PR #4](https://github.com/yo-1/japan-forest-planning-zones/pull/4)、[v0.3](https://github.com/yo-1/japan-forest-planning-zones/releases/tag/review-v0.3-20261015)
- [先行試験](https://github.com/yo-1/japan-forest-planning-zones/releases/tag/upstream-precision-pilot-20261015)、[拡張試験と実機結果の添付](https://github.com/yo-1/japan-forest-planning-zones/releases/tag/upstream-precision-expanded-20261015)
- [根拠のURL・ハッシュ・記録範囲](evidence-index.json)

```bash
python scripts/compare_gpkg_layer_content.py \
  --left output/gap-inputs/plane_rectangular_zones_2026.gpkg \
  --right output/github-crosscheck-20261016/forest-v03-plane_rectangular_zones_2026.gpkg \
  --layer plane_rectangular_zones_2026 --output output/new-zone-comparison.json
python scripts/compare_gpkg_layer_content.py \
  --left output/github-crosscheck-20261016/pilot-upstream_precision_pilot.gpkg \
  --right output/github-crosscheck-20261016/expanded-expanded_precision_trial.gpkg \
  --layer district020_precision_1e9 --right-layer districts_upstream_trial \
  --key-field district_code --key-value 020 --output output/new-020-comparison.json
```

元ファイルは各Releaseから別フォルダへ取得し、公開ハッシュを照合して展開してください。既存出力は上書きしません。この比較スクリプトは標準ライブラリだけで動き、ArcGISや新しい形状検査を実行しません。既存結果の照合を目的とします。
