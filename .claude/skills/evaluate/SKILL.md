---
name: evaluate
description: 평가 데이터셋으로 RAG 품질을 측정하고 실험 결과를 기록한다
disable-model-invocation: true
---

다음 순서로 진행한다. $ARGUMENTS 는 이번 실험의 변경 내용이다.

1. `docs/03-evaluation.md`의 지표 정의를 확인한다.
2. `eval/`의 평가 스크립트를 실행한다. 스크립트가 없으면 로드맵 2단계를 먼저 진행하자고 안내하고 멈춘다.
3. 결과를 `eval/results/`에 날짜별로 저장한다.
4. `docs/03-evaluation.md`의 실험 기록 표에 실제 측정값을 추가한다.
5. 이전 결과와 비교하고, 나빠진 지표와 실패 사례를 요약한다.

측정하지 않은 값은 추정해서 적지 않는다.
