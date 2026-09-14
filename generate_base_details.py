"""
既存36件の論文詳細解析を一括生成するスクリプト
初回だけ GitHub Actions から手動実行してください。
"""
import google.generativeai as genai
import json, re, os, time
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
model = genai.GenerativeModel("gemini-1.5-flash")

BASE_PAPERS = [
  {"id":"s1","title":"腰椎脊柱管狭窄症：除圧単独 vs 除圧＋固定 SSSS試験5年RCT","journal":"Bone & Joint, 2024","overview":"スウェーデン多施設RCT。変性すべりの有無にかかわらず247例を除圧+固定群 vs 除圧単独群に無作為化し5年追跡。","results":"固定追加による上乗せ効果なし。二次転帰3項目では除圧単独群が有意に優れた。2年MRIで固定群は再狭窄が有意に多かった。","conclusion":"変性すべり合併例でも固定の上乗せ効果がないことを示す一連のRCTの中で、高侵襲・高コストな固定術の適応を厳格化すべきという国際的議論が続いている。"},
  {"id":"s2","title":"脊椎後方固定術への術野バンコマイシン粉末：6RCT 2140例でSSI予防効果なし","journal":"JBJS Specialty Update / Spine誌, 2026年","overview":"6件のRCT・2140例を解析したメタ解析。","results":"深部・浅部・総SSIのいずれにも有意差なし。","conclusion":"ルーチン投与の根拠が乏しいことが改めて示された。"},
  {"id":"s3","title":"ロボット支援脊椎手術 vs CTナビゲーション：クラスIエビデンスでロボットの精度優位性が確立","journal":"EFORT Open Rev / Musculoskeletal Surg, 2026年","overview":"フリーハンド・ナビゲーション・ロボットをクラス別に評価した系統的レビュー・メタ解析。","results":"ロボットはフリーハンド比OR 2.74倍、ナビゲーション比OR 2.36倍の許容スクリュー設置率。","conclusion":"クラスIエビデンスでロボット支援の精度優位性が確立。"},
  {"id":"s4","title":"VBT（椎体テザリング）術後の肺合併症：60例中36.7%・気胸が最多（30.4%）","journal":"JBJS, 2026年6月","overview":"単施設でVBTを施行した60例の周術期肺合併症を後向き評価。","results":"36.7%に肺合併症が発生。最多は気胸（30.4%）。","conclusion":"VBTは前胸郭経由アプローチを要するため肺合併症が格段に高頻度。専門施設への集約化が不可欠。"},
  {"id":"s5","title":"胸腰椎バースト骨折：術前CT Hounsfield値（HU値）が術後3ヶ月の椎体再虚脱を予測","journal":"Int J Spine Surg, 2026年9月","overview":"後方固定術施行患者を対象とした後向きコホート研究。術前CTのHU値と術後3ヶ月椎体再虚脱の関連を解析。","results":"低HU値が術後3ヶ月椎体再虚脱の独立した予測因子として同定。","conclusion":"CTのHU値は骨粗鬆症スクリーニングの簡便な代替指標として術前評価に活用可能。"},
  {"id":"sh1","title":"FIMPACT試験10年：肩峰下除圧術（ASD）は偽手術・運動療法と比較して臨床的に有意差なし","journal":"BMJ, 2025年12月","overview":"フィンランド多施設三群RCT（ASD群・診断的関節鏡群・運動療法群）210例の10年追跡。","results":"10年時点でのASDの疼痛・機能は偽手術・運動療法と比較して有意差なし。","conclusion":"ASDが孤立性インピンジメント症候群には有効でないという結論が最高レベルエビデンスで確定。"},
  {"id":"sh2","title":"腱板断裂：保存療法 vs 腱板修復 15年RCT追跡で同等転帰（Moosmayer et al.）","journal":"JBJS What's New in Shoulder & Elbow, 2026年7月","overview":"小〜中等大全層腱板断裂103例対象RCTの15年追跡。保存療法群51例中15例が後に手術に移行。","results":"15年時点でConstant・ASES・SF-36・患者満足度は両群間で有意差なし。","conclusion":"長期では保存療法でも同等転帰が得られうるというエビデンスが蓄積。"},
  {"id":"sh3","title":"Bankart修復＋Remplissage：単独と比べ再発率9分の1・前方挙上も有意増加","journal":"JBJS What's New in Shoulder & Elbow, 2026年7月","overview":"Engaging Hill-Sachs病変を有する前方肩関節不安定症に対するBankart＋Remplissage vs Bankart単独の比較メタ解析。","results":"再発率が9分の1に低下。前方挙上が有意に増加（平均差1.97°、p<0.001）。","conclusion":"Hill-Sachs病変を伴う前方不安定症ではRemplissage追加が推奨される。"},
  {"id":"sh4","title":"aTSA/rTSA長期生存率：aTSA 15年91%・rTSA 10年94%（4国際レジストリ＋メタ解析）","journal":"SAGE誌, 2026年7月","overview":"4国際レジストリ＋7ケースシリーズを統合したaTSA/rTSA生存率メタ解析（≧13年追跡）。","results":"aTSA 13年生存率91.50%・15年生存率90.82%。rTSA 10年生存率94%。","conclusion":"両術式とも長期高生存率を達成するが、インプラントブランド・デザインが生存率を左右する。"},
  {"id":"sh5","title":"外傷性前方肩不安定症 ESSKA-ESA公式コンセンサス Part2：年齢・初回/再発別の治療・RTS推奨","journal":"KSSTA, 2026年6月","overview":"欧州9カ国15人のステアリンググループによる構造化デルファイ法。23の臨床質問を評価。","results":"20歳未満コンタクトアスリート（初回脱臼）：早期手術を強く推奨。","conclusion":"前方不安定症の年齢×初回/再発×活動性に基づく意思決定アルゴリズムが初めて標準化。"},
  {"id":"sh6","title":"Latarjet術後コラコイド骨吸収（CRDL分類）：高度吸収（Grade 3）で疼痛増加・機能低下","journal":"Am J Sports Med, 2026年3月","overview":"関節鏡的Latarjet術後コラコイドグラフト吸収の臨床的影響を再評価。新CRDL分類システムを開発。","results":"Grade 3（高度吸収）でASESスコアが有意に低く、VASスコアが有意に高かった。","conclusion":"「コラコイド吸収は臨床的に無意味」という従来の定説に疑問が投じられた。"},
  {"id":"sh7","title":"修復不能巨大腱板断裂：SCR vs rTSA 合併症率（SCR 3.5% vs rTSA 10.8%）で有意差","journal":"Clin Orthop Surg, 2026年6月","overview":"関節炎を伴わない修復不能腱板断裂に対するSCRとrTSAを比較した7件・430例のメタ解析。","results":"機能・疼痛・可動域は両群で有意差なし。SCRの全合併症率が有意に低かった（3.5% vs 10.8%）。","conclusion":"機能・疼痛は同等でありながらSCRの合併症率が低く、若年患者では関節温存的SCRが第一選択となりうる。"},
  {"id":"sh8","title":"rTSA revision後の再revision：NJR 685例で再revision率34%・術者中央値4例/10年","journal":"PMC, 2026年7月","overview":"英国NJR（26403例・平均追跡4.9年）からrTSA revision 685例を同定し分析した研究。","results":"再revision率34%。revision手術を行った術者244名の中央値は4例/10年と極めて低量。","conclusion":"rTSA revisionは高難度手術でありながら多くの術者が少数例しか経験しない実態が判明。"},
  {"id":"el1","title":"SCIENCE試験：小児転位性肘内側上顆骨折への手術は機能的転帰を改善しない（The Lancet RCT）","journal":"The Lancet, 2026年1月","overview":"英国・豪州・NZ 59施設・334例（7〜15歳）の多施設RCT。ギプス固定群 vs 手術固定群を比較。","results":"12ヶ月PROMs（PROMIS上肢）に有意差なし。手術群で術中合併症14件・再手術7例。","conclusion":"「手術で骨を固定すべき」という積極派の意見を否定する初の大規模RCT。"},
  {"id":"el2","title":"SOFIE RCT：高齢者（75歳以上）肘頭骨折 手術 vs 保存療法 12ヶ月DASHスコアに差なし","journal":"JBJS, 2025年","overview":"豪州・NZ 24施設の多施設RCT。75歳以上の急性転位閉鎖性肘頭骨折を手術群 vs 保存療法群に割付。","results":"12ヶ月DASHスコアに手術群・保存療法群で有意差なし。","conclusion":"高齢者肘頭骨折では保存療法が手術と同等の12ヶ月機能転帰をもたらす合理的選択肢。"},
  {"id":"el3","title":"Tommy John手術失敗後のInternal Brace Revision修復：投手11例全員が術前レベル以上に復帰・平均9ヶ月","journal":"OJSM, 2026年4月","overview":"UCL再建術失敗後にRevision UCL repair with Internal Braceを施行したプロ・大学投手11例の後向き研究。","results":"全11例が術前レベル以上への競技復帰を達成。競技復帰までの平均期間は9ヶ月。","conclusion":"UCL再建術失敗後のRevision手術はもともと転帰不良とされてきたが、Internal Brace修復がこの常識を覆す可能性を示した。"},
  {"id":"el4","title":"遠位上腕二頭筋腱部分断裂（グレード<50%）：保存療法で6ヶ月83%が完全回復","journal":"JSES, 2026年1月","overview":"部分遠位上腕二頭筋腱断裂に対する保存療法の効果を評価したケースコントロール研究。","results":"グレード<50%の部分断裂への保存療法で6ヶ月時点に83%が完全回復を達成。","conclusion":"部分遠位上腕二頭筋腱断裂は断裂深度50%以上・保存療法6ヶ月無効例に手術適応を絞る基準が示された。"},
  {"id":"ha1","title":"指尖部切断再接着：7278断指メタ解析で生存率中央値85%・2本静脈吻合が成功予測因子","journal":"Eur J Plast Surg, 2026年3月","overview":"25研究・7278断指を対象としたメタ解析。生存率・機能転帰の予後因子を評価した。","results":"生存率50〜100%（中央値85%）。鋭利損傷・短い虚血時間・2本静脈吻合が高い生存率と関連。","conclusion":"「温虚血6時間」という従来の制限は実証的根拠が薄く、2本静脈吻合が重要技術として再確認された。"},
  {"id":"ha2","title":"舟状骨骨折：YOLOv8ベースAI診断が単一PA方向X線で高精度検出（mAP@0.75=0.98）","journal":"Electronics, 2026年6月","overview":"10年間の手関節X線データを用いてYOLOv8アルゴリズムで舟状骨を自動セグメンテーション・骨折検出するフレームワークを開発・検証した研究。","results":"舟状骨の自動セグメンテーション・骨折検出において高精度を達成（mAP@0.75=0.98）。","conclusion":"救急外来での多方向撮影困難例での見逃しリスクを大幅低減できる可能性がある。"},
  {"id":"ha3","title":"ゾーン2屈筋腱修復後：能動的早期運動（CAM）が受動的早期運動（EPM）より全時点で有意に優れる（RCT）","journal":"2026年","overview":"ゾーン2全層屈筋腱断裂40例をCAM群とEPM群に無作為割付し術後6週・12週でTAM・握力・DASHスコアを比較したRCT。","results":"CAM群がEPM群より全評価時点でTAM・握力・DASHにおいて有意に優れた。12週でCAM群の80%が「優」。","conclusion":"CAMはEPMより有意に優れた早期機能回復をもたらすことが初めてRCTで確認された。"},
  {"id":"ha4","title":"高齢者橈骨遠位端骨折（高麻酔リスク）：VLP固定とギプス固定で機能的転帰が同等","journal":"PMC, 2026年5月","overview":"麻酔ハイリスク高齢患者のDRFに対するVLP固定 vs ギプス固定の比較前向き観察研究。","results":"VLP固定群とギプス固定群で機能的転帰（DASH・PRWE・ROM・握力）に統計的有意差なし。","conclusion":"高齢者DRFは活動レベル・合併症・麻酔リスクの複合的評価に基づく個別化治療選択が必要。"},
  {"id":"hi1","title":"DUALITY試験（RCT・1600例）：大腿骨頸部骨折THA後のデュアルモビリティカップで脱臼リスク70%低下","journal":"The Lancet, 2026年7月2日","overview":"英国・スウェーデン44施設・1600例の国際多施設RCT。転位性大腿骨頸部骨折へのDM-THR vs 標準THRを比較。","results":"DM-THRを受けた患者は術後脱臼リスクが70%低かった。","conclusion":"大腿骨頸部骨折THA後のデュアルモビリティ設計の標準化を後押しする2026年を代表するRCT。"},
  {"id":"hi2","title":"HIP ATTACK試験サブ解析：トロポニン上昇例でも超早期手術が90日死亡率を57%低下","journal":"JBJS, 2024年","overview":"69施設・17カ国RCT（HIP ATTACK試験）のサブ解析。入院時トロポニン上昇322例を超早期手術群 vs 標準治療群に分けて比較。","results":"90日死亡率：超早期手術群10% vs 標準治療群23%、HR 0.43（95%CI 0.24〜0.77）で有意低下。","conclusion":"「MINSを伴う場合は手術を遅らせるべき」という従来の通念を覆すデータ。"},
  {"id":"hi3","title":"寛骨臼回転骨切り術（PAO）：10年で80%以上がTHAを回避・機能スコア維持（多施設コホート）","journal":"Hip Int, 2026年","overview":"臼蓋形成不全に対するPAO施行後の10年転帰を評価した多施設コホート研究。","results":"10年時点で80%以上の患者がTHAを回避し機能スコアは維持・改善傾向。","conclusion":"PAOは適切に選択された患者で10年にわたる高い関節保存率を達成できることが多施設データで確認。"},
  {"id":"hi4","title":"骨粗鬆症合併THA：術前ビスホスホネート長期使用で周囲骨折リスクが有意に増加（OR 1.29）","journal":"J Arthroplasty, 2023→2026年継続参照","overview":"骨粗鬆症合併一次THA 9844例・1:1マッチングを対象に術前ビスホスホネート使用と2年転帰を比較した後向き研究。","results":"ビスホスホネート使用群で2年周囲骨折率が有意に高い（OR 1.29、95%CI 1.04〜1.61、p=0.022）。","conclusion":"長期使用による「凍りついた骨」がTHA時の周囲骨折リスクを逆に増加させる可能性があり、術前使用歴を考慮したインプラント選択が重要。"},
  {"id":"hi5","title":"三重テーパーカラー付き非セメントステムで早期周囲骨折リスクを従来型比3分の1に低減（AJRR・JAAOS）","journal":"JAAOS, 2026年8月","overview":"米国AJRRデータを用いた大規模多施設解析。圧入型三重テーパーカラー付きセメントレスステムの早期周囲骨折率を評価した研究。","results":"モダンな三重テーパーカラー付き非セメントステムが早期周囲骨折リスクを従来型比3倍低下させた。","conclusion":"「セメント vs 非セメント」の二項対立から「どの設計のステムを選ぶか」という議論へシフトが加速。"},
  {"id":"kn1","title":"内側区画型膝OAへのUKA vs HTO：56000例メタ解析でUKAが合併症・再置換率・術後疼痛で有意に優れる","journal":"Orthop Surg, 2025年7月","overview":"UKAとHTOを比較した39研究・56686例のメタ解析（random-effectsモデル、GRADE評価）。","results":"UKAはHTOと比較して合併症率（RR=0.37）・TKA再置換率（RR=0.64）・術後疼痛（MD=-0.33）のすべてで有意に優れた。","conclusion":"56000例規模のメタ解析としてUKAが内側区画型膝OAにおいてHTOより優れることが示された。"},
  {"id":"kn2","title":"セメントレスTKA（50歳未満）：平均30.3年超長期追跡で優秀な生存率・主要失敗原因はγ線照射ポリエチレン摩耗","journal":"J Arthroplasty, 2026年6月","overview":"50歳以下の患者75例に対してセメントレスTKAを施行し、平均30.3年追跡した単施設超長期研究。","results":"セメントレスTKAは若年コホートで優秀な30年生存率を示した。主要失敗原因はγ線照射ポリエチレンの摩耗であり、骨内固定自体の失敗は少なかった。","conclusion":"現代の高架橋ポリエチレンは耐摩耗性が格段に向上しており、若年患者へのセメントレスTKAの有効性を超長期で支持する重要なエビデンス。"},
  {"id":"kn3","title":"変性内側半月板後根断裂への半月板切除：6.3年追跡で臨床転帰は保存療法と同等だがOA進行が有意に速い","journal":"後向き比較研究, 2026年参照","overview":"変性MMPRT 146例（切除群90・保存療法群56）を平均6.3年追跡した後向き比較研究。","results":"臨床転帰は両群で有意差なし。OA進行・内側関節裂隙幅の悪化は切除群で有意に高率（p=0.03〜0.04）。","conclusion":"変性MMPRTへの関節鏡的切除は臨床症状改善では保存療法と同等だがOA進行を有意に加速させる。"},
  {"id":"kn4","title":"ACL再建＋外側半月板後根（LMPR）修復：単独ACLRと機能・安定性が同等でMRI癒合良好","journal":"J Exp Orthop, 2026年4月","overview":"ACLR＋LMPR修復を施行した55歳未満・最低2年追跡患者と傾向スコアマッチした単独ACLR患者を比較した後向きコホート研究。","results":"AP・回旋安定性・KOOSが単独ACLRと同等。MRIでは高い骨癒合率が確認された。","conclusion":"LMPR修復をACLRに同時付加しても機能転帰を悪化させず膝安定性改善に貢献する可能性が示された。"},
  {"id":"kn5","title":"変性性関節炎GWAS：196万人で962の独立した遺伝的関連・700エフェクター遺伝子・473承認薬が再目的化候補","journal":"Nature, 2025年4月","overview":"Helmholtz Munich主導の過去最大規模OA-GWAS。489975例 vs 1472094例。","results":"962の独立した遺伝的関連（うち513が新規）。700エフェクター遺伝子を同定、うち69遺伝子の蛋白産物が473種承認薬の標的。","conclusion":"OAのdisease-modifying治療のない現状に対し、既承認薬の再目的化への道を開く画期的GWAS。"},
  {"id":"tr1","title":"転位性関節内踵骨骨折：ORIF＋一期的距骨下関節固定術でORIF単独と同等以上の転帰・二次手術を回避","journal":"Bone Joint J, 2026年3月","overview":"サイナスタルジアアプローチを用いたORIF＋一期的距骨下関節固定術（PSA）を施行した64例（62患者）を後向きに評価した研究。","results":"ORIF＋PSAは良好な距骨下関節癒合率と機能転帰・QOLを達成。ORIF単独・二期的固定術と同等以上の転帰が得られた。","conclusion":"Sanders III〜IV・高度粉砕・後部関節面重篤軟骨損傷例では一期的PSAが二次手術の必要性を低減しながら良好な転帰をもたらす選択肢として確立しつつある。"},
  {"id":"tr2","title":"開放性脛骨骨折：ゲンタマイシンコーティング髄内釘（GCN）が2年時点でもFRI発生率を有意に低減","journal":"Antibiotics, 2025年5月","overview":"開放性脛骨骨折139例（Gustilo-Anderson分類）に対してGCNを使用し最低24ヶ月追跡した前向きコホート研究。","results":"GCNはGA分類によらず非コーティング釘と比較してFRI発生率を有意に低減。2年追跡でも効果の持続が確認。","conclusion":"局所抗菌薬含浸インプラントが開放性骨折管理における標準的選択肢として確立しつつある。"},
  {"id":"tr3","title":"上腕骨近位端骨折31761例スウェーデンレジストリ：保存療法後の手術移行率3.7%・80歳以上＋単純骨折では2%未満","journal":"JBJS What's New in Orthopaedic Trauma, 2026年7月","overview":"スウェーデン骨折レジストリ2013〜2021年データ。全年齢成人31761例の上腕骨近位端骨折保存療法後の早期手術移行率を評価。","results":"保存療法後の手術移行率は全体3.7%。80歳以上かつ単純骨折型では移行率2%未満。C型骨折・骨折脱臼では5〜20%。","conclusion":"高齢者の単純型上腕骨近位端骨折に対して保存療法が安全な第一選択であることが世界最大規模のレジストリデータで確認。"},
  {"id":"tr4","title":"大腿骨骨幹部骨折：拡髄髄内釘が非拡髄より骨癒合・骨不癒合率・二次手術率で有意に優れる（8RCTメタ解析）","journal":"Medicine, 2026年参照","overview":"大腿骨骨幹部骨折への拡髄髄内釘（RIN）vs 非拡髄（URIN）を比較した前向きRCTのメタ解析（8RCT）。","results":"RINは非拡髄群と比較して骨癒合期間が有意に短く（SMD=-0.62）、二次手術率（OR=0.25）・骨不癒合率（OR=0.14）が有意に低かった。","conclusion":"閉鎖骨折では拡髄髄内釘が第一選択というコンセンサスがさらに強固になった。"},
  {"id":"tr5","title":"足関節下脛腓固定：スーチャーボタン vs シンデスモーシスネジ 機能スコア差はMCIDを超えない可能性（アンブレラレビュー）","journal":"Injury, 2026年1月","overview":"SB vs SS比較の19件系統的レビュー・メタ解析を対象としたアンブレラレビュー。AOFAS・OMASスコアをMCID閾値と照合して再評価。","results":"SBはSSよりAOFAS・OMASで統計的に高いスコアを示す研究が大多数。しかし多くのケースでその差がMCID（OMAS 7.5〜11.4点）を超えなかった。","conclusion":"「統計的有意差≠臨床的意義」という重要な問題を提起。整復精度・再手術率ではSBが優れ、コスト・シンプルさではSSが有利という状況が続いている。"}
]

