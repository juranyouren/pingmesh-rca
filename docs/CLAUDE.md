# CLAUDE.md

## 椤圭洰瀹氫綅
闈㈠悜澶ц妯℃暟鎹腑蹇冪綉缁滅殑鏍瑰洜瀹氫綅锛圧CA锛夌郴缁熴€傛柟妗堬細**Pingmesh 瑙﹀彂 鈫?Skill Pipeline锛坱opo+temporal 骞惰璇勫垎铻嶅悎锛夆啋 璇佹嵁铻嶅悎灞?鈫?LLM 閲嶆帓瀹℃牳**锛屽熀浜庡崕涓轰簯 159 渚嬩汉宸ユ爣娉ㄦ晠闅滄渚嬮獙璇併€?
## 鍏抽敭绾︽潫
- **绾唴缃戠幆澧?*锛氭棤娉曡皟鐢ㄥ閮?LLM API锛屾墍鏈夋ā鍨嬪繀椤绘湰鍦伴儴缃?- **鏁版嵁鍚堣**锛氬崕涓轰簯鍐呴儴鏁呴殰鏁版嵁锛屾棤娉曞叕寮€鍙戝竷
- **纭欢**锛氬崕涓洪膊楣?920 (256 鏍? + 2TB 鍐呭瓨 + 8脳 Ascend 910B3 NPU锛?4GB HBM/鍗★級

## 鍒嗘敮绛栫暐

| 鍒嗘敮 | 鐢ㄩ€?|
|------|------|
| `main` | 涓诲垎鏀?鈥?鍏徃鏁版嵁闆?(nodes_labeled / nodes / nodes_extend) 涓婄殑鏂规硶鏀硅繘 |
| `nika` | NIKA 鍏紑鏁版嵁闆嗛€傞厤 鈥?鍙叕寮€鍙戣〃鐨勭粨鏋?|

NIKA 鍒嗘敮鍒濆浠ｇ爜涓?main 涓€鑷达紝鍚庣画鍚勮嚜鐙珛婕旇繘銆?
## 浠撳簱缁撴瀯

| 鐩綍/鏂囦欢 | 鐢ㄩ€?|
|-----------|------|
| `Sys/config.py` | 闆嗕腑閰嶇疆锛氳矾寰勩€佹ā鍨嬨€丯PU銆丳ageRank銆佹椂搴忋€丼kill 閫夋嫨 |
| `Sys/Preprocess/Preprocessor.py` | **鏁版嵁棰勫鐞?*锛歊AW 鍚堝苟 鈫?鏍￠獙 鈫?鎻愬彇 NODE 鏁版嵁 |
| `Sys/RootCauseAnalyze/SkilledAnalyzer.py` | Skill 瑙﹀彂 + LLM 閲嶆帓瀹℃牳鐨?RCA 鍒嗘瀽鍣?|
| `Sys/RootCauseAnalyze/gate/evidence.py` | 璇佹嵁铻嶅悎灞傦細涓や釜 Skill 杈撳嚭 鈫?鍊欓€夎澶囩患鍚堣瘉鎹〃 + Top-K 璇︽儏 |
| `Sys/RootCauseAnalyze/skill_pipeline.py` | 绾畻娉曟祦姘寸嚎锛歋kill 缁勫悎璇勫垎铻嶅悎锛堜笉渚濊禆 LLM/NPU锛夛紝绔埌绔瘎娴?|
| `Sys/RootCauseAnalyze/llm_alarm_scorer.py` | LLM 鍛婅鎵撳垎锛氬缂哄け鍛婅鍘婚噸鍚庣敤 LLM 璇箟鎵撳垎 1-100锛岃ˉ鍏ㄦ潈閲嶈〃 |
| `Sys/Score/Score_N.py` | 璇勫垎妯″潡锛圱op-1~5锛夛紝skill/llm 鍒嗗眰璇勬祴 |
| `Sys/Score/failure_analyzer.py` | 澶辫触妗堜緥 node 鏁版嵁璇婃柇 |
| `Sys/AlarmWeightBuilder.py` | 鍏ㄥ眬鍛婅鏉冮噸鏋勫缓鍣細`build()` / `learn_from_labels()` |
| `scripts/` | Bash 鎺ㄧ悊/娑堣瀺鑴氭湰 |
| `tmp/` | 鏈嶅姟鍣ㄧ璇婃柇/棰勫鐞?鏍囨敞杈呭姪鑴氭湰 |
| `Baseline/` | 鍩虹嚎鏂规硶锛歍raceRCA銆丯etEventCause銆丅iAn |
| `data/` | 鏍囨敞鏁版嵁锛坣odes_labeled, pingmesh_labeled锛?|
| `docs/` | 姹囨姤銆佹柟妗堜粙缁嶃€佺粯鍥炬彁绀鸿瘝銆佸紑鍙戞暀璁?|

## 鎶€鏈爤
- **LLM 鎺ㄧ悊**: DeepSeek-R1-Distill-Qwen-32B (vLLM 0.7.3 + Ascend 910B3 NPU)
- **鏍稿績渚濊禆**: PyTorch 2.5.1, LangChain 0.3.12, NumPy, pandas, networkx

## 瀹為獙缁撴灉鎬昏

### 鏈€浣崇粨鏋?(159 渚嬩汉宸ユ爣娉? 2026-06 鏈€鏂?

| 缁勫悎 | Top-1 | Top-3 | Top-5 |
|------|-------|-------|-------|
| **[1,2] topo+temporal (manual鏉冮噸)** | **76.10%** | 85.53% | 91.19% |
| [1,2] topo+temporal (llm鏉冮噸) | 66.67% | 88.05% | 93.71% |
| [2] temporal only (manual) | 62.89% | 88.05% | 94.34% |
| [1] topo only (manual) | 50.31% | 74.21% | 84.28% |

**LLM 鍚庣疆鎺ㄧ悊** (鍩轰簬 [1,2] manual 鏉冮噸 + gate/evidence):
| 璇勬祴灞?| Top-1 | Top-3 | Top-5 |
|--------|-------|-------|-------|
| skill_evaluation (绾畻娉? | 76.10% | 84.91% | 91.19% |
| llm_evaluation (LLM 閲嶆帓) | 75.47% | 86.79% | 86.79% |

LLM 鍩烘湰鏈仛鍙樻洿鈥斺€旂患鍚堝垎宸窛瓒冲澶ф椂 LLM 淇′换绠楁硶鎺掑悕锛岃繖涓?prompt 璁捐涓€鑷淬€?
### 鍘嗗彶瀵规瘮

| 鏁版嵁 | 妗堜緥鏁?| 鏍囨敞 | Top-1 (topo+temp) | 鍏抽敭鍙戠幇 |
|------|--------|------|-------------------|---------|
| 姣曡 (v1.0) | 104 | 闈炰汉宸?| 60.00% | 鏃ф爣娉ㄤ笉鍙潬 |
| nodes_labeled (鑴辨晱) | 146 | 浜哄伐 | 56.64% | 鍛婅绋€鐤? 136/146 case 鍛婅 鈮? |
| **nodes_extend (褰撳墠)** | **159** | **浜哄伐** | **76.10%** | **瀹屾暣鍛婅鏁版嵁** |

### 娑堣瀺缁撹
- Topo 鍗曠嫭: 50.31% (姣旇劚鏁忔暟鎹?38-43% 楂?7-12pp 鈫?鍛婅鎭㈠鍚?PR 鐢熸晥)
- Temporal 鍗曠嫭: 62.89% (鏃跺簭鏈夋晥, 浠嶆槸鏈€寮哄崟淇″彿)
- **Topo + Temporal: 76.10% (+13pp over temporal alone)** 鈥?鍗忓悓璇佹嵁纭嚳
- LLM 閲嶆帓: 75.47% (LLM 涓嶅簲涓诲姩鏀规帓鍚? 浠呭湪淇″彿鎺ヨ繎鏃惰鍐?

## 褰撳墠鏂规锛坴2.0锛?
```
Pingmesh 鍛婅 鈫?鈹攢 Skill 1: 鏈夊悜 PageRank 鈹€鈹?                鈹斺攢 Skill 2: 鏃跺簭瀚岀枒搴?   鈹€鈹?                                           鈫?                                    褰掍竴鍖栫瓑鏉冭瀺鍚?                                           鈫?                                    璇佹嵁铻嶅悎灞傦紙绱у噾琛級
                                           鈫?                                    LLM 閲嶆帓瀹℃牳
                                           鈫?                                      鏈€缁堟牴鍥?IP
```

### Skill 1锛氭湁鍚?PageRank
Personalization 鍚戦噺鐢卞憡璀︽潈閲?+ cross 浜ゆ眹搴?+ source/sink 閭昏繎搴﹀垵濮嬪寲銆?鍦?Spine-Leaf 鎷撴墤涓娇鐢ㄦ湁鍚戝浘锛坙inked_from/linked_to 浣滀负鏂瑰悜锛屼絾闇€娉ㄦ剰杩欐槸灞傛鏍囩鑰岄潪鍥犳灉鏂瑰悜锛夈€?
### Skill 2锛氭椂搴忓珜鐤戝害
| 鐗瑰緛 | 鍏紡 | 鏉冮噸 |
|------|------|------|
| Burst Score | `count(abs(t - ref_time) 鈮?5min) / total` | 0.40 |
| Early Bird | `1 / rank(first_alarm_among_all_devices)` | 0.35 |
| Temporal Density | `alarm_count / active_span_min` (cap 20/min) | 0.25 |

鏄綋鍓嶆渶寮哄崟淇″彿銆傚弬鑰冩椂闂?fallback锛歚ref_time_ms` 鈫?`info["alarm_time"]` 鈫?`*_info.json`銆?
### 璇佹嵁铻嶅悎灞?鐩存帴璋冪敤 skill_pipeline 鐨勮瘎鍒嗗嚱鏁帮紙涓庢秷铻嶅疄楠屼竴鑷达級锛岃緭鍑轰笁娈电揣鍑戞枃鏈紝鍘嬬缉姣?75-93%銆?
### LLM 瑙掕壊
"閲嶆帓瀹℃牳涓撳" 鈥?绠楁硶宸叉寜缁煎悎鍒嗘帓濂斤紝LLM 鍦ㄤ俊鍙锋帴杩戞椂鐢ㄥ憡璀﹁涔夎鍐炽€?
LLM 瀵瑰叏閲忓憡璀﹀仛 causal/symptom/noise 涓夊垎绫汇€倀emporal 鍗曠嫭 +1.9pp锛屼絾铻嶅悎閫€姝?鈭?.6pp
锛堝垎绫诲姞鏉冨彧瑕嗙洊鍛戒腑鏉冮噸琛ㄧ殑鍛婅锛屾湭瑕嗙洊瑁稿憡璀﹀悕 鈫?PR 鍧囧寑鍒嗗竷娣规病 temporal锛夈€?涓嬩竴姝ラ渶鎵╁睍瑕嗙洊鑼冨洿銆?
## 閰嶇疆绠＄悊

**鏂规 A锛堝綋鍓嶏級**锛氱幆澧冨彉閲?+ `scripts/common.sh` 浣滀负鍗曚竴鏉ユ簮銆?
| 鍙橀噺 | 榛樿鍊?| 璇存槑 |
|------|--------|------|
| `PINGMESH_PROJECT_ROOT` | `/home/sbp/lixinyang/pingmesh` | 椤圭洰鏍圭洰褰?|
| `PINGMESH_DATA` | `.../data/node/nodes_labeled` | node 鏁版嵁鐩綍 |
| `PINGMESH_RESULTS` | `.../data/res` | 缁撴灉鐩綍 |
| `PINGMESH_WEIGHTS_MANUAL` | `.../all_alarms.json` | 浜哄伐鏉冮噸 |
| `PINGMESH_WEIGHTS_LLM` | `.../alarm_weights.json` | LLM 瀛︿範鏉冮噸 |
| `PINGMESH_SKILLS` | `1 2` | 榛樿 Skill |
| `PINGMESH_TOP_K` | `5` | 鍊欓€夋暟 |

## 鎺ㄧ悊鑴氭湰

| 鑴氭湰 | 渚濊禆 | 鐢ㄩ€?|
|------|------|------|
| `run_inference.sh` | NPU | 鍗曟鎺ㄧ悊 + 璇勫垎 |
| `run_full_ablation.sh` | 鏃?| 6 缁勭函绠楁硶娑堣瀺 |
| `run_llm_alarm_scoring.sh` | NPU | LLM 鍛婅鍘婚噸鎵撳垎 |

## 寰呭姙锛堟寜浼樺厛绾э級

### P0: 缁撴瀯鍖?Prompt锛堚渽 宸插畬鎴愶級
### P0: 鍛婅淇℃伅瑙勮寖鍖栵紙1.3锛?### P1: 灏忔ā鍨嬪墠缃墦鍒嗭紙2.1-2.4锛?### P2: 鍏朵粬 鈥?璋?K / NIKA / LoRA SFT

## 娉ㄦ剰浜嬮」
- co_occur Skill 宸插純鐢ㄥ垹闄?- 鏈夊悜 PageRank锛歋pine-Leaf 鎷撴墤涓?linked_from/to 鏄眰娆℃爣绛撅紝涓嶇紪鐮佸洜鏋滄柟鍚戯紝璁烘枃搴旇瘹瀹炲憟鐜?- 鍛婅瀛楁绾﹀畾锛堝叏浠撳簱缁熶竴锛夛細`alarm_name > name > 绌哄瓧绗︿覆`
- historical 鏁版嵁娉勬紡宸蹭慨澶嶏紙`temporal_score.py` 涓嶅啀璇?`label.json`锛?