print(f"📖 既存{len(BASE_PAPERS)}件の論文詳細解析を一括生成します...")

existing = {}
try:
    with open("details.json", encoding="utf-8") as f:
        existing = json.load(f)
except Exception:
    pass

generated = 0
for i, p in enumerate(BASE_PAPERS):
    if p["id"] in existing:
        print(f"  ⏭ スキップ（生成済み）: {p['title'][:30]}...")
        continue
    try:
        prompt = f"""あなたは整形外科の専門家です。以下の論文について整形外科医向けの詳細な解説をJSON形式のみで返してください。

論文タイトル: {p['title']}
雑誌: {p['journal']}
概要: {p['overview']}
結果: {p['results']}
結論: {p['conclusion']}

フィールド:
- background（研究背景と臨床的課題、3〜4文）
- methodology（研究デザイン・対象・方法の詳細、3〜4文）
- keyFindings（主要な発見・数値の詳細、3〜4文）
- clinicalImpact（日本の整形外科診療への臨床的インパクト、3〜4文）
- limitations（研究の限界・課題、2〜3文）
- relatedEvidence（関連エビデンスとの比較・文脈、2〜3文）

JSONのみを返し、前置きや説明文は含めないこと。"""

        resp = model.generate_content(prompt)
        dm = re.search(r'\{[\s\S]*\}', resp.text)
        if dm:
            existing[p["id"]] = json.loads(dm.group(0))
            generated += 1
            print(f"  ✅ [{i+1}/{len(BASE_PAPERS)}] {p['title'][:35]}...")
        time.sleep(1)  # レート制限対策
    except Exception as e:
        print(f"  ⚠ スキップ ({p['id']}): {e}")
        time.sleep(3)

with open("details.json", "w", encoding="utf-8") as f:
    json.dump(existing, f, ensure_ascii=False, indent=2)

print(f"\n✅ 完了: {generated}件を新規生成（累計 {len(existing)}件が details.json に保存されました）")
